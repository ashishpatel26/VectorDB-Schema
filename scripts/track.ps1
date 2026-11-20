<#
.SYNOPSIS
  Live tracker for the per-DB notebooks. Refreshes every few seconds; Ctrl+C to stop.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\track.ps1
  powershell -ExecutionPolicy Bypass -File scripts\track.ps1 -Once
#>
param([int]$Seconds = 5, [switch]$Once)

$Root = Resolve-Path (Join-Path $PSScriptRoot '..')
$Expected = '01_pgvector', '02_qdrant', '03_weaviate', '04_milvus', '05_chroma', '06_lancedb', '99_compare'
$Sections = 14   # sections 0..13 like 01_pgvector

function Get-Row($name) {
    $nb = Join-Path $Root "notebooks\$name.ipynb"
    $db = ($name -split '_', 2)[1]
    $res = Join-Path $Root "data\results\$db.json"
    $row = [ordered]@{ Notebook = $name; Built = '-'; Sections = '-'; Executed = '-'; Errors = '-'; 'hit@1' = '-'; 'p50 ms' = '-'; Updated = '-'; Status = 'waiting' }
    if (-not (Test-Path $nb)) { return [pscustomobject]$row }
    try { $j = Get-Content $nb -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $row.Status = 'writing...'; return [pscustomobject]$row }
    $code = @($j.cells | Where-Object cell_type -eq 'code')
    $heads = @($j.cells | Where-Object { $_.cell_type -eq 'markdown' -and (($_.source -join '') -match '^## \d+\.') }).Count
    $ran = @($code | Where-Object { $_.execution_count }).Count
    $errs = @($code | ForEach-Object { $_.outputs } | Where-Object { $_.output_type -eq 'error' }).Count
    $row.Built = 'yes'
    $row.Sections = if ($name -eq '99_compare') { "$heads" } else { "$heads/$Sections" }
    $row.Executed = "$ran/$($code.Count) cells"
    $row.Errors = $errs
    $row.Updated = (Get-Item $nb).LastWriteTime.ToString('HH:mm:ss')
    if (Test-Path $res) {
        $m = Get-Content $res -Raw | ConvertFrom-Json
        $row.'hit@1' = $m.'hit@1'; $row.'p50 ms' = $m.latency_p50_ms
    }
    $row.Status = if ($errs -gt 0) { 'ERRORS' }
                  elseif ($ran -eq $code.Count -and $code.Count -gt 0) { 'DONE' }
                  elseif ($ran -gt 0) { 'partially run' }
                  else { 'built, not run yet' }
    [pscustomobject]$row
}

do {
    $rows = $Expected | ForEach-Object { Get-Row $_ }
    $done = @($rows | Where-Object Status -eq 'DONE').Count
    if (-not $Once) { Clear-Host }
    Write-Host ("VectorDB notebooks  {0}  |  {1}/{2} done" -f (Get-Date -Format 'HH:mm:ss'), $done, $Expected.Count) -ForegroundColor Cyan
    $bar = ('#' * ($done * 4)).PadRight($Expected.Count * 4, '.')
    Write-Host "[$bar]`n"
    $rows | Format-Table -AutoSize | Out-String | Write-Host
    $podman = podman ps --format '{{.Names}} {{.Status}}' 2>$null
    if ($podman) { Write-Host "containers:"; $podman | ForEach-Object { Write-Host "  $_" } }
    if (-not $Once) { Start-Sleep -Seconds $Seconds }
} while (-not $Once)
