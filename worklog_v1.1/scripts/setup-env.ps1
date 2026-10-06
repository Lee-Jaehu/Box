# Worklog first-time environment setup. Same order as the launcher (select-python.ps1): Conda -> embedded -> venv.
# It stops at the first option that ends with a working environment (all runtime packages importable).
# Safety: never installs into or modifies the conda *base* environment, never accepts Anaconda Terms of Service
# (conda-forge only, --override-channels), never changes PATH, registry, firewall or services.
# ASCII only (Windows PowerShell 5.1 reads BOM-less files with the system codepage).
#
#   .\scripts\setup-env.ps1                    # auto: conda, then embedded, then venv
#   .\scripts\setup-env.ps1 -Only venv         # try just one option (conda | embedded | venv)
#   .\scripts\setup-env.ps1 -WheelDir .\wheels # offline packages (pip --no-index); a "wheels" folder next to the program is used automatically
#   .\scripts\setup-env.ps1 -Dev               # development PC: test packages too (+ Node.js 22 in the conda env)
#   .\scripts\setup-env.ps1 -DryRun            # print the plan only, change nothing
# Output: progress lines, then "RESULT|<kind>|<python path>" (exit 0) or "RESULT|FAILED" (exit 1).
param(
    [ValidateSet("auto", "conda", "embedded", "venv")][string]$Only = "auto",
    [string]$AppRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$WheelDir = "",
    [switch]$Dev,
    [switch]$DryRun,
    [string]$ConfigFile = "",
    [string]$CondaEnvName = "",
    [string[]]$CondaRoots = @(),
    [string]$EmbeddedPython = "",
    [string]$VenvPython = "",
    [string]$BasePython = ""
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$PythonVersion = "3.12"
$NodeVersion = "22"
$FullProbe = "import sys, fastapi, uvicorn, sqlalchemy, alembic, pydantic, openpyxl, PIL, multipart, pptx, jsonschema, fontTools; assert sys.version_info >= (3, 11); print(sys.version.split()[0])"

function Say([string]$m) { Write-Host "[setup] $m" }  # Write-Host: messages must not become function return values
function Plan([string]$kind, [string]$m) { Write-Host "PLAN|$kind|$m" }

# --- config (same keys and precedence as select-python.ps1) --------------------------------------
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
function Resolve-AppPath([string]$p) { if ([System.IO.Path]::IsPathRooted($p)) { return $p } return (Join-Path $AppRoot $p) }

$envName  = Pick $CondaEnvName "WORKLOG_CONDA_ENV_NAME" "CONDA_ENV_NAME" "worklog"
$embedded = Resolve-AppPath (Pick $EmbeddedPython "WORKLOG_EMBEDDED_PYTHON_PATH" "EMBEDDED_PYTHON_PATH" "runtime\python\python.exe")
$venvPy   = Resolve-AppPath (Pick $VenvPython "WORKLOG_VENV_PYTHON_PATH" "VENV_PYTHON_PATH" ".venv\Scripts\python.exe")
$venvDir  = Split-Path -Parent (Split-Path -Parent $venvPy)
$req      = Join-Path $AppRoot ($(if ($Dev) { "backend\requirements-dev.txt" } else { "backend\requirements.txt" }))
if (-not (Test-Path -LiteralPath $req)) { Say "requirements file not found: $req"; Write-Host "RESULT|FAILED"; exit 1 }

if (-not $WheelDir) {
    $auto = Join-Path $AppRoot "wheels"
    if ((Test-Path -LiteralPath $auto) -and (Get-ChildItem -LiteralPath $auto -Filter *.whl -ErrorAction SilentlyContinue)) { $WheelDir = $auto }
}
if ($WheelDir) { $WheelDir = (Resolve-Path -LiteralPath $WheelDir).Path; Say "offline package folder: $WheelDir (pip --no-index)" }
else { Say "packages will be downloaded from PyPI (internet or proxy needed; set HTTPS_PROXY if your network requires it)" }

function Invoke-Native([string]$exe, [string[]]$argv) {
    # Native tools write progress to stderr; with ErrorActionPreference=Stop that would abort, so relax it here.
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $exe @argv 2>&1 | ForEach-Object { Write-Host "    $_" }; return [int]$LASTEXITCODE } finally { $ErrorActionPreference = $old }
}
function Test-Full([string]$py) {
    if (-not $py -or -not (Test-Path -LiteralPath $py)) { return $null }
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { $v = & $py -c $FullProbe 2>$null; if ($LASTEXITCODE -eq 0) { return ($v | Select-Object -Last 1) } return $null } finally { $ErrorActionPreference = $old }
}
function Test-Version([string]$py) {
    if (-not $py -or -not (Test-Path -LiteralPath $py)) { return $false }
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $py -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null | Out-Null; return ($LASTEXITCODE -eq 0) } finally { $ErrorActionPreference = $old }
}
function Install-Requirements([string]$py) {
    $argv = @("-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", "-r", $req)
    if ($WheelDir) { $argv += @("--no-index", "--find-links", $WheelDir) }
    Say "installing packages: $py -m pip install -r $(Split-Path -Leaf $req)"
    return ((Invoke-Native $py $argv) -eq 0)
}
function Finish([string]$kind, [string]$py) {
    $ver = Test-Full $py
    if (-not $ver) { Say "[$kind] packages are still not importable with $py"; return $false }
    Say "[$kind] ready: Python $ver at $py"
    Write-Host "RESULT|$kind|$py"
    return $true
}

# --- conda ---------------------------------------------------------------------------------------
function Get-CondaRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    foreach ($r in $CondaRoots) { if ($r) { $roots.Add($r) } }
    if ($roots.Count -eq 0) {
        if ($env:CONDA_EXE) { $roots.Add((Split-Path -Parent (Split-Path -Parent $env:CONDA_EXE))) }
        foreach ($n in @("miniconda3", "anaconda3", "miniforge3", "mambaforge")) {
            foreach ($b in @($env:USERPROFILE, $env:ProgramData, $env:LOCALAPPDATA)) { if ($b) { $roots.Add((Join-Path $b $n)) } }
        }
    }
    return ($roots | Select-Object -Unique)
}
function Find-CondaEnvPython([string]$condaExe, [string[]]$roots) {
    foreach ($root in $roots) { $p = Join-Path $root "envs\$envName\python.exe"; if (Test-Path -LiteralPath $p) { return $p } }
    if ($CondaRoots.Count -eq 0 -and $env:USERPROFILE) {
        $p = Join-Path $env:USERPROFILE ".conda\envs\$envName\python.exe"   # where conda puts envs when the install folder is read-only
        if (Test-Path -LiteralPath $p) { return $p }
    }
    if ($condaExe -and -not $DryRun) {
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        try {
            $json = (& $condaExe env list --json 2>$null) -join "`n"
            if ($LASTEXITCODE -eq 0 -and $json) {
                foreach ($e in ($json | ConvertFrom-Json).envs) {
                    if ((Split-Path -Leaf $e) -ieq $envName -and (Test-Path -LiteralPath (Join-Path $e "python.exe"))) { return (Join-Path $e "python.exe") }
                }
            }
        } catch { } finally { $ErrorActionPreference = $old }
    }
    return $null
}
function Setup-Conda {
    $roots = Get-CondaRoots
    $condaExe = $null
    foreach ($root in $roots) {
        foreach ($c in @("Scripts\conda.exe", "condabin\conda.bat")) {
            $p = Join-Path $root $c
            if (Test-Path -LiteralPath $p) { $condaExe = $p; break }
        }
        if ($condaExe) { break }
    }
    if (-not $condaExe) { Say "[conda] skipped: no conda installation found (looked in: $($roots -join '; '))"; return $false }
    Say "[conda] conda found: $condaExe"
    $py = Find-CondaEnvPython $condaExe $roots
    if ($DryRun) {
        if ($py) { Plan "conda" "env '$envName' exists ($py): install/update packages from $(Split-Path -Leaf $req)" }
        else { Plan "conda" "create env '$envName' (python=$PythonVersion$(if ($Dev) { ", nodejs=$NodeVersion" })) from conda-forge, then install packages" }
        return $true
    }
    if (-not $py) {
        $pkgs = @("python=$PythonVersion"); if ($Dev) { $pkgs += "nodejs=$NodeVersion" }
        Say "[conda] creating env '$envName' from conda-forge ($($pkgs -join ', ')). The base env is not changed."
        $rc = Invoke-Native $condaExe (@("create", "-y", "-n", $envName, "--override-channels", "-c", "conda-forge") + $pkgs)
        if ($rc -ne 0) { Say "[conda] env creation failed (offline? proxy? see messages above) -> next option"; return $false }
        $py = Find-CondaEnvPython $condaExe $roots
        if (-not $py) { Say "[conda] env was created but its python.exe was not found -> next option"; return $false }
    } elseif ($Dev -and -not (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $py) "node.exe"))) {
        Say "[conda] adding Node.js $NodeVersion to env '$envName' (development build only)"
        $rc = Invoke-Native $condaExe @("install", "-y", "-n", $envName, "--override-channels", "-c", "conda-forge", "nodejs=$NodeVersion")
        if ($rc -ne 0) { Say "[conda] Node.js install failed (the server still works; only the UI build needs Node.js)" }
    }
    if (-not (Test-Version $py)) { Say "[conda] $py is older than Python 3.11 -> next option"; return $false }
    if (-not (Install-Requirements $py)) { Say "[conda] package install failed -> next option"; return $false }
    return (Finish "conda" $py)
}

# --- embedded (Windows embeddable package unpacked to runtime\python) ----------------------------
function Setup-Embedded {
    if (-not (Test-Path -LiteralPath $embedded)) {
        Say "[embedded] skipped: $embedded not found (unpack the 'Windows embeddable package (64-bit)' of Python 3.11+ there to use this option)"
        return $false
    }
    if (-not (Test-Version $embedded)) { Say "[embedded] $embedded does not run or is older than 3.11 -> next option"; return $false }
    $dir = Split-Path -Parent $embedded
    $pth = Get-ChildItem -LiteralPath $dir -Filter "python3*._pth" -ErrorAction SilentlyContinue | Select-Object -First 1
    $needSite = $pth -and ((Get-Content -LiteralPath $pth.FullName) -match '^\s*#\s*import site')
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $embedded -m pip --version 2>$null | Out-Null; $hasPip = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $old
    if ($DryRun) {
        $steps = @()
        if ($needSite) { $steps += "enable 'import site' in $($pth.Name)" }
        if (-not $hasPip) { $steps += $(if ($WheelDir) { "install pip from the wheel folder" } else { "download get-pip.py from bootstrap.pypa.io and install pip" }) }
        $steps += "install packages from $(Split-Path -Leaf $req)"
        Plan "embedded" ($steps -join "; ")
        return $true
    }
    if ($needSite) {
        $bak = "$($pth.FullName).orig"
        if (-not (Test-Path -LiteralPath $bak)) { Copy-Item -LiteralPath $pth.FullName -Destination $bak }
        $lines = Get-Content -LiteralPath $pth.FullName | ForEach-Object { $_ -replace '^\s*#\s*import site', 'import site' }
        [System.IO.File]::WriteAllLines($pth.FullName, [string[]]$lines, [System.Text.ASCIIEncoding]::new())
        Say "[embedded] enabled 'import site' in $($pth.Name) (original kept as $($pth.Name).orig) so installed packages can be imported"
    }
    if (-not $hasPip) {
        if ($WheelDir) {
            $whl = Get-ChildItem -LiteralPath $WheelDir -Filter "pip-*.whl" | Sort-Object Name | Select-Object -Last 1
            if (-not $whl) { Say "[embedded] no pip-*.whl in $WheelDir (make-wheelhouse.ps1 adds it) -> next option"; return $false }
            $rc = Invoke-Native $embedded @((Join-Path $whl.FullName "pip"), "install", "--no-index", "--find-links", $WheelDir, "--no-warn-script-location", "pip")
        } else {
            $getPip = Join-Path $dir "get-pip.py"
            Say "[embedded] pip is missing: downloading https://bootstrap.pypa.io/get-pip.py"
            try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip }
            catch { Say "[embedded] download failed ($($_.Exception.Message)) -> next option"; return $false }
            $rc = Invoke-Native $embedded @($getPip, "--no-warn-script-location")
        }
        if ($rc -ne 0) { Say "[embedded] pip install failed -> next option"; return $false }
    }
    if (-not (Install-Requirements $embedded)) { Say "[embedded] package install failed -> next option"; return $false }
    return (Finish "embedded" $embedded)
}

# --- venv (.venv, created from any Python 3.11+; the base interpreter is only used to create it) --
function Find-BasePython {
    if ($BasePython) { if (Test-Version $BasePython) { return $BasePython } Say "[venv] -BasePython $BasePython is not Python 3.11+"; return $null }
    $cands = New-Object System.Collections.Generic.List[string]
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"; $p = & py -3 -c "import sys; print(sys.executable)" 2>$null; $ErrorActionPreference = $old; if ($p) { $cands.Add([string]$p) } }
    foreach ($c in @(Get-Command python -All -ErrorAction SilentlyContinue)) { if ($c.Source -notmatch 'WindowsApps') { $cands.Add($c.Source) } }  # skip the Microsoft Store stub
    foreach ($root in (Get-CondaRoots)) { $cands.Add((Join-Path $root "python.exe")) }  # conda base only *runs* 'python -m venv'; nothing is installed into it
    foreach ($c in ($cands | Select-Object -Unique)) { if (Test-Version $c) { return $c } }
    return $null
}
function Setup-Venv {
    $base = Find-BasePython
    if (-not $base) { Say "[venv] skipped: no Python 3.11+ found (install Python from python.org or pass -BasePython <path>)"; return $false }
    if ($DryRun) {
        $what = $(if (Test-Path -LiteralPath $venvPy) { "venv exists ($venvPy)" } else { "create $venvDir with $base" })
        Plan "venv" "$what; install packages from $(Split-Path -Leaf $req)"
        return $true
    }
    if (-not (Test-Path -LiteralPath $venvPy)) {
        Say "[venv] creating $venvDir with $base"
        $rc = Invoke-Native $base @("-m", "venv", $venvDir)
        if ($rc -ne 0 -or -not (Test-Path -LiteralPath $venvPy)) { Say "[venv] venv creation failed"; return $false }
    }
    if (-not (Install-Requirements $venvPy)) { Say "[venv] package install failed"; return $false }
    return (Finish "venv" $venvPy)
}

# --- run -----------------------------------------------------------------------------------------
$order = $(if ($Only -eq "auto") { @("conda", "embedded", "venv") } else { @($Only) })
Say "app folder: $AppRoot"
Say "order: $($order -join ' -> ')$(if ($DryRun) { '  (dry run: nothing will be changed)' })"
foreach ($kind in $order) {
    $ok = switch ($kind) { "conda" { Setup-Conda } "embedded" { Setup-Embedded } "venv" { Setup-Venv } }
    if ($ok -eq $true) {
        if ($DryRun) { Write-Host "RESULT|$kind|(dry run)"; exit 0 }
        # show what the launcher will actually pick (an earlier, broken candidate is skipped by the launcher too)
        $sel = Join-Path $PSScriptRoot "select-python.ps1"
        if (Test-Path -LiteralPath $sel) {
            $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            $pick = & powershell -NoProfile -ExecutionPolicy Bypass -File $sel -AppRoot $AppRoot 2>$null | Select-Object -Last 1
            $ErrorActionPreference = $old
            if ($pick) { Say "launcher (run .bat) will use: $($pick -replace '^OK\|', '' -replace '\|', ' ')" }
        }
        exit 0
    }
}
Say "no option could be set up. Read the reasons above (offline? proxy? no Python?)."
Write-Host "RESULT|FAILED"
exit 1
