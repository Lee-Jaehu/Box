# Checks whether a TCP port can be used by the server.
# Exit codes: 0 = free, 2 = already in use (another server is listening), 3 = reserved by Windows (excluded port range, would fail with WinError 10013)
# ASCII only (Windows PowerShell 5.1 reads BOM-less files with the system codepage).
param([Parameter(Mandatory = $true)][int]$Port)
$ErrorActionPreference = "Stop"

$listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listen) {
    $pidv = ($listen | Select-Object -First 1).OwningProcess
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidv" -ErrorAction SilentlyContinue
    [Console]::Error.WriteLine("port $Port is already in use by pid $pidv : " + ($proc.CommandLine))
    exit 2
}
$lines = & netsh interface ipv4 show excludedportrange protocol=tcp 2>$null
foreach ($line in $lines) {
    if ($line -match '^\s*(\d+)\s+(\d+)') {
        if ($Port -ge [int]$Matches[1] -and $Port -le [int]$Matches[2]) {
            [Console]::Error.WriteLine("port $Port is inside a Windows excluded port range ($($Matches[1])-$($Matches[2]))")
            exit 3
        }
    }
}
exit 0
