# Plan: VectorDB Schema Project — one notebook per vector DB, separate index per industry

> **Update (2026-11-20):** there is no `src/vschema` package and no `tests/` folder. Each notebook is self-contained (schema, embedder, LangChain Word/PDF loading, gates, store). Sample input is realistic fake Word/PDF files in `data/docs/<industry>/` plus a `manifest.jsonl` holding the planned metadata. Where this plan says `stores/<db>.py` or `vschema`, read "the store section of that DB's notebook".

## Context
Build the "Vector Database Schema & Ingestion Guardrails" blueprint by hand in Python at `d:\Projects\VectorDB-Schema` (empty, Windows 11). The user writes the code; this plan is the guide.

Requirements:
- **6 vector DBs**: pgvector, Qdrant, Weaviate, Milvus, Chroma, LanceDB. All run locally or self-hosted.
- **Separate index per industry in every DB**: 8 industries × 6 DBs = 48 indexes.
- **One Jupyter notebook per DB**, all with the same section structure so results compare directly.
- Follow standard vector DB design patterns (section 2).

Core idea: one shared Python package (`vschema`) holds the schema, gates, sample data and embedding code. The notebooks stay thin. Each one only shows how its DB maps the same schema and runs the same checks.

---

## 1. Industries (8 indexes per DB)
`healthcare, banking, insurance, legal, retail, manufacturing, government, education_hr`

Every industry index has:
- **base fields** (identity, provenance, content/vector, access, lifecycle)
- **its industry fields**, taken from the infographic (e.g. healthcare: `patient_ref_token, record_type, provider, encounter_date, consent_scope`)

Index naming everywhere: `{industry}_v{schema}_{model}_{dim}`, e.g. `healthcare_v1_bgesmall_384`, plus an alias or view called `healthcare`.

## 2. Design patterns to follow

| # | Pattern | Applied as |
|---|---|---|
| 1 | Index, not source of truth | Postgres `sources` table is the system of record. Every vector index can be rebuilt from it. |
| 2 | Deterministic ID + idempotent upsert | `chunk_id = sha256(tenant\|source\|version\|chunk_no)`. Re-running a batch gives the same row count. |
| 3 | **Index per industry** (your choice) + tenant partition inside it | Industry = separate index. Tenant = partition key or filter inside the index. |
| 4 | Pre-filter in the vector query, re-authorize after | `tenant + ACL + status + validity` filters go inside the ANN query, never applied in Python after top-k. |
| 5 | Repository / adapter | One `stores/<db>.py` per DB with the same 5 functions (section 4). Notebooks call only these. |
| 6 | Gate pipeline, fail closed | Each gate returns a record or a `Rejection`. Rejections go to quarantine. |
| 7 | Versioned index + alias (blue/green) | A model change builds a new index, evaluates it, switches the alias, then drops the old one. |
| 8 | Status lifecycle | Status moves `staged → active → superseded/deleted`. Search reads only `active`. |
| 9 | Hard purge + verify absence | Delete by `source_id`, then assert 0 hits. |
| 10 | Embedding cache by `content_hash` | Unchanged chunks are not re-embedded. |
| 11 | Parent–child chunks | Add a `parent_id` field now; small-to-big retrieval logic comes later. |

Anti-patterns: raw PII in metadata, mixing embedding models in one index, random IDs, filtering after top-k, a vector DB as the only copy of the data.

## 3. Repo layout
```
VectorDB-Schema/
├── pyproject.toml              # pydantic, sentence-transformers, jupyter, pytest
│                               # extras: pg, qdrant, weaviate, milvus, chroma, lancedb
├── compose.yaml                # Podman compose, profiles: pg, qdrant, weaviate  (start only what you need)
├── docker/milvus/docker-compose.yml  # official Milvus standalone compose (etcd + minio + milvus)
├── data/
│   ├── samples/<industry>.jsonl   # ~10 fake docs per industry, 2 tenants each, NO real PII
│   ├── chroma/  lancedb/          # embedded DB files (gitignored)
├── sql/
│   ├── 000_base.sql            # extension, sources, quarantine, outbox
│   └── 010_industries.sql      # 8 chunks_<industry> tables + HNSW + RLS
├── src/vschema/
│   ├── base.py                 # BaseChunk, chunk_id()
│   ├── industries.py           # 8 subclasses + INDUSTRIES registry {name: model}
│   ├── gates.py                # gate funcs → record | Rejection
│   ├── embed.py                # pinned model, cache by content_hash
│   ├── samples.py              # load + chunk data/samples → validated records
│   └── stores/
│       ├── pgvector.py  qdrant.py  weaviate.py
│       └── milvus.py    chroma.py  lancedb.py
├── notebooks/
│   ├── 00_schema_and_gates.ipynb    # DB-agnostic: models, JSON Schema export, gates demo
│   ├── 01_pgvector.ipynb
│   ├── 02_qdrant.ipynb
│   ├── 03_weaviate.ipynb
│   ├── 04_milvus.ipynb
│   ├── 05_chroma.ipynb
│   ├── 06_lancedb.ipynb
│   └── 99_compare.ipynb             # latency, recall@k, isolation pass/fail across all 6
└── tests/
    └── test_contract.py        # one parametrized test runs every store through the same checks
```

## 4. Store contract (same in every `stores/<db>.py`)
```python
def create_indexes(industries, dim) -> None      # one index per industry + payload/filter indexes + alias
def upsert(industry, records) -> int             # idempotent
def safe_search(industry, tenant_id, groups, qvec, k) -> list  # raises if tenant/groups missing
def supersede(industry, source_id, old_version) -> int
def purge(industry, source_id) -> int            # caller then asserts safe_search finds 0
```

## 5. Per-DB mapping

| DB | Run | "Industry index" | Tenant isolation inside index | ACL filter (`allowed_groups`) | Notes |
|---|---|---|---|---|---|
| **pgvector** | Podman `pgvector/pgvector:pg17` :5432 | Table `chunks_<industry>`: base columns copied with `LIKE chunks_base INCLUDING ALL`, plus typed industry columns with `NOT NULL`/`CHECK` | **RLS** policy on `current_setting('app.tenant_id')`, non-superuser app role | `allowed_groups && :groups` + GIN index | HNSW `vector_cosine_ops`. Set `hnsw.iterative_scan = relaxed_order`. Alias = view `healthcare` |
| **Qdrant** | Podman `qdrant/qdrant` :6333/6334 | Collection per industry + alias | Payload index `tenant_id` keyword with `is_tenant=true` | `MatchAny` on keyword index | Point ID = `uuid5(ns, chunk_id)` |
| **Weaviate** | Podman `semitechnologies/weaviate` :8080/50051 | Collection per industry (v4 client) | **Native multi-tenancy**: tenant = `tenant_id` shard | `ContainsAny` filter on `text[]` property | `vectorizer: none` (we bring vectors). Collection alias for blue/green |
| **Milvus** | Podman, official standalone compose (milvus + etcd + minio). Milvus Lite has no Windows support | Collection per industry | `tenant_id` field `is_partition_key=True` | `ARRAY_CONTAINS_ANY(allowed_groups, [...])` | Heaviest. Start its compose file only when running this notebook. Alias supported |
| **Chroma** | Embedded `PersistentClient("data/chroma")` | Collection per industry | `where={"tenant_id": ...}` filter only | ⚠ List metadata support is limited. Store groups as bool flags `grp_<name>: True` and use an `$or` filter | Weakest isolation. Dev baseline only; mark this in the 99 comparison |
| **LanceDB** | Embedded `lancedb.connect("data/lancedb")` | Table per industry (PyArrow schema with typed industry columns) | `where("tenant_id = '...'", prefilter=True)` | SQL list function on the `allowed_groups` list column. Check the exact function name in the LanceDB filter docs | Scalar index on `tenant_id` and `status`. Vector index only after ~10k rows (flat search before that) |

## 6. Notebook template (same sections in 01–06)
1. **Setup**: start container (or open embedded path), connect, print version
2. **Create 8 industry indexes** with the shared registry, then list them back
3. **Ingest**: load `data/samples/<industry>.jsonl` → gates → embed (cached) → `upsert`. Show the quarantine count
4. **Idempotency**: upsert the same batch again and assert counts are unchanged
5. **Safe search**: same 3 golden queries per industry, as tenant A and as tenant B
6. **Isolation test**: tenant A never sees tenant B; a user without the group sees nothing
7. **Update**: new source version → supersede old → only new chunks returned
8. **Delete / consent withdrawal**: `purge` → assert 0 hits
9. **Model change**: build a `_v2_` index → re-embed → switch the alias → drop v1 (optional cell)
10. **Metrics cell**: write latency and recall@5 to `data/results/<db>.json` for notebook 99

## 6b. First deliverables (Claude writes these right after approval, before any code)

### `SETUP.md` (repo root): step-by-step setup guide, one section per DB
Common prereqs first: Python 3.12, `uv`, Podman machine (WSL), Jupyter kernel, pinned embedding model download (`bge-small-en-v1.5`), `.env` layout.
Then the same 7 steps for each DB (pgvector, Qdrant, Weaviate, Milvus, Chroma, LanceDB):
1. What it is, and whether it runs embedded or as a server
2. Install: Podman run/compose block (with the profile name) or `pip`/`uv add` extra
3. Start + health check command (e.g. `pg_isready`, `curl :6333/healthz`, `curl :8080/v1/.well-known/ready`, Milvus `:9091/healthz`)
4. Python client install + minimal connect snippet
5. Create one test industry index, insert 1 vector, query it, delete it (smoke test)
6. GUI / dashboard (pgAdmin/DBeaver, Qdrant dashboard, Attu for Milvus, etc.)
7. Stop / reset data / common Windows gotchas (ports, WSL memory for Milvus, volume paths)

Each command is checked against that DB's current official docs while writing (versions, ports, client API).

### `docs/PLAN.md`
A copy of this approved plan, kept in the repo as the reference design.

### `AGENTS.md` (repo root, per https://agents.md/)
Plain Markdown, no frontmatter, nearest file wins. Sections:
- Project overview (blueprint, 6 DBs × 8 industry indexes, Postgres = system of record)
- Setup commands (`uv sync`, `podman compose --profile … up -d`, pointer to SETUP.md)
- Build & test commands (`pytest tests/test_contract.py`, notebook "Restart & Run All")
- Code style (Pydantic models are the only schema source, store contract of 5 functions, naming `{industry}_v{n}_{model}_{dim}`)
- Design rules (fail closed, deterministic IDs, pre-filter in the query, no raw PII, never mix embedding models)
- Testing instructions (isolation + purge tests must pass before any store change)
- Security considerations (fake sample data only, `.env` not committed, RLS app role)
- PR / commit guidelines
`AGENT.md` symlink not needed (no legacy file).

## 7. Build order
1. `00_schema_and_gates` plus `vschema` package and sample data (no DB yet)
2. `01_pgvector`: also creates the Postgres system-of-record tables the others rebuild from
3. `02_qdrant` → `03_weaviate` → `05_chroma` → `06_lancedb` → `04_milvus` (heaviest last)
4. `99_compare`

## 8. Verification
- `podman compose --profile pg --profile qdrant --profile weaviate up -d`, then Milvus separately with `podman compose -f docker/milvus/docker-compose.yml up -d`
- `pytest tests/test_contract.py`: the same contract test runs against all 6 stores (skip stores whose server is down)
- Run every notebook top to bottom with "Restart & Run All". Sections 4, 6, 8 must assert green
- `99_compare` shows the isolation column all PASS (Chroma flagged as filter-only isolation)

## Skipped (add later)
- Hybrid BM25+vector search (Weaviate built-in, pg `tsvector`, Qdrant sparse vectors)
- Outbox sync worker (notebooks load from `sources` directly)
- Elasticsearch/OpenSearch, Vespa
