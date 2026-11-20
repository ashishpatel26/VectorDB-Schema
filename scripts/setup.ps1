<#
.SYNOPSIS
  One-shot setup for the VectorDB-Schema project (Windows + Podman).

.DESCRIPTION
  Does SETUP.md steps 2-12 in one go:
    - checks uv + Podman (installs uv if missing)
    - adds Python deps per vector DB as optional extras and syncs .venv
    - registers the Jupyter kernel and downloads the embedding model
    - creates folders, .env, compose.yaml, .gitignore entries (never overwrites existing files)
    - starts pgvector, Qdrant, Weaviate (+ Milvus + Attu) in Podman and waits for health checks
    - verifies the embedded DBs (Chroma, LanceDB) import
  Safe to re-run: every step skips work that is already done.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SetWslMemory        # also raise WSL memory to 8 GB (restarts WSL)
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipMilvus
#>
param(
    [switch]$SkipMilvus,        # don't download/start Milvus + Attu
    [switch]$SkipContainers,    # Python side only
    [switch]$SetWslMemory,      # write memory=8GB to %UserProfile%\.wslconfig and restart WSL (stops ALL WSL distros)
    [string]$MilvusVersion = "" # e.g. v2.6.4; empty = latest GitHub release
)

$ErrorActionPreference = 'Stop'
$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
Set-Location $Root
$Results = [ordered]@{}

function Write-Step($msg) { Write-Host "`n=== $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  OK   $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "  WARN $msg" -ForegroundColor Yellow }

function Invoke-Native {
    # run an external command, throw if it fails (PowerShell doesn't do this by default)
    param([string]$Exe, [string[]]$ArgList)
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) { throw "'$Exe $($ArgList -join ' ')' failed with exit code $LASTEXITCODE" }
}

function Test-Native {
    # run an external command silently, return $true if exit code 0
    # (PS 5.1 + ErrorActionPreference=Stop turns redirected stderr into a terminating error, so relax it here)
    param([scriptblock]$Cmd)
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { & $Cmd *> $null } catch { }
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    return $ok
}

function Write-FileIfMissing {
    param([string]$Path, [string]$Content)
    if (Test-Path $Path) { Write-Ok "$Path exists, left unchanged"; return }
    # UTF-8 without BOM (PowerShell 5.1 Set-Content adds a BOM, which some YAML parsers dislike)
    [IO.File]::WriteAllText((Join-Path $Root $Path), $Content.Replace("`r`n", "`n"))
    Write-Ok "created $Path"
}

function Wait-Http {
    param([string]$Name, [string]$Url, [int]$TimeoutSec = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { Write-Ok "$Name healthy ($Url)"; $Results[$Name] = 'healthy'; return }
        } catch { }
        Start-Sleep -Seconds 3
    }
    Write-Warn2 "$Name not healthy after ${TimeoutSec}s. Check: podman logs <container>"
    $Results[$Name] = 'NOT healthy'
}

# ---------------------------------------------------------------- 1. tools
Write-Step "1. Tools"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warn2 "uv not found, installing"
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
Write-Ok ("uv " + (uv --version))
if (-not $SkipContainers) {
    if (-not (Get-Command podman -ErrorAction SilentlyContinue)) {
        throw "Podman not found. Install Podman Desktop / Podman for Windows first, or re-run with -SkipContainers."
    }
    Write-Ok ((podman --version) | Out-String).Trim()
}

# ---------------------------------------------------------------- 2. python deps
Write-Step "2. Python dependencies (optional extra per vector DB)"
$extras = [ordered]@{
    pg       = @('psycopg[binary]', 'pgvector')
    qdrant   = @('qdrant-client')
    weaviate = @('weaviate-client')
    milvus   = @('pymilvus')
    chroma   = @('chromadb')
    lancedb  = @('lancedb', 'pyarrow', 'pandas')
}
Invoke-Native uv @('add', 'pydantic', 'numpy', 'sentence-transformers', 'jupyter', 'ipykernel', 'pytest', 'python-dotenv')
foreach ($e in $extras.Keys) {
    Invoke-Native uv (@('add', '--optional', $e) + $extras[$e])
    Write-Ok "extra [$e]: $($extras[$e] -join ', ')"
}
Invoke-Native uv @('sync', '--all-extras')
$Results['python deps'] = 'installed'

# ---------------------------------------------------------------- 3. kernel + model
Write-Step "3. Jupyter kernel + embedding model"
Invoke-Native uv @('run', 'python', '-m', 'ipykernel', 'install', '--user', '--name', 'vectordb-schema', '--display-name', 'VectorDB Schema')
$dim = uv run python -c "from sentence_transformers import SentenceTransformer as S; print(S('BAAI/bge-small-en-v1.5').get_sentence_embedding_dimension())"
if ($LASTEXITCODE -ne 0 -or ($dim | Select-Object -Last 1).Trim() -ne '384') { throw "embedding model check failed: $dim" }
Write-Ok "bge-small-en-v1.5 loaded, dim=384"
$Results['embedding model'] = 'ok (384)'

# ---------------------------------------------------------------- 4. project files
Write-Step "4. Project files"
foreach ($d in 'sql', 'data', 'data\samples', 'data\results', 'docker\milvus', 'smoke', 'notebooks', 'tests') {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}
Write-Ok "folders ready"

Write-FileIfMissing '.env' @'
PG_DSN=postgresql://postgres:dev@localhost:5432/vectors
QDRANT_URL=http://localhost:6333
WEAVIATE_HOST=localhost
MILVUS_URI=http://localhost:19530
CHROMA_PATH=data/chroma
LANCEDB_PATH=data/lancedb
EMBED_MODEL=BAAI/bge-small-en-v1.5
EMBED_DIM=384
'@

Write-FileIfMissing 'compose.yaml' @'
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
'@

$ignore = @('.env', 'data/chroma/', 'data/lancedb/', 'data/results/', 'docker/milvus/volumes/', '.ipynb_checkpoints/')
$existing = if (Test-Path .gitignore) { Get-Content .gitignore } else { @() }
$missing = $ignore | Where-Object { $existing -notcontains $_ }
if ($missing) {
    Add-Content .gitignore -Value (@('', '# vectordb-schema') + $missing)
    Write-Ok ".gitignore: added $($missing -join ', ')"
} else { Write-Ok ".gitignore already complete" }

# ---------------------------------------------------------------- 5. embedded DBs
Write-Step "5. Embedded DBs (Chroma, LanceDB)"
foreach ($m in 'chromadb', 'lancedb') {
    $v = uv run python -c "import $m; print($m.__version__)"
    if ($LASTEXITCODE -eq 0) { Write-Ok "$m $v"; $Results[$m] = "ok ($v)" }
    else { Write-Warn2 "$m import failed"; $Results[$m] = 'import FAILED' }
}

if ($SkipContainers) { $Results['containers'] = 'skipped (-SkipContainers)' }
else {
    # ------------------------------------------------------------ 6. podman machine
    Write-Step "6. Podman machine"
    if ($SetWslMemory) {
        $cfg = Join-Path $env:USERPROFILE '.wslconfig'
        $txt = if (Test-Path $cfg) { Copy-Item $cfg "$cfg.bak" -Force; Get-Content $cfg -Raw } else { '' }
        if     ($txt -match '(?m)^\s*memory\s*=') { $txt = $txt -replace '(?m)^\s*memory\s*=.*$', 'memory=8GB' }
        elseif ($txt -match '(?m)^\[wsl2\]')      { $txt = $txt -replace '(?m)^\[wsl2\]', "[wsl2]`nmemory=8GB" }
        else                                      { $txt = $txt.TrimEnd() + "`n[wsl2]`nmemory=8GB`n" }
        [IO.File]::WriteAllText($cfg, $txt)
        Write-Ok ".wslconfig memory=8GB (backup: .wslconfig.bak). Restarting WSL..."
        podman machine stop | Out-Null
        wsl --shutdown
    }
    if (-not (Test-Native { podman info })) { Invoke-Native podman @('machine', 'start') }
    $memGB = [math]::Round([double](podman info --format '{{.Host.MemTotal}}') / 1GB, 1)
    Write-Ok "machine running, memory ${memGB} GB"
    if (-not $SkipMilvus -and $memGB -lt 7) {
        Write-Warn2 "Milvus needs ~8 GB, machine has ${memGB} GB. Skipping Milvus. Re-run with -SetWslMemory to fix."
        $SkipMilvus = $true
        $Results['milvus'] = "skipped (only ${memGB} GB RAM)"
    }

    # ------------------------------------------------------------ 7. pg, qdrant, weaviate
    Write-Step "7. pgvector, Qdrant, Weaviate"
    # one profile at a time: an image pull failure (e.g. Docker Hub rate limit) must not block the others
    $started = @{}
    foreach ($p in 'pg', 'qdrant', 'weaviate') {
        $started[$p] = Test-Native { podman compose --profile $p up -d }
        if (-not $started[$p]) {
            Write-Warn2 "$p failed to start (Docker Hub rate limit? run: podman login docker.io). Details: podman compose --profile $p up -d"
            $Results[$(if ($p -eq 'pg') { 'pgvector' } else { $p })] = 'NOT started'
        }
    }

    $deadline = (Get-Date).AddSeconds(90); $pgOk = $false
    while ($started['pg'] -and (Get-Date) -lt $deadline -and -not $pgOk) {
        if (Test-Native { podman exec vdb-pg pg_isready -U postgres }) { $pgOk = $true } else { Start-Sleep 3 }
    }
    if ($pgOk) {
        $ext = podman exec vdb-pg psql -U postgres -d vectors -tAc "CREATE EXTENSION IF NOT EXISTS vector; SELECT extversion FROM pg_extension WHERE extname='vector';"
        $ver = ($ext | Select-Object -Last 1).Trim()
        Write-Ok "pgvector healthy, extension $ver"; $Results['pgvector'] = "healthy (vector $ver)"
    } elseif ($started['pg']) { Write-Warn2 "pgvector not ready. Check: podman logs vdb-pg"; $Results['pgvector'] = 'NOT healthy' }

    if ($started['qdrant'])   { Wait-Http 'qdrant'   'http://localhost:6333/healthz' }
    if ($started['weaviate']) { Wait-Http 'weaviate' 'http://localhost:8080/v1/.well-known/ready' }

    # ------------------------------------------------------------ 8. milvus
    if (-not $SkipMilvus) {
        Write-Step "8. Milvus (+ Attu GUI)"
        $mc = 'docker\milvus\docker-compose.yml'
        if (-not (Test-Path $mc)) {
            $api = if ($MilvusVersion) { "tags/$MilvusVersion" } else { 'latest' }
            $rel = Invoke-RestMethod "https://api.github.com/repos/milvus-io/milvus/releases/$api" -Headers @{ 'User-Agent' = 'setup-script' }
            $MilvusVersion = $rel.tag_name
            # asset is .yml on 2.x and .yaml on 3.x
            $asset = $rel.assets | Where-Object { $_.name -match '^milvus-standalone-docker-compose\.ya?ml$' } | Select-Object -First 1
            if (-not $asset) { throw "no standalone compose asset in Milvus release $MilvusVersion" }
            $yml = (Invoke-WebRequest $asset.browser_download_url -UseBasicParsing).Content
            if ($yml -is [byte[]]) { $yml = [Text.Encoding]::UTF8.GetString($yml) }

            # Podman edit 1: fully-qualified image names (no short-name registry prompt)
            #   'image: x/y'                     (skip YAML aliases like 'image: *milvus-image')
            $yml = $yml -replace '(?m)^(\s*image:[ \t]*)(?![\w.-]+\.[\w-]+/|\*)(\S+)', '${1}docker.io/${2}'
            #   'x-milvus-image: &milvus-image x/y'  (3.x defines the image once as a YAML anchor)
            $yml = $yml -replace '(?m)^(\s*[\w-]+:[ \t]*&[\w-]+[ \t]+)(?![\w.-]+\.[\w-]+/)([\w.-]+/\S+)', '${1}docker.io/${2}'
            # Podman edit 2: ./volumes bind mounts -> named volumes (WSL file bridge is slow for etcd/minio)
            $names = [regex]::Matches($yml, '\$\{DOCKER_VOLUME_DIRECTORY:-\.\}/volumes/([\w-]+):') | ForEach-Object { "milvus_$($_.Groups[1].Value)" } | Select-Object -Unique
            $yml = $yml -replace '\$\{DOCKER_VOLUME_DIRECTORY:-\.\}/volumes/([\w-]+):', 'milvus_${1}:'
            if ($names) {
                if ($yml -match '(?m)^volumes:') { Write-Warn2 "compose already has top-level volumes:, add $($names -join ', ') by hand" }
                else { $yml = $yml.TrimEnd() + "`n`nvolumes:`n" + (($names | ForEach-Object { "  ${_}: {}" }) -join "`n") + "`n" }
            }
            [IO.File]::WriteAllText((Join-Path $Root $mc), $yml.Replace("`r`n", "`n"))
            Write-Ok "downloaded + patched Milvus $MilvusVersion compose -> $mc"
        } else { Write-Ok "$mc exists, left unchanged" }

        if (Test-Native { podman compose -f $mc up -d }) { Wait-Http 'milvus' 'http://localhost:9091/healthz' 180 }
        else { Write-Warn2 "Milvus failed to start (Docker Hub rate limit? run: podman login docker.io)"; $Results['milvus'] = 'NOT started' }

        podman run -d --replace --name vdb-attu -p 8001:3000 -e MILVUS_URL=host.containers.internal:19530 docker.io/zilliz/attu:latest | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Ok "Attu GUI -> http://localhost:8001"; $Results['attu'] = 'running :8001' }
        else { Write-Warn2 "Attu failed to start"; $Results['attu'] = 'FAILED' }
    } elseif (-not $Results.Contains('milvus')) { $Results['milvus'] = 'skipped (-SkipMilvus)' }
}

# ---------------------------------------------------------------- summary
Write-Step "Summary"
$Results.GetEnumerator() | ForEach-Object { [pscustomobject]@{ Component = $_.Key; Status = $_.Value } } | Format-Table -AutoSize
Write-Host "Next: run the smoke tests in SETUP.md (steps 6d-11f), then open notebooks/00_schema_and_gates.ipynb"
Write-Host "UIs: Qdrant http://localhost:6333/dashboard | Attu http://localhost:8001"
