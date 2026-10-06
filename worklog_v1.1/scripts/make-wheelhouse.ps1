# Run on a PC with internet access to prepare an offline wheelhouse for the operating PC.
# The wheelhouse must be built with the same Python minor version and CPU architecture as the target PC.
#   .\scripts\make-wheelhouse.ps1 -Python C:\Python312\python.exe -Out .\wheels
param([string]$Python = "python", [string]$Out = "")
$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $PSScriptRoot
if (-not $Out) { $Out = Join-Path $AppRoot "wheels" }
New-Item -ItemType Directory -Force $Out | Out-Null
& $Python -m pip download --disable-pip-version-check -r (Join-Path $AppRoot "backend\requirements.txt") -d $Out
if ($LASTEXITCODE -ne 0) { Write-Error "pip download failed"; exit 1 }
# pip itself: lets setup-env.ps1 install pip into an embedded Python offline
& $Python -m pip download --disable-pip-version-check pip -d $Out
if ($LASTEXITCODE -ne 0) { Write-Error "pip download (pip wheel) failed"; exit 1 }
Write-Output "Wheelhouse ready: $Out ($((Get-ChildItem $Out).Count) files). Copy it next to the program and run setup-venv.ps1 -WheelDir."
