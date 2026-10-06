# Builds a release zip that can be unzipped OVER an existing installation without touching user data or settings.
# Included: backend code, built frontend (frontend\dist), scripts, launcher, config example, docs, notices.
# Never included: data\, config\config.json, .venv, runtime\ (embedded Python), node_modules, caches, tests.
#   npm run build   (in frontend, on the development PC)   then   .\scripts\package.ps1
#   .\scripts\package.ps1 -Name worklog_v1   -> release\worklog_v1.zip  (default name: worklog-<Version>-<yyyyMMdd>)
param([string]$OutDir = "", [string]$Version = "0.1.0", [string]$Name = "")
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$AppRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $AppRoot "release" }
if (-not (Test-Path (Join-Path $AppRoot "frontend\dist\index.html"))) {
    Write-Error "frontend\dist is missing. Run 'npm run build' in the frontend folder on the development PC first."
    exit 1
}
$stamp = Get-Date -Format "yyyyMMdd"
$name = if ($Name) { $Name } else { "worklog-$Version-$stamp" }
$stage = Join-Path ([IO.Path]::GetTempPath()) "$name-stage-$([guid]::NewGuid().ToString('N').Substring(0,6))"
$root = Join-Path $stage "worklog"
New-Item -ItemType Directory -Force $root | Out-Null

function Copy-Tree([string]$rel, [string[]]$excludeDirs = @("__pycache__", ".pytest_cache", "node_modules")) {
    $src = Join-Path $AppRoot $rel
    $dst = Join-Path $root $rel
    New-Item -ItemType Directory -Force $dst | Out-Null
    Get-ChildItem -LiteralPath $src -Force | ForEach-Object {
        if ($_.PSIsContainer) {
            if ($excludeDirs -notcontains $_.Name) { Copy-Tree (Join-Path $rel $_.Name) $excludeDirs }
        } elseif ($_.Extension -notin @(".pyc", ".pyo", ".sqlite3", ".log")) {
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Force
        }
    }
}
Copy-Tree "backend"
Copy-Tree "frontend\dist"
Copy-Tree "scripts"
Copy-Tree "docs"
New-Item -ItemType Directory -Force (Join-Path $root "config") | Out-Null
Copy-Item (Join-Path $AppRoot "config\config.example.json") (Join-Path $root "config") -Force
foreach ($f in @("README.md", "THIRD_PARTY_NOTICES.md")) {
    if (Test-Path (Join-Path $AppRoot $f)) { Copy-Item (Join-Path $AppRoot $f) $root -Force }
}
Copy-Item -LiteralPath (Join-Path $AppRoot "$([char]0xC2E4)$([char]0xD589).bat") $root -Force   # launcher (Korean file name)
Copy-Item -LiteralPath (Join-Path $AppRoot "$([char]0xCD08)$([char]0xAE30)$([char]0xC124)$([char]0xC815).bat") $root -Force   # first-time setup (Korean file name)
Copy-Item -LiteralPath (Join-Path $AppRoot "$([char]0xD14C)$([char]0xC2A4)$([char]0xD2B8)$([char]0xC2E4)$([char]0xD589).bat") $root -Force   # test-server launcher (separate port and data_test)
# Not included on purpose: the build launcher (needs Node.js and frontend sources) and the deploy launcher (dev-folder -> installation sync tool).

New-Item -ItemType Directory -Force $OutDir | Out-Null
$zip = Join-Path $OutDir "$name.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
# Build the archive entry by entry: ZipFile.CreateFromDirectory on Windows PowerShell 5.1 (.NET Framework) stores '\' in entry
# names, which other unzip tools treat as part of the file name. The zip standard separator is '/'.
$archive = [System.IO.Compression.ZipFile]::Open($zip, [System.IO.Compression.ZipArchiveMode]::Create, [System.Text.Encoding]::UTF8)
try {
    Get-ChildItem -LiteralPath $stage -Recurse -File | ForEach-Object {
        $entry = $_.FullName.Substring($stage.Length).TrimStart('\').Replace('\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $_.FullName, $entry, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
} finally { $archive.Dispose() }
Remove-Item $stage -Recurse -Force
Write-Output "Created: $zip ($([math]::Round((Get-Item $zip).Length / 1MB, 2)) MB)"
