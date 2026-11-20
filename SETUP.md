# SETUP — Local Vector DB Environment (Windows 11 + Podman)

Follow the steps in order. Every step has **Do** (run it) and **Expect** (what success looks like). Don't move on until you see the expected result.

All commands are for **PowerShell**, run from the repo folder `d:\Projects\VectorDB-Schema`.

## Fast path — one script does steps 2–11

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1                 # everything
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SetWslMemory   # + raise WSL memory to 8 GB (restarts ALL WSL distros)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipMilvus     # without Milvus/Attu
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipContainers # Python side only
```

The script installs the Python dependencies (one optional extra per DB), registers the Jupyter kernel, downloads the embedding model, and creates `.env`, `compose.yaml` and `.gitignore` entries without overwriting existing files. It also starts and health-checks pgvector, Qdrant and Weaviate, downloads and patches the Milvus compose file for Podman, starts Milvus and Attu, and finishes with a status table. It is safe to re-run. Then do the **smoke tests** (6d, 7d, 8d, 9b, 10b, 11f) by hand.

The manual steps below do the same thing one by one and explain each part.

## Checklist

| Step | What                                                              | Time   |
| ---- | ----------------------------------------------------------------- | ------ |
| 1    | Install tools                                                     | 10 min |
| 2    | Get the Podman machine ready                                      | 5 min  |
| 3    | Create the Python environment                                     | 5 min  |
| 4    | Download the embedding model                                      | 2 min  |
| 5    | Create project files (`.env`, `compose.yaml`, `.gitignore`) | 5 min  |
| 6    | pgvector                                                          | 10 min |
| 7    | Qdrant                                                            | 5 min  |
| 8    | Weaviate                                                          | 5 min  |
| 9    | Chroma (no container)                                             | 3 min  |
| 10   | LanceDB (no container)                                            | 3 min  |
| 11   | Milvus (heaviest, do last)                                        | 15 min |
| 12   | Check all 6 at once                                               | 2 min  |
| 13   | Stop / reset                                                      | —     |

> Each DB step ends with a **smoke test**: create a throwaway index `smoke_healthcare`, insert 1 fake vector, run a filtered search, delete the index. It only proves the DB works. Real industry indexes come later in the notebooks ([docs/PLAN.md](docs/PLAN.md)).

---

## Step 1 — Install tools

**Do:** install anything missing.

| Tool             | Install                                                                                | Check                      |
| ---------------- | -------------------------------------------------------------------------------------- | -------------------------- |
| Python 3.12+     | `winget install Python.Python.3.12`                                                  | `python --version`       |
| uv               | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` | `uv --version`           |
| Podman           | already installed (5.8.x)                                                              | `podman version`         |
| Compose provider | already present (`docker-compose.exe`, which Podman calls for you)                   | `podman compose version` |
| Git              | `winget install Git.Git`                                                             | `git --version`          |

**Expect:** every **Check** command prints a version. `podman compose version` prints a banner saying it is calling the external compose provider. That is normal.

> If `podman compose` ever says no provider is found, run `uv tool install podman-compose`.

---

## Step 2 — Get the Podman machine ready

Podman runs containers inside a small Linux VM called the "machine", which uses WSL here.

**2a. Check the machine is running**

```powershell
podman machine list
```

**Expect:** `podman-machine-default` with `Currently running`. If not, run `podman machine start`.

**2b. Give it more memory** (Milvus needs about 8 GB, the others are fine with 4 GB)

WSL machines get their memory from `.wslconfig`, not from `podman machine set`. Create or edit `%UserProfile%\.wslconfig`:

```ini
[wsl2]
memory=8GB
processors=4
```

Then restart:

```powershell
podman machine stop
wsl --shutdown
podman machine start
```

**Expect:** `podman info --format "{{.Host.MemTotal}}"` prints about 8 GB in bytes (around `8000000000`).

**2c. Test a container**

```powershell
podman run --rm docker.io/library/hello-world
```

**Expect:** `Hello from Docker!`. The image is Docker's, but it runs fine in Podman.

> **Podman rule used in every step:** always write the full image name (`docker.io/...`, `cr.weaviate.io/...`). Short names like `qdrant/qdrant` can make Podman stop and ask which registry to use.

---

## Step 3 — Python environment

**Do:**

```powershell
cd d:\Projects\VectorDB-Schema
uv venv --python 3.12
.\.venv\Scripts\Activate.ps1
uv pip install pydantic numpy sentence-transformers jupyter ipykernel pytest python-dotenv
python -m ipykernel install --user --name vectordb-schema --display-name "VectorDB Schema"
```

**Expect:** the prompt starts with `(VectorDB-Schema)`, and `jupyter kernelspec list` shows `vectordb-schema`.

> If activation is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

---

## Step 4 — Embedding model

**Do:**

```powershell
python -c "from sentence_transformers import SentenceTransformer as S; m=S('BAAI/bge-small-en-v1.5'); print(m.get_sentence_embedding_dimension())"
```

**Expect:** `384`. The model downloads once (about 130 MB) into the Hugging Face cache. Every index in this project uses **384 dims**.

---

## Step 5 — Project files

**5a. Create folders**

```powershell
mkdir sql, data, docker\milvus, smoke
```

**5b. `.env`** (never commit it)

```ini
PG_DSN=postgresql://postgres:dev@localhost:5432/vectors
QDRANT_URL=http://localhost:6333
WEAVIATE_HOST=localhost
MILVUS_URI=http://localhost:19530
CHROMA_PATH=data/chroma
LANCEDB_PATH=data/lancedb
EMBED_MODEL=BAAI/bge-small-en-v1.5
EMBED_DIM=384
```

`dev` is a local-only password.

**5c. `.gitignore`**

```
.venv/
.env
data/chroma/
data/lancedb/
data/results/
docker/milvus/volumes/
.ipynb_checkpoints/
```

**5d. `compose.yaml`** (repo root). It covers pgvector, Qdrant and Weaviate, each behind its own profile so you start only what you need.

```yaml
services:
  pg:
    profiles: ["pg"]
    image: docker.io/pgvector/pgvector:pg17
    container_name: vdb-pg
    environment:
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: vectors
    ports: ["5432:5432"]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./sql:/docker-entrypoint-initdb.d   # *.sql runs only on first start (empty volume)

  qdrant:
    profiles: ["qdrant"]
    image: docker.io/qdrant/qdrant:latest
    container_name: vdb-qdrant
    ports: ["6333:6333", "6334:6334"]
    volumes: ["qdrantdata:/qdrant/storage"]

  weaviate:
    profiles: ["weaviate"]
    image: cr.weaviate.io/semitechnologies/weaviate:latest
    container_name: vdb-weaviate
    command: ["--host", "0.0.0.0", "--port", "8080", "--scheme", "http"]
    ports: ["8080:8080", "50051:50051"]
    environment:
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: "true"   # local dev only
      PERSISTENCE_DATA_PATH: /var/lib/weaviate
      DEFAULT_VECTORIZER_MODULE: none                   # we bring our own vectors
      ENABLE_MODULES: ""
      CLUSTER_HOSTNAME: node1
    volumes: ["weaviatedata:/var/lib/weaviate"]

volumes:
  pgdata: {}
  qdrantdata: {}
  weaviatedata: {}
```

**Expect:** `podman compose config` prints the file back without errors.

> Named volumes live inside the Podman machine, which makes them fast. Bind mounts from `D:\` go through WSL's file bridge, which is slow and has permission issues for databases. The only bind mount here is the read-only `./sql` folder.

**Port map**

| Service           | Ports                                        |
| ----------------- | -------------------------------------------- |
| pgvector          | 5432                                         |
| Qdrant            | 6333 (REST + dashboard), 6334 (gRPC)         |
| Weaviate          | 8080 (REST), 50051 (gRPC)                    |
| Milvus            | 19530 (gRPC), 9091 (health); MinIO 9000/9001 |
| Attu (Milvus GUI) | 8001                                         |

---

## Step 6 — pgvector (PostgreSQL)

**What:** Postgres plus the `vector` extension, running as a server. It is also this project's **system of record**.

**6a. Start**

```powershell
podman compose --profile pg up -d
```

**6b. Health check**

```powershell
podman exec vdb-pg pg_isready -U postgres
podman exec vdb-pg psql -U postgres -d vectors -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector';"
```

**Expect:** `accepting connections`, then a version of `0.8.x` or higher.

**6c. Python client**

```powershell
uv pip install "psycopg[binary]" pgvector
```

**6d. Smoke test.** Save as `smoke\smoke_pg.py`:

```python
import numpy as np, psycopg
from pgvector.psycopg import register_vector

with psycopg.connect("postgresql://postgres:dev@localhost:5432/vectors", autocommit=True) as conn:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    conn.execute("""CREATE TABLE smoke_healthcare (
        chunk_id text PRIMARY KEY, tenant_id text NOT NULL,
        allowed_groups text[] NOT NULL CHECK (cardinality(allowed_groups) > 0),
        embedding vector(384) NOT NULL)""")
    conn.execute("CREATE INDEX ON smoke_healthcare USING hnsw (embedding vector_cosine_ops)")
    v = np.full(384, 0.1, dtype=np.float32)
    conn.execute("INSERT INTO smoke_healthcare VALUES (%s, %s, %s, %s)", ("c1", "t1", ["g1"], v))
    rows = conn.execute(
        "SELECT chunk_id, embedding <=> %s AS dist FROM smoke_healthcare "
        "WHERE tenant_id = %s AND allowed_groups && %s ORDER BY dist LIMIT 3",
        (v, "t1", ["g1"])).fetchall()
    print(rows)
    conn.execute("DROP TABLE smoke_healthcare")
```

Run `python smoke\smoke_pg.py`.
**Expect:** `[('c1', 0.0)]`. The distance may print as a tiny number like `1e-08`.

**6e. GUI:** DBeaver or pgAdmin, connecting to `localhost:5432`, user `postgres`, password `dev`, database `vectors`.

**6f. Gotchas**

- `sql/*.sql` runs **only on the first start**. After editing those files, reset with `podman compose --profile pg down -v`.
- Superusers **bypass RLS**. Tenant-isolation tests need a separate app role (built later in the notebooks).
- If port 5432 is taken by a local Postgres, change it to `"5433:5432"` and update `.env`.

---

## Step 7 — Qdrant

**What:** a fast vector DB server with rich metadata (payload) filtering. It is this project's "advanced" pick.

**7a. Start**

```powershell
podman compose --profile qdrant up -d
```

**7b. Health check**

```powershell
curl.exe http://localhost:6333/healthz
```

**Expect:** `healthz check passed`.

**7c. Python client**

```powershell
uv pip install qdrant-client
```

**7d. Smoke test.** Save as `smoke\smoke_qdrant.py`:

```python
import uuid
from qdrant_client import QdrantClient, models

c = QdrantClient(url="http://localhost:6333")
name = "smoke_healthcare"
c.create_collection(name, vectors_config=models.VectorParams(size=384, distance=models.Distance.COSINE))
c.create_payload_index(name, "tenant_id",
    field_schema=models.KeywordIndexParams(type=models.KeywordIndexType.KEYWORD, is_tenant=True))
c.create_payload_index(name, "allowed_groups", field_schema=models.PayloadSchemaType.KEYWORD)

pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "c1"))          # deterministic id from chunk_id
c.upsert(name, points=[models.PointStruct(id=pid, vector=[0.1] * 384,
         payload={"chunk_id": "c1", "tenant_id": "t1", "allowed_groups": ["g1"]})])

flt = models.Filter(must=[
    models.FieldCondition(key="tenant_id", match=models.MatchValue(value="t1")),
    models.FieldCondition(key="allowed_groups", match=models.MatchAny(any=["g1"])),
])
print(c.query_points(name, query=[0.1] * 384, query_filter=flt, limit=3).points)
c.delete_collection(name)
```

Run `python smoke\smoke_qdrant.py`.
**Expect:** one point with `payload={'chunk_id': 'c1', ...}` and `score≈1.0`.

**7e. GUI:** http://localhost:6333/dashboard

**7f. Gotchas**

- Point IDs must be an int or a UUID, so derive one from `chunk_id` with `uuid5`.
- Create payload indexes **before** bulk loading.

---

## Step 8 — Weaviate

**What:** a vector DB server with **native multi-tenancy** (one shard per tenant) and built-in hybrid search.

**8a. Start**

```powershell
podman compose --profile weaviate up -d
```

**8b. Health check**

```powershell
curl.exe -i http://localhost:8080/v1/.well-known/ready
```

**Expect:** `HTTP/1.1 200 OK`.

**8c. Python client**

```powershell
uv pip install weaviate-client
```

**8d. Smoke test.** Save as `smoke\smoke_weaviate.py`:

```python
import weaviate
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.tenants import Tenant
from weaviate.classes.query import Filter

client = weaviate.connect_to_local()          # localhost:8080 + gRPC 50051
try:
    coll = client.collections.create(
        "SmokeHealthcare",
        vectorizer_config=Configure.Vectorizer.none(),   # newer clients: vector_config=Configure.Vectors.self_provided()
        multi_tenancy_config=Configure.multi_tenancy(enabled=True),
        properties=[
            Property(name="chunk_id", data_type=DataType.TEXT),
            Property(name="allowed_groups", data_type=DataType.TEXT_ARRAY),
        ],
    )
    coll.tenants.create([Tenant(name="t1")])
    t1 = coll.with_tenant("t1")
    t1.data.insert(properties={"chunk_id": "c1", "allowed_groups": ["g1"]}, vector=[0.1] * 384)
    res = t1.query.near_vector(near_vector=[0.1] * 384, limit=3,
                               filters=Filter.by_property("allowed_groups").contains_any(["g1"]))
    print([o.properties for o in res.objects])
    client.collections.delete("SmokeHealthcare")
finally:
    client.close()
```

Run `python smoke\smoke_weaviate.py`.
**Expect:** `[{'chunk_id': 'c1', 'allowed_groups': ['g1']}]`.

**8e. GUI:** none built in. Browse http://localhost:8080/v1/schema.

**8f. Gotchas**

- Collection names must start with a capital letter.
- With multi-tenancy on, **every** read and write goes through `with_tenant(...)`.
- If you get a deprecation error on `vectorizer_config`, switch to the `vector_config` line in the comment.

---

## Step 9 — Chroma (embedded, no container)

**What:** a lightweight vector store that saves to a local folder. Its isolation is the **weakest** (metadata filters only), so it's the dev baseline.

**9a. Install**

```powershell
uv pip install chromadb
```

**9b. Smoke test.** Save as `smoke\smoke_chroma.py`:

```python
import chromadb

client = chromadb.PersistentClient(path="data/chroma")
col = client.get_or_create_collection("smoke_healthcare", metadata={"hnsw:space": "cosine"})
# list metadata is limited -> store each ACL group as a bool flag
col.upsert(ids=["c1"], embeddings=[[0.1] * 384],
           metadatas=[{"tenant_id": "t1", "grp_g1": True}])
res = col.query(query_embeddings=[[0.1] * 384], n_results=3,
                where={"$and": [{"tenant_id": "t1"}, {"grp_g1": True}]})
print(res["ids"], res["distances"])
client.delete_collection("smoke_healthcare")
```

Run `python smoke\smoke_chroma.py`.
**Expect:** `[['c1']] [[0.0]]` (or a tiny number).

**9c. GUI:** none. Use `col.peek()` in a notebook.

**9d. Gotchas**

- `$and` and `$or` need at least 2 conditions each.
- The distance metric is fixed when the collection is created. Newer versions use `configuration={"hnsw": {"space": "cosine"}}`.
- Only one process should write to `data/chroma` at a time.

---

## Step 10 — LanceDB (embedded, no container)

**What:** a columnar vector DB that saves to a local folder, with a typed PyArrow schema and SQL-style pre-filters.

**10a. Install**

```powershell
uv pip install lancedb pyarrow pandas
```

**10b. Smoke test.** Save as `smoke\smoke_lancedb.py`:

```python
import lancedb, pyarrow as pa

db = lancedb.connect("data/lancedb")
schema = pa.schema([
    pa.field("chunk_id", pa.string()),
    pa.field("tenant_id", pa.string()),
    pa.field("allowed_groups", pa.list_(pa.string())),
    pa.field("vector", pa.list_(pa.float32(), 384)),     # fixed-size list = vector column
])
tbl = db.create_table("smoke_healthcare", schema=schema, mode="overwrite")
tbl.add([{"chunk_id": "c1", "tenant_id": "t1", "allowed_groups": ["g1"], "vector": [0.1] * 384}])
rows = (tbl.search([0.1] * 384)
           .metric("cosine")
           .where("tenant_id = 't1' AND array_has_any(allowed_groups, ['g1'])", prefilter=True)
           .limit(3).to_list())
print([r["chunk_id"] for r in rows])
db.drop_table("smoke_healthcare")
```

Run `python smoke\smoke_lancedb.py`.
**Expect:** `['c1']`.

**10c. GUI:** none. Use `tbl.to_pandas()` in a notebook.

**10d. Gotchas**

- If `array_has_any` is rejected, check the list functions in the LanceDB SQL filter docs for your version.
- Search is exact (brute-force) until you create a vector index, which is fine under ~10k rows.

---

## Step 11 — Milvus (heaviest, do last)

**What:** a large-scale vector DB. Standalone mode runs **3 containers**: etcd, minio and milvus. Milvus Lite (pip) does not support Windows, so it runs in Podman.

**11a. Download the official compose file.** Find the latest version at https://github.com/milvus-io/milvus/releases, then:

```powershell
curl.exe -L -o docker\milvus\docker-compose.yml https://github.com/milvus-io/milvus/releases/download/v<VERSION>/milvus-standalone-docker-compose.yaml
```

On 2.x releases the file ends in `.yml`; on 3.x it ends in `.yaml`. Check the release's asset list.
On 3.x the Milvus image is defined once at the top (`x-milvus-image: &milvus-image milvusdb/milvus:...`). Prefix **that** line, and leave `image: *milvus-image` as it is.

**11b. Make two Podman edits** in `docker\milvus\docker-compose.yml`:

1. **Full image names.** Prefix any image without a registry with `docker.io/`, for example `minio/minio:...` → `docker.io/minio/minio:...` and `milvusdb/milvus:...` → `docker.io/milvusdb/milvus:...`. Images already on `quay.io/...` are fine.
2. **Named volumes instead of `./volumes` bind mounts.** etcd and MinIO are slow or fail on the WSL file bridge. Replace each `${DOCKER_VOLUME_DIRECTORY:-.}/volumes/<x>:/<path>` with a named volume, then declare them at the bottom:

   ```yaml
       volumes:
         - milvus_etcd:/etcd          # etcd service
   #     - milvus_minio:/minio_data   # minio service
   #     - milvus_data:/var/lib/milvus  # standalone service
   ...
   volumes:
     milvus_etcd: {}
     milvus_minio: {}
     milvus_data: {}
   ```

   Keep each container path (the part after `:`) exactly as the original file has it.

**11c. Start**

```powershell
podman compose -f docker\milvus\docker-compose.yml up -d
podman ps
```

**Expect:** 3 containers (`milvus-etcd`, `milvus-minio`, `milvus-standalone`). Wait about 60 seconds the first time.

**11d. Health check**

```powershell
curl.exe http://localhost:9091/healthz
```

**Expect:** `OK`.

**11e. Python client**

```powershell
uv pip install pymilvus
```

**11f. Smoke test.** Save as `smoke\smoke_milvus.py`:

```python
from pymilvus import MilvusClient, DataType

c = MilvusClient(uri="http://localhost:19530")
name = "smoke_healthcare"

schema = MilvusClient.create_schema(auto_id=False)
schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64)
schema.add_field("tenant_id", DataType.VARCHAR, max_length=64, is_partition_key=True)
schema.add_field("allowed_groups", DataType.ARRAY, element_type=DataType.VARCHAR,
                 max_capacity=32, max_length=64)
schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=384)

idx = c.prepare_index_params()
idx.add_index("embedding", index_type="HNSW", metric_type="COSINE", params={"M": 16, "efConstruction": 200})
c.create_collection(name, schema=schema, index_params=idx, consistency_level="Strong")

c.insert(name, [{"chunk_id": "c1", "tenant_id": "t1", "allowed_groups": ["g1"], "embedding": [0.1] * 384}])
print(c.search(name, data=[[0.1] * 384], limit=3, output_fields=["chunk_id"],
               filter='tenant_id == "t1" and ARRAY_CONTAINS_ANY(allowed_groups, ["g1"])'))
c.drop_collection(name)
```

Run `python smoke\smoke_milvus.py`.
**Expect:** one hit with `'chunk_id': 'c1'` and `distance≈1.0`.

**11g. GUI (Attu)**

```powershell
podman run -d --name vdb-attu -p 8001:3000 -e MILVUS_URL=host.containers.internal:19530 docker.io/zilliz/attu:latest
```

Open http://localhost:8001. Podman uses `host.containers.internal`, not Docker's `host.docker.internal`.

**11h. Gotchas**

- Containers keep restarting? The machine has too little memory, so redo **Step 2b**.
- `consistency_level="Strong"` lets a search see a row right after insert. Fine for tests.

---

## Step 12 — Check all 6 at once

```powershell
podman compose --profile pg --profile qdrant --profile weaviate up -d
podman compose -f docker\milvus\docker-compose.yml up -d
Get-ChildItem smoke\smoke_*.py | ForEach-Object { "== $($_.Name)"; python $_.FullName }
```

**Expect:** each of the 6 scripts prints a single hit for `c1`. Setup is done. Next, start `notebooks/00_schema_and_gates.ipynb`.

---

## Step 13 — Stop / reset

| Goal                               | Command                                                                                 |
| ---------------------------------- | --------------------------------------------------------------------------------------- |
| Stop pg/Qdrant/Weaviate, keep data | `podman compose --profile pg --profile qdrant --profile weaviate down`                |
| Stop + **delete** their data | same command with `-v`                                                                |
| Stop Milvus                        | `podman compose -f docker\milvus\docker-compose.yml down` (add `-v` to delete data) |
| Remove Attu                        | `podman rm -f vdb-attu`                                                               |
| Reset Chroma / LanceDB             | delete `data\chroma\` / `data\lancedb\`                                             |
| Free machine memory                | `podman machine stop`                                                                 |

---

## Troubleshooting (Podman)

| Problem                                                 | Fix                                                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `short-name ... did not resolve` or a registry prompt | Use the full image name `docker.io/<org>/<image>:<tag>`                                   |
| `connection refused` on localhost                     | `podman machine list` shows not running → `podman machine start`                       |
| Port already in use                                     | `netstat -ano \| findstr :<port>`, then change the left side of `ports:`                 |
| DB container exits right away                           | `podman logs <container>`                                                                 |
| Slow or permission errors on volumes                    | Use named volumes, not `D:\` bind mounts                                                  |
| `curl` behaves oddly in PowerShell                    | Use `curl.exe`, not the `curl` alias                                                    |
| Pin versions                                            | Once everything works, replace each `:latest` with the version you got: `podman images` |
