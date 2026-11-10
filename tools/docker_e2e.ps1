# End to end inside the image, from Windows PowerShell: raw files are generated into a volume, dbt builds the warehouse,
# every mart is checked against the independent calculation, and a small benchmark is run and rebuilt from its JSON
# (read-only root, no capabilities, no network). Needs Docker Desktop.
# Usage: .\tools\docker_e2e.ps1 [-Image dbtwh]
param([string]$Image = "dbtwh")
$ErrorActionPreference = "Stop"

$id = Get-Random
$vol = "dbtwh-e2e-$id"
$secure = @("--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--network", "none", "-v", "${vol}:/data")

# Windows PowerShell 5.1 turns a program's message on stderr into an error under "Stop": the commands that print
# progress on stderr or are expected to fail run with errors not terminating, and only their exit code is looked at.
function Invoke-WhCode([int[]]$Allowed, [string[]]$WhArgs) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = docker run --rm @secure $Image @WhArgs 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($Allowed -notcontains $code) { throw "dbtwh $WhArgs exited with $code : $out" }
    ($out | Out-String)
}
function Invoke-Wh([string[]]$WhArgs) { Invoke-WhCode @(0) $WhArgs }
function Read-Volume($path) {
    $out = docker run --rm --entrypoint cat -v "${vol}:/data" $Image $path 2>$null
    if ($LASTEXITCODE -ne 0) { throw "cannot read $path" }
    ($out | Out-String)
}
function Assert-Contains($text, $needle) { if ($text -notmatch [regex]::Escape($needle)) { throw "expected '$needle' in: $text" } }

try {
    docker volume create $vol | Out-Null
    docker run --rm --user 0 -v "${vol}:/data" --entrypoint chown $Image 10001 /data
    if ($LASTEXITCODE -ne 0) { throw "could not prepare the volume" }

    Assert-Contains (Invoke-Wh @("generate", "--orders", "3000", "--seed", "1", "--out", "/data/raw")) "written: 5 parquet files and manifest.json in /data/raw"
    Assert-Contains (Read-Volume "/data/raw/manifest.json") '"orders": 3000'

    $build = Invoke-Wh @("build", "--raw", "/data/raw", "--db", "/data/wh.duckdb", "--workdir", "/data/work", "--threads", "2", "--quiet", "--docs")
    Assert-Contains $build "dbt build: 12 models, 49 data tests, 5 unit tests: 66 passed, 0 failed"
    Assert-Contains (Read-Volume "/data/work/target/static_index.html") "mart_cohort_retention"

    Assert-Contains (Invoke-Wh @("verify", "--raw", "/data/raw", "--db", "/data/wh.duckdb")) "31 of 31 checks match the independent calculation"

    Invoke-Wh @("bench", "--sizes", "500,1000", "--repeat", "1", "--threads", "2", "--out", "/data/bench") | Out-Null
    Assert-Contains (Read-Volume "/data/bench/bench.json") '"verified": true'
    $md = Read-Volume "/data/bench/bench.md"
    Invoke-Wh @("render", "/data/bench/bench.json", "-o", "/data/bench/again.md") | Out-Null
    if ((Read-Volume "/data/bench/again.md") -ne $md) { throw "the report rebuilt from the JSON is not identical" }

    Invoke-WhCode @(2) @("verify", "--raw", "/data/nope", "--db", "/data/wh.duckdb") | Out-Null
    Write-Host "docker end-to-end: OK"
}
finally {
    $ErrorActionPreference = "Continue"
    docker volume rm -f $vol 2>&1 | Out-Null
}
