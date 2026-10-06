# Builds the web UI (frontend\dist) that FastAPI serves. Needs Node.js on the DEVELOPMENT PC only; the operating PC needs no Node.
# ASCII only (Windows PowerShell 5.1 reads BOM-less files with the system codepage).
#
#   .\scripts\build-frontend.ps1              build (installs packages first if node_modules is missing or package-lock.json changed)
#   .\scripts\build-frontend.ps1 -Clean       delete node_modules and reinstall exactly from package-lock.json
#   .\scripts\build-frontend.ps1 -Test        also run type check + unit tests before building
#   .\scripts\build-frontend.ps1 -Package     after building, create the release zip (scripts\package.ps1)
param(
    [switch]$Clean,
    [switch]$Test,
    [switch]$Package,
    [string]$CondaEnvName = "",
    [string[]]$CondaRoots = @()
)
$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $AppRoot "frontend"
$LogFile = Join-Path $AppRoot "build.log"
try { Start-Transcript -Path $LogFile -Force | Out-Null } catch { $LogFile = $null }

function Fail([string]$msg) {
    [Console]::Error.WriteLine("[build] ERROR: " + $msg)
    if ($LogFile) { try { Stop-Transcript | Out-Null } catch { } ; [Console]::Error.WriteLine("[build] Full log: " + $LogFile) }
    exit 1
}
# Run an external command and stop with a clear message that names the failing step and its exit code.
function Step([string]$name, [scriptblock]$cmd) {
    Write-Output "[build] >> $name"
    $global:LASTEXITCODE = 0
    & $cmd
    $code = $LASTEXITCODE
    if ($code -ne 0) { Fail "step '$name' failed (exit code $code). Read the messages just above this line." }
}
trap { [Console]::Error.WriteLine("[build] UNEXPECTED ERROR: " + $_.Exception.Message); [Console]::Error.WriteLine($_.ScriptStackTrace); Fail "unexpected error (see above)" }

# --- 1) find Node.js: PATH first, then the conda env used for development ---------------------------------
function Find-NodeDir {
    $cmd = Get-Command node -ErrorAction SilentlyContinue
    if ($cmd) { return (Split-Path -Parent $cmd.Source) }
    $envName = $CondaEnvName
    if (-not $envName) { $envName = $env:WORKLOG_CONDA_ENV_NAME }
    if (-not $envName) {
        $cfg = Join-Path $AppRoot "config\config.json"
        if (Test-Path -LiteralPath $cfg) {
            try { $j = [System.IO.File]::ReadAllText($cfg, [System.Text.Encoding]::UTF8) | ConvertFrom-Json; if ($j.CONDA_ENV_NAME) { $envName = [string]$j.CONDA_ENV_NAME } } catch { }
        }
    }
    if (-not $envName) { $envName = "worklog" }
    $roots = New-Object System.Collections.Generic.List[string]
    foreach ($r in $CondaRoots) { if ($r) { $roots.Add($r) } }
    if ($roots.Count -eq 0) {
        if ($env:CONDA_EXE) { $roots.Add((Split-Path -Parent (Split-Path -Parent $env:CONDA_EXE))) }
        foreach ($n in @("miniconda3", "anaconda3", "miniforge3", "mambaforge")) {
            $roots.Add((Join-Path $env:USERPROFILE $n)); $roots.Add((Join-Path $env:ProgramData $n)); $roots.Add((Join-Path $env:LOCALAPPDATA $n))
        }
    }
    foreach ($root in ($roots | Select-Object -Unique)) {
        $dir = Join-Path $root "envs\$envName"
        if (Test-Path -LiteralPath (Join-Path $dir "node.exe")) { return $dir }
    }
    return $null
}

$nodeDir = Find-NodeDir
if (-not $nodeDir) {
    Fail ("Node.js was not found. Install Node.js 20+ (https://nodejs.org) or create the conda env: " +
          "conda create -n worklog --override-channels -c conda-forge python=3.12 nodejs=22")
}
$env:Path = "$nodeDir;$nodeDir\Scripts;" + $env:Path
$nodeVersion = (& node --version).Trim()
if ([int]($nodeVersion.TrimStart('v').Split('.')[0]) -lt 18) { Fail "Node.js 18+ is required (found $nodeVersion)." }
Write-Output "[build] Node $nodeVersion ($nodeDir)"

if (-not (Test-Path -LiteralPath (Join-Path $Frontend "package.json"))) { Fail "frontend\package.json not found: $Frontend" }
Push-Location $Frontend
try {
    # --- 2) install packages exactly from package-lock.json when needed ---------------------------------
    $nm = Join-Path $Frontend "node_modules"
    $lock = Join-Path $Frontend "package-lock.json"
    $stamp = Join-Path $nm ".worklog-lock-hash"
    $lockHash = if (Test-Path $lock) { (Get-FileHash $lock -Algorithm SHA256).Hash } else { "" }
    $needInstall = $Clean -or -not (Test-Path $nm) -or -not (Test-Path $stamp) -or ((Get-Content $stamp -Raw).Trim() -ne $lockHash)
    if ($Clean -and (Test-Path $nm)) {
        Write-Output "[build] -Clean: removing node_modules"
        Remove-Item -LiteralPath $nm -Recurse -Force
    }
    if ($needInstall) {
        Write-Output "[build] Installing packages ..."
        if (Test-Path $lock) { & npm ci --no-audit --no-fund } else { & npm install --no-audit --no-fund }
        if ($LASTEXITCODE -ne 0) {
            Fail ("npm install failed (exit code $LASTEXITCODE). Common causes: (1) a running dev server (npm run dev / vite) or editor is holding files in frontend\node_modules - close it and retry with -Clean; " +
                  "(2) no network access to the npm registry (needed the first time); (3) antivirus locking files.")
        }
        Set-Content -LiteralPath $stamp -Value $lockHash -Encoding ascii
    } else {
        Write-Output "[build] node_modules is up to date (use -Clean to reinstall)"
    }

    # --- 3) optional checks ---------------------------------------------------------------------------
    if ($Test) {
        Step "type check (tsc --noEmit)" { & npx tsc --noEmit }
        Step "unit tests (vitest)" { & npx vitest run }
    }

    # --- 4) build -------------------------------------------------------------------------------------
    # Run the two build stages separately so the failing one is named (npm run build = tsc --noEmit && vite build).
    if (-not $Test) { Step "type check (tsc --noEmit)" { & npx tsc --noEmit } }
    Step "bundle (vite build)" { & npx vite build }
} finally {
    Pop-Location
}

$index = Join-Path $Frontend "dist\index.html"
if (-not (Test-Path -LiteralPath $index)) { Fail "build finished but frontend\dist\index.html is missing" }
$size = [math]::Round(((Get-ChildItem (Join-Path $Frontend "dist") -Recurse -File | Measure-Object Length -Sum).Sum) / 1KB)
Write-Output "[build] OK: frontend\dist ($size KB). Restart the server (the launcher .bat) to serve the new build."

if ($Package) {
    Write-Output "[build] Creating release zip ..."
    & (Join-Path $PSScriptRoot "package.ps1")
    if ($LASTEXITCODE -ne 0) { Fail "packaging failed" }
}
if ($LogFile) { try { Stop-Transcript | Out-Null } catch { } }
exit 0
