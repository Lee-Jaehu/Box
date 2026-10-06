# Creates the .venv used as the last fallback by the launcher, then installs the pinned runtime packages.
# It never touches a base/conda environment. ASCII only (Windows PowerShell 5.1 reads BOM-less files with the system codepage).
#
#   .\scripts\setup-venv.ps1                         # online install from PyPI
#   .\scripts\setup-venv.ps1 -WheelDir .\wheels      # offline install from a wheelhouse (see make-wheelhouse.ps1)
#   .\scripts\setup-venv.ps1 -Python C:\Python312\python.exe -Dev   # also install test packages
param(
    [string]$Python = "",
    [string]$VenvDir = "",
    [string]$WheelDir = "",
    [switch]$Dev
)
$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $PSScriptRoot
if (-not $VenvDir) { $VenvDir = Join-Path $AppRoot ".venv" }

function Test-Python([string]$exe) {
    if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { return $false }
    & $exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

if (-not $Python) {
    foreach ($c in @("py", "python")) {
        $cmd = Get-Command $c -ErrorAction SilentlyContinue
        if ($cmd) {
            $p = if ($c -eq "py") { (& py -3 -c "import sys; print(sys.executable)" 2>$null) } else { $cmd.Source }
            if (Test-Python $p) { $Python = $p; break }
        }
    }
}
if (-not (Test-Python $Python)) {
    Write-Error "Python 3.11+ was not found. Pass -Python <path\to\python.exe> (Conda env python.exe also works)."
    exit 1
}
Write-Output "Using base Python: $Python"
if (-not (Test-Path -LiteralPath (Join-Path $VenvDir "Scripts\python.exe"))) {
    & $Python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Error "venv creation failed"; exit 1 }
}
$venvPy = Join-Path $VenvDir "Scripts\python.exe"
$req = Join-Path $AppRoot ($(if ($Dev) { "backend\requirements-dev.txt" } else { "backend\requirements.txt" }))
$args = @("-m", "pip", "install", "--disable-pip-version-check", "-r", $req)
if ($WheelDir) { $args += @("--no-index", "--find-links", $WheelDir) }
& $venvPy @args
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed"; exit 1 }
& $venvPy -c "import fastapi, uvicorn, sqlalchemy, alembic, pydantic, openpyxl, PIL, multipart, pptx, jsonschema, fontTools; print('OK: runtime packages import')"
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Output "venv ready: $venvPy"
