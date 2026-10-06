# Applies a new version of the program to an existing installation (test PC folder, operating folder) WITHOUT touching user data.
# Never copied / never deleted: data\, data_test\, backups\, config\config.json, .venv\, runtime\, wheels\, release\, node_modules\, *.sqlite3*, *.log
# Code folders (backend, frontend, scripts, docs, tests) are mirrored, so deleted/renamed files disappear from the target too.
# Before copying, the target database (if any) is copied to <target>\data\backups\pre-update-<time>\ as a safety net.
# ASCII only (Windows PowerShell 5.1 reads BOM-less files with the system codepage).
#
#   .\scripts\deploy.ps1 -Target "C:\Users\me\Desktop\tft_test"            # apply
#   .\scripts\deploy.ps1 -Target "C:\Users\me\Desktop\tft_test" -DryRun    # only list what would change
#   -Source <dir>  : program folder to copy from (default: this repository)
param(
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$Source = "",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
if (-not $Source) { $Source = Split-Path -Parent $PSScriptRoot }
function Fail([string]$m) { [Console]::Error.WriteLine("[deploy] ERROR: " + $m); exit 1 }

$Source = [System.IO.Path]::GetFullPath($Source).TrimEnd('\')
$Target = [System.IO.Path]::GetFullPath($Target).TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $Source "backend\run.py"))) { Fail "Source does not look like a Worklog program folder: $Source" }
if ($Source -ieq $Target) { Fail "Source and target are the same folder." }
if ($Target.StartsWith($Source + "\", [StringComparison]::OrdinalIgnoreCase) -or $Source.StartsWith($Target + "\", [StringComparison]::OrdinalIgnoreCase)) {
    Fail "Source and target must not be inside each other."
}
if (-not (Test-Path -LiteralPath (Join-Path $Source "frontend\dist\index.html"))) {
    Write-Output "[deploy] WARNING: frontend\dist is missing in the source. Run the build first (build .bat) or the UI will not update."
}

$isNew = -not (Test-Path -LiteralPath (Join-Path $Target "backend\run.py"))
if ($isNew -and (Test-Path -LiteralPath $Target) -and (Get-ChildItem -LiteralPath $Target -Force | Select-Object -First 1)) {
    Fail "Target folder exists, is not empty and is not a Worklog installation: $Target (refusing to write into it)"
}

# 1) the server of the target folder must not be running (files are in use and the database is open)
$running = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.Name -match 'python|cmd' -and $_.CommandLine.IndexOf((Join-Path $Target "backend\run.py"), [StringComparison]::OrdinalIgnoreCase) -ge 0
}
if ($running) { Fail ("The server of the target folder is running (pid " + (($running | ForEach-Object { $_.ProcessId }) -join ", ") + "). Close its window / stop it first.") }

# 2) safety copy of the database
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dbDir = Join-Path $Target "data\db"
if ((Test-Path -LiteralPath (Join-Path $dbDir "worklog.sqlite3")) -and -not $DryRun) {
    $safe = Join-Path $Target "data\backups\pre-update-$stamp"
    New-Item -ItemType Directory -Force $safe | Out-Null
    Get-ChildItem -LiteralPath $dbDir -Filter "worklog.sqlite3*" -File | Copy-Item -Destination $safe -Force
    Write-Output "[deploy] Database safety copy: $safe"
}

# 3) copy
$protectedDirs = @("data", "data_test", "backups", ".venv", "runtime", "wheels", "release", "node_modules", "__pycache__", ".pytest_cache", ".vite", ".claude")
$xd = @($protectedDirs | ForEach-Object { $_ })
$xf = @("config.json", "*.sqlite3", "*.sqlite3-wal", "*.sqlite3-shm", "*.log", "*.pyc")
$flags = @("/NJH", "/NJS", "/NP", "/NDL", "/R:2", "/W:1")
if ($DryRun) { $flags += "/L" }
$total = 0

function Sync-Dir([string]$rel, [bool]$mirror) {
    $src = Join-Path $Source $rel
    if (-not (Test-Path -LiteralPath $src)) { return }
    $dst = Join-Path $Target $rel
    $mode = if ($mirror) { "/MIR" } else { "/E" }
    $out = & robocopy $src $dst $mode /XD @xd /XF @xf @flags
    $code = $LASTEXITCODE
    if ($code -ge 8) { Fail "robocopy failed for '$rel' (exit code $code)" }
    $n = @($out | Where-Object { $_ -match '\S' }).Count
    $script:total += $n
    Write-Output ("[deploy] {0,-22} {1} file(s) {2}" -f $rel, $n, $(if ($DryRun) { "would change" } else { "updated" }))
}

# code folders: mirrored (the target gets exactly the new code). User data is excluded above, and none of these folders hold user data.
foreach ($d in @("backend", "frontend", "scripts", "docs", "tests")) { Sync-Dir $d $true }
# top-level files (launchers, README, ...) and the config EXAMPLE only; config\config.json is never touched
$out = & robocopy $Source $Target "*.bat" "*.md" "pytest.ini" ".gitignore" /LEV:1 @flags
if ($LASTEXITCODE -ge 8) { Fail "robocopy failed for top-level files (exit code $LASTEXITCODE)" }
$n = @($out | Where-Object { $_ -match '\S' }).Count; $total += $n
Write-Output ("[deploy] {0,-22} {1} file(s) {2}" -f "(top-level files)", $n, $(if ($DryRun) { "would change" } else { "updated" }))
New-Item -ItemType Directory -Force (Join-Path $Target "config") | Out-Null
$out = & robocopy (Join-Path $Source "config") (Join-Path $Target "config") "config.example.json" @flags
if ($LASTEXITCODE -ge 8) { Fail "robocopy failed for config example (exit code $LASTEXITCODE)" }

$kept = @("data", "data_test", "config\config.json", ".venv", "runtime") | Where-Object { Test-Path -LiteralPath (Join-Path $Target $_) }
Write-Output ("[deploy] Preserved (not touched): " + $(if ($kept) { $kept -join ", " } else { "(nothing existed yet)" }))
if ($DryRun) { Write-Output "[deploy] Dry run: nothing was changed." } else { Write-Output "[deploy] Done: $total file(s) updated. Start the server again." }
exit 0
