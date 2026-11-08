# Copies what the API needs in production into apps/api (the only folder FastAPI Cloud uploads):
#   packs/*.json      -> apps/api/packs/      (zone packs, manifest, JSON Schema; not golden_cases.json)
#   data/seed/*.json  -> apps/api/data/seed/  (reference data served by /crops, /soils, ...)
#
# Run it after every pack rebuild (python -m pipeline.run_all) or seed change, then commit the copies:
#   powershell -ExecutionPolicy Bypass -File scripts\prepare_deploy.ps1
#   git add apps/api/packs apps/api/data/seed
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$api = Join-Path $repo "apps\api"

function Sync-JsonFiles([string]$from, [string]$to, [string[]]$exclude) {
    if (-not (Test-Path $from)) { throw "Source folder not found: $from" }
    New-Item -ItemType Directory -Force $to | Out-Null
    # Remove stale copies (only *.json inside the target folder, which lives in the repository).
    Get-ChildItem -Path $to -Filter *.json -File | Remove-Item -Force
    $files = Get-ChildItem -Path $from -Filter *.json -File | Where-Object { $exclude -notcontains $_.Name }
    foreach ($f in $files) { Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $to $f.Name) }
    Write-Host ("{0,-28} -> {1}  ({2} files)" -f $from.Replace("$repo\", ""), $to.Replace("$repo\", ""), $files.Count)
}

Sync-JsonFiles (Join-Path $repo "packs") (Join-Path $api "packs") @("golden_cases.json")
Sync-JsonFiles (Join-Path $repo "data\seed") (Join-Path $api "data\seed") @()

# Byte-for-byte check (the pack ETag is the sha256 of the file).
$bad = @()
foreach ($pair in @(@("packs", "packs"), @("data\seed", "data\seed"))) {
    foreach ($f in Get-ChildItem -Path (Join-Path $api $pair[1]) -Filter *.json -File) {
        $src = Join-Path (Join-Path $repo $pair[0]) $f.Name
        if ((Get-FileHash $src).Hash -ne (Get-FileHash $f.FullName).Hash) { $bad += $f.FullName }
    }
}
if ($bad.Count -gt 0) { throw "Copies differ from sources: $($bad -join ', ')" }
Write-Host "OK: copies identical to sources. Commit apps/api/packs and apps/api/data/seed."
