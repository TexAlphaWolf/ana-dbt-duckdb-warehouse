# The full measurement on your own computer, in Docker (no network, read-only root, no capabilities), from Windows
# PowerShell: the whole warehouse is built from raw files of growing size, and every mart is checked after each build.
# Usage: .\tools\run_full.ps1 [-Sizes 10000,100000,1000000] [-Repeat 5] [-Threads 4] [-Out results]
param(
    [string]$Sizes = "10000,100000,1000000",
    [int]$Repeat = 5,
    [int]$Threads = 4,
    [string]$Out = "results"
)
# Windows PowerShell 5.1 turns anything a program writes on stderr into an error under "Stop": docker and dbtwh print
# their progress there, so only the exit code is looked at.
$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$outFull = (Resolve-Path -LiteralPath $Out).Path

docker build -t dbtwh .
if ($LASTEXITCODE -ne 0) { Write-Host "docker build failed"; exit 1 }

# The files dbt reads and writes while it runs go in /tmp (memory), not in the shared folder, so the times measure dbt
# and DuckDB and not the file sharing between Windows and Docker; only the three result files go to $Out.
Write-Host "== bench (sizes $Sizes, $Repeat builds each, $Threads threads) =="
docker run --rm --read-only --tmpfs /tmp:rw,size=3g --cap-drop ALL --security-opt no-new-privileges --network none -v "${outFull}:/out" dbtwh bench --sizes $Sizes --repeat $Repeat --threads $Threads --out /out
if ($LASTEXITCODE -ne 0) { Write-Host "bench failed (exit code $LASTEXITCODE)"; exit 1 }
Write-Host "Done. Send me $Out\bench.json, $Out\bench.md and $Out\summary.png."
