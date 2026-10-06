# Checks whether a TCP port can be used by the server.
# Exit codes: 0 = free (or could not be checked), 2 = already in use (another server is listening),
#             3 = reserved by Windows (excluded port range, would fail with WinError 10013)
# On company PCs, security policy may block netsh.exe or the network cmdlets ("Access is denied").
# Then the check is skipped with a one-line note (exit 0); the server itself reports WinError 10013 if the port is reserved.
# ASCII only (Windows PowerShell 5.1 reads BOM-less files with the system codepage).
param([Parameter(Mandatory = $true)][int]$Port)
$ErrorActionPreference = "Stop"

try {
    $listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
} catch {
    $listen = $null
    [Console]::Error.WriteLine("note: in-use port check skipped (not allowed on this PC)")
}
if ($listen) {
    $pidv = ($listen | Select-Object -First 1).OwningProcess
    $cmd = ""
    try { $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$pidv" -ErrorAction SilentlyContinue).CommandLine } catch { }
    [Console]::Error.WriteLine("port $Port is already in use by pid $pidv : " + $cmd)
    exit 2
}
try {
    $lines = & netsh interface ipv4 show excludedportrange protocol=tcp 2>$null
} catch {
    [Console]::Error.WriteLine("note: reserved-port check skipped (netsh is not allowed on this PC); if the server fails with WinError 10013, use another port")
    exit 0
}
foreach ($line in $lines) {
    if ($line -match '^\s*(\d+)\s+(\d+)') {
        if ($Port -ge [int]$Matches[1] -and $Port -le [int]$Matches[2]) {
            [Console]::Error.WriteLine("port $Port is inside a Windows excluded port range ($($Matches[1])-$($Matches[2]))")
            exit 3
        }
    }
}
exit 0
