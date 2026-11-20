# AGENTS.md

Guidance for AI coding agents working in this repository. Format follows https://agents.md/. A nested `AGENTS.md` overrides this one for its own subfolder.

## Project overview
- Python implementation of the **Vector Database Schema & Ingestion Guardrails** blueprint.
- **6 vector DBs**: pgvector, Qdrant, Weaviate, Milvus, Chroma, LanceDB. **8 industry indexes** in each: healthcare, banking, insurance, legal, retail, manufacturing, government, education_hr.
- **Postgres is the system of record.** Every vector index is a rebuildable search index that points back to its sources.
- Full design: [docs/PLAN.md](docs/PLAN.md). Environment setup: [SETUP.md](SETUP.md).
- The repo owner builds this by hand to learn. Unless asked to write code, explain and review instead.

## Layout
- **No `src/` package.** Each notebook is self-contained: schema models, embedder, LangChain loading, gates and the DB store live in its cells.
- `notebooks/`: one per vector DB (`01_pgvector` … `06_lancedb`, `99_compare`), same sections in each so results compare.
- `data/docs/<industry>/`: realistic fake Word/PDF files + `manifest.jsonl` (planned metadata per file)
- `data/samples/`: fake source text (`<industry>.jsonl`) + `golden_queries.json`
- `scripts/`: `make_samples.py` -> `make_docs.py` (regenerate files), `setup.ps1` (environment)
- `sql/`: mounted into the pg container as init scripts (tables are created by the notebook)

## Setup commands
- Python env is **uv** (`.venv`, version from `.python-version`). Install: `uv sync --all-extras`. Notebook kernel `VectorDB Schema` points to `.venv`.
- Regenerate sample files: `uv run python scripts/make_samples.py`, then `cd scripts; uv run python make_docs.py`
- One-shot setup: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` (flags: `-SkipMilvus`, `-SkipContainers`, `-SetWslMemory`)
- Container runtime is **Podman** (no Docker). Always use full image names (`docker.io/...`).
- Start servers: `podman compose --profile pg --profile qdrant --profile weaviate up -d`
- Start Milvus: `podman compose -f docker/milvus/docker-compose.yml up -d`
- Chroma and LanceDB are embedded, so there is nothing to start.

## Build & test commands
- Run a notebook headless: `cd notebooks; uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.kernel_name=vectordb-schema 01_pgvector.ipynb`
- Assert cells (idempotency, isolation, update, purge) must pass with 0 error outputs.

## Code style
- uv `.venv` Python, type hints, Pydantic v2. Word/PDF loading uses LangChain (`PyPDFLoader`, `Docx2txtLoader`, `RecursiveCharacterTextSplitter`) inside the notebook.
- **The Pydantic models in each notebook are the only schema source.** DDL, collection configs and JSON Schema are derived from them, never hand-copied with different fields.
- Each notebook's store section implements the same functions: `create_indexes`, `upsert`, `promote`, `safe_search`, `supersede`, `purge`.
- Index naming: `{industry}_v{schema}_{model}_{dim}` (e.g. `healthcare_v1_bgesmall_384`), plus an alias or view named `{industry}`.
- Keep it small: no extra abstraction layers, factories or config frameworks.

## Design rules (do not break)
- **Fail closed**: a gate returns a record or a `Rejection`. Rejections go to quarantine and are never silently dropped.
- **Deterministic IDs**: `chunk_id = sha256(tenant_id|source_id|source_version|chunk_no)`. Upserts must be idempotent.
- **Pre-filter in the vector query** on tenant, `allowed_groups`, `status='active'` and validity dates. Never filter in Python after top-k.
- `safe_search` must raise if tenant or groups are missing.
- **One embedding model per index.** A model change means a new versioned index plus an alias switch.
- Deletion means a hard purge followed by a check that the data is gone.

## Testing instructions
- Before changing any store, the isolation tests (tenant A never sees tenant B; a user without the group gets 0 hits) and the purge test must pass for that store.
- Keep the schema cells identical across notebooks; change them all together.
- Chroma's isolation is filter-only, so flag it rather than claiming it is equivalent.

## Security considerations
- Sample data must be **fake**. No real names, IDs, PHI or account numbers.
- No raw identifiers in vector metadata. Use tokens (`patient_ref_token`, `customer_ref_token`).
- Never commit `.env`, DB data folders or container volumes.
- Postgres tenant isolation uses RLS with a **non-superuser** app role, because superusers bypass RLS.
- Container credentials (`dev`) are for local use only.

## Commit / PR guidelines
- Small commits with an imperative subject line, e.g. `Add qdrant store purge`.
- Re-run the affected notebook headless before committing.
- Update `docs/PLAN.md` or `SETUP.md` when a design decision or setup step changes.
