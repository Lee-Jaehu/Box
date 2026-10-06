# Worklog Python selector: Conda -> embedded -> venv, first healthy candidate wins.
# Output (stdout, one line):  OK|<kind>|<python path>      exit 0
# On failure: reasons on stderr, exit 1. Never installs or modifies anything (no base env changes).
# Parameters exist so the order and fallbacks can be unit-tested (tests/test_launcher.py).
param(
    [string]$AppRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ConfigFile = "",
    [string]$CondaEnvName = "",
    [string[]]$CondaRoots = @(),
    [string]$EmbeddedPython = "",
    [string]$VenvPython = "",
    [string]$Probe = "import sys, fastapi, uvicorn, sqlalchemy, alembic, pydantic, openpyxl, PIL, multipart; assert sys.version_info >= (3, 11)"
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)

# --- config (config/config.json, UTF-8 with or without BOM) -------------------------------------
if (-not $ConfigFile) { $ConfigFile = Join-Path $AppRoot "config\config.json" }
$cfg = @{}
if (Test-Path -LiteralPath $ConfigFile) {
    $raw = [System.IO.File]::ReadAllText($ConfigFile, [System.Text.Encoding]::UTF8)
    ($raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $cfg[$_.Name.ToUpper()] = $_.Value }
}
function Pick([string]$explicit, [string]$envName, [string]$cfgKey, [string]$default) {
    if ($explicit) { return $explicit }
    $e = [Environment]::GetEnvironmentVariable($envName)
    if ($e) { return $e }
    if ($cfg.ContainsKey($cfgKey) -and $cfg[$cfgKey]) { return [string]$cfg[$cfgKey] }
    return $default
}
function Resolve-AppPath([string]$p) {
    if ([System.IO.Path]::IsPathRooted($p)) { return $p }
    return (Join-Path $AppRoot $p)
}

$envName  = Pick $CondaEnvName "WORKLOG_CONDA_ENV_NAME" "CONDA_ENV_NAME" "worklog"
$embedded = Resolve-AppPath (Pick $EmbeddedPython "WORKLOG_EMBEDDED_PYTHON_PATH" "EMBEDDED_PYTHON_PATH" "runtime\python\python.exe")
$venv     = Resolve-AppPath (Pick $VenvPython "WORKLOG_VENV_PYTHON_PATH" "VENV_PYTHON_PATH" ".venv\Scripts\python.exe")

# --- conda roots: explicit > CONDA_EXE > common install locations --------------------------------
$roots = New-Object System.Collections.Generic.List[string]
foreach ($r in $CondaRoots) { if ($r) { $roots.Add($r) } }
if ($roots.Count -eq 0) {
    if ($env:CONDA_EXE) { $roots.Add((Split-Path -Parent (Split-Path -Parent $env:CONDA_EXE))) }
    foreach ($n in @("miniconda3", "anaconda3", "miniforge3", "mambaforge")) {
        $roots.Add((Join-Path $env:USERPROFILE $n))
        $roots.Add((Join-Path $env:ProgramData $n))
        $roots.Add((Join-Path $env:LOCALAPPDATA $n))
    }
}

$candidates = New-Object System.Collections.Generic.List[object]
$condaPy = $null
foreach ($root in ($roots | Select-Object -Unique)) {
    $p = Join-Path $root "envs\$envName\python.exe"
    if (Test-Path -LiteralPath $p) { $condaPy = $p; break }
}
if (-not $condaPy -and $CondaRoots.Count -eq 0 -and $env:USERPROFILE) {
    # conda creates envs here when the install folder (e.g. C:\ProgramData\miniconda3) is not writable for the user
    $p = Join-Path $env:USERPROFILE ".conda\envs\$envName\python.exe"
    if (Test-Path -LiteralPath $p) { $condaPy = $p }
}
if ($condaPy) { $candidates.Add(@{ Kind = "conda"; Path = $condaPy }) }
else { $candidates.Add(@{ Kind = "conda"; Path = "(conda env '$envName' not found under: $(($roots | Select-Object -Unique) -join '; '))"; Missing = $true }) }
$candidates.Add(@{ Kind = "embedded"; Path = $embedded })
$candidates.Add(@{ Kind = "venv"; Path = $venv })

$tried = @()
foreach ($c in $candidates) {
    if ($c.Missing) { $tried += "[$($c.Kind)] $($c.Path)"; continue }
    if (-not (Test-Path -LiteralPath $c.Path)) { $tried += "[$($c.Kind)] not found: $($c.Path)"; continue }
    try {
        $out = & $c.Path -c $Probe 2>&1
        if ($LASTEXITCODE -ne 0) {
            $last = ($out | Select-Object -Last 1)
            $tried += "[$($c.Kind)] unusable (required packages/version missing): $($c.Path) :: $last"
            continue
        }
    } catch {
        $tried += "[$($c.Kind)] cannot run: $($c.Path) :: $($_.Exception.Message)"
        continue
    }
    Write-Output ("OK|{0}|{1}" -f $c.Kind, $c.Path)
    exit 0
}
[Console]::Error.WriteLine("No usable Python environment was found. Tried in order (Conda -> embedded -> venv):")
foreach ($t in $tried) { [Console]::Error.WriteLine("  " + $t) }
exit 1
