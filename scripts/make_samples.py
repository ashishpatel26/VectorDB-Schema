"""Generate FAKE sample documents: data/samples/<industry>.jsonl + golden_queries.json.

All names, tokens and numbers are invented. Each industry has 4 good docs over 2 tenants
plus 1 deliberately bad doc that a gate must quarantine.
Run: uv run python scripts/make_samples.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "samples"

COMMON = {"source_version": "1", "purpose": "rag_search", "language": "en",
          "valid_from": "2026-01-01", "valid_to": None, "retention_until": "2033-12-31"}


def doc(sid, tenant, system, entity, title, text, cls, groups, juris, meta, **over):
    return {**COMMON, "source_id": sid, "tenant_id": tenant, "source_system": system,
            "entity_type": entity, "title": title, "text": text, "classification": cls,
            "allowed_groups": groups, "jurisdiction": juris, "metadata": meta, **over}


SAMPLES = {
    "healthcare": [
        doc("hc-001", "acme_health", "ehr_export", "clinical_note", "Discharge summary - chest pain",
            "Patient was admitted with chest pain and ruled out for myocardial infarction. Troponin levels remained "
            "normal across three draws. Discharged on low-dose aspirin and a statin with cardiology follow-up in two "
            "weeks. Patient advised to avoid strenuous exercise until stress test results are reviewed. "
            "Questions can be sent to cardio.desk@acme-health.example.",
            "confidential", ["care_team_cardiology"], "US-CA",
            {"patient_ref_token": "tok_p1001", "record_type": "discharge_summary", "provider": "Dr. A. Rivera",
             "encounter_date": "2026-02-10", "consent_scope": "treatment"}),
        doc("hc-002", "acme_health", "ehr_export", "care_plan", "Diabetes management plan",
            "HbA1c of 8.2 percent indicates suboptimal glycemic control. Metformin dose increased to 1000 mg twice "
            "daily. Dietitian referral placed for carbohydrate counting education. Recheck HbA1c in three months.",
            "confidential", ["care_team_endocrine"], "US-CA",
            {"patient_ref_token": "tok_p1002", "record_type": "care_plan", "provider": "Dr. M. Chen",
             "encounter_date": "2026-03-04", "consent_scope": "treatment"}),
        doc("hc-003", "beacon_clinic", "ehr_export", "clinical_note", "Well-child visit 18 months",
            "Well-child visit at 18 months. Growth tracking along the 60th percentile for height and weight. "
            "Immunizations administered per schedule including MMR and varicella boosters. Parents counseled on "
            "toddler sleep routines and car seat safety.",
            "confidential", ["care_team_pediatrics"], "US-NY",
            {"patient_ref_token": "tok_p2001", "record_type": "visit_note", "provider": "Dr. S. Patel",
             "encounter_date": "2026-01-22", "consent_scope": "treatment"}),
        doc("hc-004", "beacon_clinic", "ehr_export", "diagnostic_report", "Echocardiogram report",
            "Echocardiogram shows ejection fraction of 40 percent consistent with mild systolic dysfunction. Started "
            "on an ACE inhibitor and a beta blocker. Sodium restricted diet recommended. Enrolled in the heart failure "
            "clinic for monitoring.",
            "confidential", ["care_team_cardiology"], "US-NY",
            {"patient_ref_token": "tok_p2002", "record_type": "diagnostic_report", "provider": "Dr. L. Okafor",
             "encounter_date": "2026-02-18", "consent_scope": "care_coordination"}),
        doc("hc-bad", "acme_health", "ehr_export", "clinical_note", "Note with raw identifier",
            "Follow-up for patient SSN 123-45-6789 regarding medication refill.",
            "confidential", ["care_team_cardiology"], "US-CA",
            {"patient_ref_token": "tok_p1003", "record_type": "visit_note", "provider": "Dr. A. Rivera",
             "encounter_date": "2026-03-01", "consent_scope": "treatment"}),
    ],
    "banking": [
        doc("bk-001", "northbank", "core_banking", "policy", "Premium savings interest policy",
            "Premium savings accounts earn tiered interest. Balances above 10,000 earn 3.1 percent APY. Interest "
            "accrues daily and is credited monthly. Accounts falling below the minimum balance for 30 days revert to "
            "the standard rate.",
            "internal", ["retail_banking_ops"], "US",
            {"product": "savings", "account_type": "premium_savings", "document_type": "policy",
             "effective_date": "2026-01-01"}),
        doc("bk-002", "northbank", "core_banking", "procedure", "Mortgage pre-approval checklist",
            "Mortgage pre-approval requires two years of income statements, recent bank statements, credit report "
            "authorization and proof of down payment. Pre-approval is valid for 90 days. The debt-to-income ratio "
            "must not exceed 43 percent.",
            "internal", ["mortgage_team"], "US",
            {"product": "mortgage", "account_type": "loan", "document_type": "checklist",
             "effective_date": "2026-01-15"}),
        doc("bk-003", "river_cu", "core_banking", "procedure", "Card dispute procedure",
            "Members may dispute unauthorized card transactions within 60 days of the statement date. Provisional "
            "credit is issued within 10 business days while the investigation proceeds. Chargeback reason codes must "
            "be recorded on the case.",
            "internal", ["card_services"], "US",
            {"customer_ref_token": None, "product": "credit_card", "account_type": "card",
             "document_type": "procedure", "effective_date": "2026-02-01"}),
        doc("bk-004", "river_cu", "core_banking", "policy", "Wire transfer cutoff",
            "Domestic wires submitted before 3 PM Eastern settle the same business day. International wires require "
            "the beneficiary SWIFT code and purpose of payment. Wires above 50,000 need dual approval.",
            "internal", ["retail_banking_ops"], "US",
            {"product": "payments", "account_type": "checking", "document_type": "policy",
             "effective_date": "2026-01-10"}),
        doc("bk-bad", "northbank", "core_banking", "runbook", "Export runbook with credential",
            "Nightly export uses api_key=AKIAIOSFODNN7EXAMPLE to pull ledger files.",
            "internal", ["retail_banking_ops"], "US",
            {"product": "ops", "account_type": "n/a", "document_type": "runbook", "effective_date": "2026-01-01"}),
    ],
    "insurance": [
        doc("in-001", "shieldco", "claims_system", "claim_guideline", "Auto collision claim intake",
            "Auto collision claim intake requires the police report number, photos of vehicle damage and a repair "
            "estimate. An adjuster inspection is scheduled within 5 business days. Rental reimbursement covers up to "
            "30 days.",
            "internal", ["claims_adjusters"], "US-TX",
            {"policy_ref": "tok_pol100", "claim_ref": None, "line_of_business": "auto", "event_date": None,
             "claim_status": "n/a"}),
        doc("in-002", "shieldco", "claims_system", "underwriting_guideline", "Homeowner underwriting",
            "Roofs older than 20 years require an inspection before binding. Properties within 1,000 feet of a "
            "coastline need wind mitigation documentation. Prior water damage claims increase the deductible tier.",
            "internal", ["underwriting"], "US-TX",
            {"policy_ref": "tok_pol101", "line_of_business": "homeowners", "claim_status": "n/a"}),
        doc("in-003", "harbor_mutual", "claims_system", "claim_file", "Water damage claim",
            "A burst pipe in the kitchen caused flooring and cabinet damage. A mitigation vendor was dispatched within "
            "24 hours. The claim was approved for 18,400 after depreciation.",
            "confidential", ["claims_adjusters"], "US-FL",
            {"policy_ref": "tok_pol200", "claim_ref": "tok_clm200", "line_of_business": "homeowners",
             "event_date": "2026-02-02", "claim_status": "closed"}),
        doc("in-004", "harbor_mutual", "claims_system", "underwriting_guideline", "Commercial property renewal",
            "Commercial property renewal requires an updated sprinkler inspection certificate and occupancy details. "
            "Vacancy over 60 days voids coverage for vandalism.",
            "internal", ["underwriting"], "US-FL",
            {"policy_ref": "tok_pol201", "line_of_business": "commercial_property", "claim_status": "n/a"}),
        doc("in-bad", "shieldco", "personal_laptop", "claim_file", "Claim notes from unmanaged device",
            "Copied claim notes from a personal laptop export.",
            "internal", ["claims_adjusters"], "US-TX",
            {"policy_ref": "tok_pol102", "line_of_business": "auto", "claim_status": "open"}),
    ],
    "legal": [
        doc("lg-001", "lexpartners", "dms_legal", "memo", "Non-compete enforceability memo",
            "Memo on the enforceability of a non-compete clause under California law. Business and Professions Code "
            "section 16600 voids most employee non-compete agreements. Recommend removing the clause and relying on "
            "confidentiality obligations instead.",
            "restricted", ["matter_m100_team"], "US-CA",
            {"matter_id": "M-100", "client_ref": "tok_c100", "privilege_status": "privileged",
             "document_type": "memo", "effective_date": "2026-02-01"}),
        doc("lg-002", "lexpartners", "dms_legal", "contract_summary", "MSA summary",
            "Master services agreement summary: 36-month term with automatic renewal, liability capped at twelve "
            "months of fees, and termination for convenience on 90 days notice.",
            "internal", ["matter_m200_team"], "US-NY",
            {"matter_id": "M-200", "client_ref": "tok_c200", "privilege_status": "none",
             "document_type": "contract_summary", "effective_date": "2026-01-05"}),
        doc("lg-003", "cityattorneys", "dms_legal", "notice", "Litigation hold notice",
            "Litigation hold notice issued to custodians in procurement and finance. Preserve email, chat and shared "
            "drive records from January 2024 onward. Auto-delete policies are suspended for the listed mailboxes.",
            "restricted", ["matter_m300_team"], "US-IL",
            {"matter_id": "M-300", "client_ref": "tok_c300", "privilege_status": "work_product",
             "document_type": "hold_notice", "effective_date": "2026-01-20"}),
        doc("lg-004", "cityattorneys", "dms_legal", "schedule", "Deposition schedule",
            "Deposition schedule for the procurement dispute: three witnesses in March, with transcripts due ten days "
            "after each session.",
            "internal", ["matter_m300_team"], "US-IL",
            {"matter_id": "M-300", "client_ref": "tok_c300", "privilege_status": "none",
             "document_type": "schedule", "effective_date": "2026-02-10"}),
        doc("lg-bad", "lexpartners", "dms_legal", "memo", "Privileged memo marked public",
            "Strategy memo on settlement range for the pending dispute.",
            "public", ["matter_m100_team"], "US-CA",
            {"matter_id": "M-100", "client_ref": "tok_c100", "privilege_status": "privileged",
             "document_type": "memo", "effective_date": "2026-02-01"}),
    ],
    "retail": [
        doc("rt-001", "shopnova", "pim", "policy", "Apparel return policy",
            "Unworn apparel can be returned within 30 days with a receipt for a full refund. Final sale items and gift "
            "cards are not returnable. Online orders can also be returned in store.",
            "public", ["support_team"], "US",
            {"product_id": "prd-100", "sku": "APP-ALL", "brand": "Nova", "locale": "en-US", "channel": "omni",
             "inventory_region": "us"}),
        doc("rt-002", "shopnova", "pim", "promotion", "Spring trail shoe promotion",
            "Trail running shoe SKU TR-2201 is priced at 89.99 from March 1 to March 31. Inventory is allocated to "
            "west coast stores first.",
            "internal", ["merch_team"], "US",
            {"product_id": "prd-2201", "sku": "TR-2201", "brand": "Nova Trail", "locale": "en-US",
             "channel": "store", "price_valid_from": "2026-03-01", "price_valid_to": "2026-03-31",
             "inventory_region": "us-west"}),
        doc("rt-003", "urbanmart", "pim", "faq", "Grocery delivery FAQ",
            "Grocery delivery slots open 48 hours in advance. Orders above 50 qualify for free delivery. Substitutions "
            "are offered for out-of-stock items unless the customer opts out.",
            "public", ["support_team"], "DE",
            {"product_id": "svc-delivery", "sku": "DELIVERY", "brand": "UrbanMart", "locale": "en-GB",
             "channel": "online", "inventory_region": "eu"}),
        doc("rt-004", "urbanmart", "pim", "price_card", "Private label coffee price",
            "The private label coffee 1 kg bag is priced at 12.49 for EU stores until the end of the quarter. Fair "
            "trade certification must appear on shelf labels.",
            "internal", ["merch_team"], "DE",
            {"product_id": "prd-cof1", "sku": "COF-1KG", "brand": "UrbanMart Select", "locale": "de-DE",
             "channel": "store", "price_valid_from": "2026-01-01", "price_valid_to": "2026-03-31",
             "inventory_region": "eu"}),
        doc("rt-bad", "shopnova", "pim", "support_ticket", "Ticket with card number",
            "Customer paid with card 4111 1111 1111 1111 and wants a refund.",
            "internal", ["support_team"], "US",
            {"product_id": "prd-100", "sku": "APP-ALL", "brand": "Nova", "locale": "en-US", "channel": "online",
             "inventory_region": "us"}),
    ],
    "manufacturing": [
        doc("mf-001", "forgeworks", "plm", "procedure", "Hydraulic press lockout tagout",
            "Hydraulic press HP-400 lockout tagout procedure: isolate electrical and hydraulic energy, bleed residual "
            "pressure, apply personal locks, and verify zero energy before starting maintenance.",
            "internal", ["maintenance"], "US-OH",
            {"asset_id": "HP-400", "site_id": "site_a", "equipment_type": "hydraulic_press", "safety_class": "high",
             "revision": "C", "document_owner": "EHS", "approval_status": "approved"}),
        doc("mf-002", "forgeworks", "plm", "work_instruction", "CNC spindle warm-up",
            "Run the CNC mill spindle at 2,000 rpm for 10 minutes before production. Check coolant concentration "
            "daily with a target of 6 to 8 percent.",
            "internal", ["line_ops"], "US-OH",
            {"asset_id": "CNC-12", "site_id": "site_a", "equipment_type": "cnc_mill", "safety_class": "medium",
             "revision": "B", "document_owner": "Production", "approval_status": "approved"}),
        doc("mf-003", "voltgrid", "plm", "procedure", "Transformer oil sampling",
            "Transformer oil is sampled every 6 months. Dissolved gas analysis flags acetylene above 2 ppm for "
            "immediate engineering review.",
            "internal", ["maintenance"], "US-TX",
            {"asset_id": "TX-7", "site_id": "substation_7", "equipment_type": "transformer",
             "safety_class": "high", "revision": "A", "document_owner": "Asset Mgmt",
             "approval_status": "approved"}),
        doc("mf-004", "voltgrid", "plm", "safety_standard", "Switchgear arc flash boundary",
            "The arc flash boundary for switchgear SG-12 is 1.2 meters. Category 2 PPE is required for any energized "
            "work inside the boundary.",
            "internal", ["safety"], "US-TX",
            {"asset_id": "SG-12", "site_id": "substation_7", "equipment_type": "switchgear",
             "safety_class": "high", "revision": "D", "document_owner": "EHS", "approval_status": "approved"}),
        doc("mf-bad", "forgeworks", "plm", "procedure", "Draft press procedure",
            "Draft: new press changeover steps, not yet reviewed by EHS.",
            "internal", ["maintenance"], "US-OH",
            {"asset_id": "HP-400", "site_id": "site_a", "equipment_type": "hydraulic_press", "safety_class": "high",
             "revision": "D-draft", "document_owner": "EHS", "approval_status": "draft"}),
    ],
    "government": [
        doc("gv-001", "state_dmv", "records_mgmt", "public_guidance", "License renewal online",
            "A driver license can be renewed online every eight years if no vision test is required. Bring proof of "
            "residency for in-person renewals.",
            "public", ["public"], "US-CA",
            {"agency_id": "DMV", "record_class": "guidance", "release_status": "public_release"}),
        doc("gv-002", "state_dmv", "records_mgmt", "case_guideline", "Suspended license handling",
            "For suspended licenses, verify the court clearance letter, collect the reinstatement fee, and update the "
            "case record within 2 business days.",
            "confidential", ["caseworkers"], "US-CA",
            {"agency_id": "DMV", "record_class": "case_procedure", "release_status": "restricted_release",
             "case_ref_token": "tok_case77"}),
        doc("gv-003", "city_planning", "records_mgmt", "public_guidance", "Building permit requirements",
            "Residential building permit applications require a site plan, structural drawings and a zoning "
            "compliance letter. Review takes 15 business days.",
            "public", ["public"], "US-WA",
            {"agency_id": "PLANNING", "record_class": "guidance", "release_status": "public_release"}),
        doc("gv-004", "city_planning", "records_mgmt", "procedure", "Zoning variance hearing",
            "For a zoning variance hearing, notify property owners within 300 feet at least 10 days before the "
            "hearing date.",
            "internal", ["caseworkers"], "US-WA",
            {"agency_id": "PLANNING", "record_class": "procedure", "release_status": "restricted_release"}),
        doc("gv-bad", "state_dmv", "records_mgmt", "case_guideline", "Expired retention record",
            "Old case handling guide that should have been destroyed.",
            "internal", ["caseworkers"], "US-CA",
            {"agency_id": "DMV", "record_class": "case_procedure", "release_status": "restricted_release"},
            retention_until="2020-12-31"),
    ],
    "education_hr": [
        doc("ed-001", "northstate_univ", "lms_hris", "syllabus", "CS101 syllabus",
            "CS101 weekly programming labs count for 30 percent of the grade. Late submissions lose 10 percent per "
            "day. The final project is due in week 14.",
            "internal", ["course_cs101"], "US-MI",
            {"domain": "education", "org_unit": "engineering", "course_or_department": "CS101",
             "term": "2026-spring", "region": "us"}),
        doc("ed-002", "northstate_univ", "lms_hris", "announcement", "CS101 office hours",
            "Office hours are on Tuesdays and Thursdays from 2 to 4 PM in engineering building room 210, and online "
            "by appointment.",
            "internal", ["course_cs101"], "US-MI",
            {"domain": "education", "org_unit": "engineering", "course_or_department": "CS101",
             "term": "2026-spring", "region": "us"}),
        doc("ed-003", "globex_corp", "lms_hris", "policy", "Parental leave policy",
            "Primary caregivers receive 16 weeks of paid parental leave and secondary caregivers receive 6 weeks, "
            "available after 6 months of employment.",
            "internal", ["hr_partners"], "US",
            {"domain": "hr", "org_unit": "people", "course_or_department": "HR", "region": "us"}),
        doc("ed-004", "globex_corp", "lms_hris", "policy", "Remote work guideline",
            "Employees may work remotely up to three days per week with manager approval. A one-time equipment "
            "stipend of 500 is provided.",
            "internal", ["hr_partners"], "US",
            {"domain": "hr", "org_unit": "people", "course_or_department": "HR", "region": "us"}),
        doc("ed-bad", "globex_corp", "lms_hris", "policy", "Doc without ACL",
            "Compensation band adjustments for next cycle.",
            "confidential", [], "US",
            {"domain": "hr", "org_unit": "people", "course_or_department": "HR", "region": "us"}),
    ],
}

# golden queries: (tenant, groups, query, expected source_id)
GOLDEN = {
    "healthcare": [("acme_health", ["care_team_cardiology"], "chest pain troponin aspirin discharge", "hc-001"),
                   ("beacon_clinic", ["care_team_pediatrics"], "toddler vaccination schedule MMR", "hc-003")],
    "banking": [("northbank", ["mortgage_team"], "documents needed for mortgage pre-approval", "bk-002"),
                ("river_cu", ["card_services"], "how long do members have to dispute a card charge", "bk-003")],
    "insurance": [("shieldco", ["claims_adjusters"], "what is needed to file an auto collision claim", "in-001"),
                  ("harbor_mutual", ["underwriting"], "sprinkler certificate for commercial renewal", "in-004")],
    "legal": [("lexpartners", ["matter_m100_team"], "is a non-compete enforceable in California", "lg-001"),
              ("cityattorneys", ["matter_m300_team"], "preserve documents under litigation hold", "lg-003")],
    "retail": [("shopnova", ["support_team"], "return window for clothing", "rt-001"),
               ("urbanmart", ["support_team"], "minimum order for free delivery", "rt-003")],
    "manufacturing": [("forgeworks", ["maintenance"], "how to lock out the hydraulic press", "mf-001"),
                      ("voltgrid", ["safety"], "PPE required near switchgear", "mf-004")],
    "government": [("state_dmv", ["public"], "renew driver license online", "gv-001"),
                   ("city_planning", ["caseworkers"], "notify neighbors before zoning variance hearing", "gv-004")],
    "education_hr": [("northstate_univ", ["course_cs101"], "penalty for late lab submission", "ed-001"),
                     ("globex_corp", ["hr_partners"], "how many weeks of parental leave", "ed-003")],
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for industry, docs in SAMPLES.items():
        (OUT / f"{industry}.jsonl").write_text("\n".join(json.dumps(d) for d in docs) + "\n", encoding="utf-8")
    golden = [{"industry": i, "tenant_id": t, "groups": g, "query": q, "expected_source_id": e}
              for i, rows in GOLDEN.items() for t, g, q, e in rows]
    (OUT / "golden_queries.json").write_text(json.dumps(golden, indent=2), encoding="utf-8")
    print(f"wrote {sum(map(len, SAMPLES.values()))} docs for {len(SAMPLES)} industries + {len(golden)} golden queries")
