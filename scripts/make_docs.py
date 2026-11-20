"""Turn the FAKE sample docs into realistic files: data/docs/<industry>/<source_id>.pdf|.docx + manifest.jsonl.

Each file looks like a controlled business document: organization letterhead, classification banner,
document-control table, numbered sections (Purpose, Scope, Details, Responsibilities, References),
revision history, approval block, and a page footer. All organizations, people and numbers are invented.

- Odd-numbered docs (and the bad doc) -> PDF, even-numbered -> Word (.docx).
- manifest.jsonl = the source system's metadata export (tenant, ACL, classification, jurisdiction,
  validity, retention, industry fields). The LangChain loader merges it into Document.metadata.
Run: uv run python scripts/make_docs.py
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

from docx import Document as Docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from fpdf import FPDF

from make_samples import SAMPLES

OUT = Path(__file__).resolve().parents[1] / "data" / "docs"

ORGS = {  # tenant -> (display name, code, address, department)
    "acme_health": ("Acme Health System", "AHS", "1200 Harbor Blvd, San Diego, CA 92101", "Department of Medicine"),
    "beacon_clinic": ("Beacon Family Clinic", "BFC", "45 Elm Street, Albany, NY 12207", "Clinical Services"),
    "northbank": ("NorthBank N.A.", "NBK", "300 Market Street, Minneapolis, MN 55401", "Retail Banking Operations"),
    "river_cu": ("River Valley Credit Union", "RVCU", "88 Mill Road, Dayton, OH 45402", "Member Services"),
    "shieldco": ("ShieldCo Insurance", "SCI", "700 Commerce Ave, Austin, TX 78701", "Claims & Underwriting"),
    "harbor_mutual": ("Harbor Mutual Insurance", "HMI", "19 Bayfront Drive, Tampa, FL 33602", "Property Division"),
    "lexpartners": ("Lex Partners LLP", "LEX", "500 Grand Ave, Los Angeles, CA 90071", "Corporate Practice Group"),
    "cityattorneys": ("Office of the City Attorney", "OCA", "121 N LaSalle St, Chicago, IL 60602", "Litigation Division"),
    "shopnova": ("ShopNova Inc.", "SNV", "2400 Pine Street, Seattle, WA 98101", "Merchandising & Customer Care"),
    "urbanmart": ("UrbanMart GmbH", "UMG", "Friedrichstrasse 80, 10117 Berlin", "Category Management EU"),
    "forgeworks": ("ForgeWorks Manufacturing", "FWM", "9 Foundry Lane, Toledo, OH 43604", "Plant Engineering - Site A"),
    "voltgrid": ("VoltGrid Energy", "VGE", "1500 Power Parkway, Houston, TX 77002", "Transmission & Substations"),
    "state_dmv": ("State Department of Motor Vehicles", "DMV", "2415 First Ave, Sacramento, CA 95818", "Licensing Division"),
    "city_planning": ("City Planning Department", "CPD", "700 5th Ave, Seattle, WA 98104", "Permits & Zoning"),
    "northstate_univ": ("NorthState University", "NSU", "1 University Drive, Ann Arbor, MI 48109", "College of Engineering"),
    "globex_corp": ("Globex Corporation", "GLX", "10 Corporate Plaza, Denver, CO 80202", "People & Culture"),
}

INDUSTRY = {  # responsibilities, references, approver role
    "healthcare": (["Attending physician: accuracy and completeness of the clinical documentation.",
                    "Care team: completion of follow-up actions listed in this document.",
                    "Health Information Management: retention, amendment and release of information."],
                   ["HIPAA Privacy Rule, 45 CFR Part 164", "Clinical Documentation Standard CDS-04",
                    "Patient Consent and Authorization Policy PCP-02"], "Chief Medical Officer"),
    "banking": (["Product owner: content and rate parameters of this document.",
                 "Branch and operations staff: day-to-day execution.",
                 "Compliance: annual review against applicable regulation."],
                ["Truth in Savings Act (Regulation DD)", "Internal Control Standard ICS-11",
                 "Record Retention Schedule RRS-2026"], "Head of Retail Banking"),
    "insurance": (["Claims manager: adherence of adjusters to this guideline.",
                   "Underwriting lead: risk acceptance decisions and exceptions.",
                   "Compliance: alignment with state claims-handling regulation."],
                  ["Unfair Claims Settlement Practices Act (state)", "Underwriting Manual UW-3",
                   "Claims Handling Standard CH-7"], "VP Claims & Underwriting"),
    "legal": (["Responsible partner: legal conclusions and client communication.",
               "Matter team: confidentiality and need-to-know access.",
               "Records: privilege labeling and legal hold enforcement."],
              ["ABA Model Rule 1.6 (Confidentiality)", "Firm Privilege Protocol FP-1",
               "Litigation Hold Procedure LH-2"], "Managing Partner"),
    "retail": (["Category manager: pricing and promotion accuracy.",
                "Store operations: shelf labels and in-store execution.",
                "Customer care: consistent communication to customers."],
               ["Pricing Governance Policy PG-5", "Returns & Refunds Policy RP-1",
                "Consumer Protection Guidelines"], "Director of Merchandising"),
    "manufacturing": (["EHS manager: hazard assessment and procedure approval.",
                       "Maintenance supervisor: training and verification of qualified personnel.",
                       "Operators: follow every step; stop work if conditions differ."],
                      ["OSHA 29 CFR 1910.147 (Control of Hazardous Energy)", "NFPA 70E",
                       "Site Safety Manual SSM-2"], "Plant EHS Manager"),
    "government": (["Program manager: content and periodic review.",
                    "Caseworkers and counter staff: consistent application.",
                    "Records officer: retention and public-release decisions."],
                   ["State Public Records Act", "General Records Retention Schedule GRS-5",
                    "Agency Privacy Notice"], "Division Chief"),
    "education_hr": (["Owner (instructor or HR business partner): content and updates.",
                      "Department administration: communication to the audience.",
                      "Records: retention per institutional schedule."],
                     ["FERPA / Employee Privacy Policy", "Employee Handbook EH-2026",
                      "Academic Integrity Policy"], "Dean / Chief People Officer"),
}

PEOPLE = ["J. Morgan", "R. Alvarez", "K. Nakamura", "T. Brennan", "P. Singh", "L. Dubois", "M. Okoye", "S. Larsen"]
LIST_TYPES = {"procedure", "checklist", "work_instruction", "claim_guideline", "underwriting_guideline",
              "case_guideline", "policy", "safety_standard", "runbook"}
BANNER = {"public": (46, 125, 50), "internal": (21, 101, 192), "confidential": (230, 81, 0), "restricted": (183, 28, 28)}


def build(d: dict, idx: int) -> dict:
    """Structured content shared by the PDF and DOCX writers."""
    org, code, addr, dept = ORGS[d["tenant_id"]]
    ind = next(i for i, docs in SAMPLES.items() if d in docs)
    resp, refs, approver_role = INDUSTRY[ind]
    meta = d["metadata"]
    eff = date.fromisoformat(meta.get("effective_date") or meta.get("encounter_date") or d["valid_from"])
    etype = d["entity_type"].replace("_", " ")
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", d["text"].strip()) if s]
    author, approver = PEOPLE[idx % len(PEOPLE)], PEOPLE[(idx + 3) % len(PEOPLE)]
    return {
        "org": org, "addr": addr, "dept": dept, "title": d["title"], "cls": d["classification"],
        "doc_no": f"{code}-{d['entity_type'][:3].upper()}-{d['source_id'].upper()}",
        "control": [("Document No.", f"{code}-{d['entity_type'][:3].upper()}-{d['source_id'].upper()}"),
                    ("Version", f"{d['source_version']}.0"), ("Document type", etype.title()),
                    ("Effective date", eff.strftime("%d %b %Y")),
                    ("Next review", (eff + timedelta(days=365)).strftime("%d %b %Y")),
                    ("Owner", dept), ("Classification", d["classification"].upper()),
                    ("Jurisdiction", d["jurisdiction"])],
        "sections": [
            ("1. Purpose", [f"This {etype} sets out {d['title'].lower()} for {org}. "
                            f"It is the controlled reference for staff in {dept}."], False),
            ("2. Scope", [f"Applies to {dept} personnel with an approved business need. "
                          f"Distribution is limited to the groups authorized for this document."], False),
            ("3. Details", sentences, d["entity_type"] in LIST_TYPES),
            ("4. Responsibilities", resp, True),
            ("5. References", refs, True),
        ],
        "revisions": [("1.0", d["valid_from"], author, "Initial issue")],
        "approval": (approver, approver_role, eff.strftime("%d %b %Y")),
        "author": author,
    }


class PdfDoc(FPDF):
    def __init__(self, c):
        super().__init__()
        self.c = c
        self.set_auto_page_break(True, margin=20)

    def header(self):
        c = self.c
        self.set_fill_color(*BANNER[c["cls"]]); self.set_text_color(255)
        self.set_font("Helvetica", "B", 8)
        self.cell(0, 5, c["cls"].upper(), align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2); self.set_text_color(25, 45, 75); self.set_font("Helvetica", "B", 15)
        self.cell(0, 7, c["org"], new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 8); self.set_text_color(110)
        self.cell(0, 4, f"{c['dept']}  |  {c['addr']}", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(25, 45, 75); self.set_line_width(0.6)
        self.line(self.l_margin, self.get_y() + 2, self.w - self.r_margin, self.get_y() + 2)
        self.ln(6); self.set_text_color(30)

    def footer(self):
        self.set_y(-14); self.set_font("Helvetica", "", 7); self.set_text_color(120)
        self.cell(0, 4, f"{self.c['doc_no']}  |  {self.c['cls'].upper()}  |  Uncontrolled copy when printed  |  "
                        f"Page {self.page_no()} of {{nb}}", align="C")


def write_pdf(path: Path, c: dict) -> None:
    pdf = PdfDoc(c)
    pdf.set_title(c["title"]); pdf.set_author(c["author"]); pdf.set_subject(c["doc_no"]); pdf.set_creator(c["org"])
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16); pdf.multi_cell(0, 8, c["title"]); pdf.ln(2)
    pdf.set_font("Helvetica", size=9)
    with pdf.table(col_widths=(32, 63, 32, 63), text_align="LEFT", line_height=6,
                   headings_style=None, first_row_as_headings=False) as t:
        ctl = c["control"]
        for i in range(0, len(ctl), 2):
            row = t.row()
            for k, v in ctl[i:i + 2]:
                pdf.set_font("Helvetica", "B", 9); row.cell(k)
                row.cell(v)
    pdf.ln(4)
    for heading, items, as_list in c["sections"]:
        pdf.set_font("Helvetica", "B", 12); pdf.set_text_color(25, 45, 75)
        pdf.cell(0, 8, heading, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10.5); pdf.set_text_color(30)
        if as_list:
            for n, it in enumerate(items, 1):
                pdf.multi_cell(0, 5.5, f"  {n}.  {it}", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.multi_cell(0, 5.5, " ".join(items), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12); pdf.set_text_color(25, 45, 75)
    pdf.cell(0, 8, "Revision History", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9); pdf.set_text_color(30)
    with pdf.table(col_widths=(20, 35, 45, 90), text_align="LEFT", line_height=6) as t:
        t.row(["Version", "Date", "Author", "Change"])
        for r in c["revisions"]:
            t.row(list(r))
    pdf.ln(6)
    name, role, when = c["approval"]
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 6, f"Approved by: {name}, {role}        Date: {when}        Signature: ______________________",
             new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def write_docx(path: Path, c: dict) -> None:
    doc = Docx()
    st = doc.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(10.5)
    cp = doc.core_properties
    cp.title, cp.author, cp.subject, cp.category = c["title"], c["author"], c["doc_no"], c["cls"].upper()
    sec = doc.sections[0]
    hp = sec.header.paragraphs[0]
    r = hp.add_run(c["org"]); r.bold = True; r.font.size = Pt(12); r.font.color.rgb = RGBColor(25, 45, 75)
    r = hp.add_run(f"\t\t{c['cls'].upper()}"); r.bold = True; r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(*BANNER[c["cls"]])
    sub = sec.header.add_paragraph(f"{c['dept']}  |  {c['addr']}"); sub.runs[0].font.size = Pt(8)
    fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fr = fp.add_run(f"{c['doc_no']}  |  {c['cls'].upper()}  |  Uncontrolled copy when printed"); fr.font.size = Pt(8)

    doc.add_heading(c["title"], level=0)
    ctl = c["control"]
    tbl = doc.add_table(rows=0, cols=4); tbl.style = "Light Grid Accent 1"
    for i in range(0, len(ctl), 2):
        cells = tbl.add_row().cells
        for j, (k, v) in enumerate(ctl[i:i + 2]):
            cells[j * 2].text = k; cells[j * 2].paragraphs[0].runs[0].bold = True
            cells[j * 2 + 1].text = v
    for heading, items, as_list in c["sections"]:
        doc.add_heading(heading, level=1)
        if as_list:
            for it in items:
                doc.add_paragraph(it, style="List Number")
        else:
            doc.add_paragraph(" ".join(items))
    doc.add_heading("Revision History", level=1)
    rt = doc.add_table(rows=1, cols=4); rt.style = "Light List Accent 1"
    for cell, h in zip(rt.rows[0].cells, ["Version", "Date", "Author", "Change"]):
        cell.text = h
    for rev in c["revisions"]:
        for cell, v in zip(rt.add_row().cells, rev):
            cell.text = v
    name, role, when = c["approval"]
    doc.add_paragraph()
    doc.add_paragraph(f"Approved by: {name}, {role}\tDate: {when}\tSignature: ____________________")
    doc.save(str(path))


if __name__ == "__main__":
    total = 0
    for industry, docs in SAMPLES.items():
        folder = OUT / industry
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.*"):
            old.unlink()
        manifest = []
        for d in docs:
            num = d["source_id"].split("-")[-1]
            ext = "docx" if num.isdigit() and int(num) % 2 == 0 else "pdf"
            fname = f"{d['source_id']}.{ext}"
            content = build(d, total)
            (write_docx if ext == "docx" else write_pdf)(folder / fname, content)
            manifest.append({"file": fname, **{k: v for k, v in d.items() if k != "text"}})
            total += 1
        (folder / "manifest.jsonl").write_text("\n".join(json.dumps(m) for m in manifest) + "\n", encoding="utf-8")
    print(f"wrote {total} files (pdf + docx) + {len(SAMPLES)} manifests under {OUT}")
