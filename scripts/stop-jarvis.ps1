# Stop JARVIS processes started from this folder. Asks the window to close
# first (the app then stops its backend); remaining processes are terminated
# after the grace period. Never touches other Python processes.
[CmdletBinding()]
param([int]$GraceSec = 10)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "JarvisCommon.psm1") -Force

$targets = @(Get-JarvisProcesses)
if ($targets.Count -eq 0) {
    Write-Host "JARVIS is not running."
    exit 0
}

foreach ($target in $targets | Where-Object { $_.Role -eq "desktop" }) {
    $proc = Get-Process -Id $target.ProcessId -ErrorAction SilentlyContinue
    if ($proc -and $proc.MainWindowHandle -ne 0) { [void]$proc.CloseMainWindow() }
}

$deadline = (Get-Date).AddSeconds($GraceSec)
while ((Get-Date) -lt $deadline -and @(Get-JarvisProcesses).Count -gt 0) {
    Start-Sleep -Milliseconds 500
}

$remaining = @(Get-JarvisProcesses)
foreach ($target in $remaining) {
    Stop-Process -Id $target.ProcessId -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 500
$left = @(Get-JarvisProcesses)
if ($left.Count -gt 0) {
    Write-Host ("Could not stop process id(s): {0}" -f (($left | ForEach-Object ProcessId) -join ", ")) -ForegroundColor Red
    exit 1
}
Write-Host ("JARVIS stopped ({0} process(es))." -f $targets.Count)
exit 0
