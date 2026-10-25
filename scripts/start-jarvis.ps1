# Start the JARVIS desktop app for the current user.
# Used by the Startup shortcut / logon task (-AutoStart) and by hand.
[CmdletBinding()]
param(
    [switch]$AutoStart,
    [int]$ReadyTimeoutSec = 120
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "JarvisCommon.psm1") -Force

$root = Get-JarvisRoot
$logDir = Get-JarvisLogDir
$startupLog = Join-Path $logDir "startup.log"

function Write-StartupLog([string]$message) {
    $line = "{0} [start-jarvis] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $message
    Add-Content -LiteralPath $startupLog -Value $line -Encoding UTF8
    if (-not $AutoStart) { Write-Host $message }
}

$pythonw = Get-JarvisPython -Windowless
if (-not $pythonw) {
    Write-StartupLog "ERROR: venv not found in '$root'. Run setup.ps1 first."
    if (-not $AutoStart) { exit 1 }
    exit 1
}

if (Get-JarvisProcesses | Where-Object { $_.Role -eq "desktop" }) {
    Write-StartupLog "JARVIS is already running; not starting a second instance."
    exit 0
}

Write-StartupLog ("Starting JARVIS from '{0}'{1}." -f $root, $(if ($AutoStart) { " (login auto-start)" } else { "" }))
$env:JARVIS_STARTUP_LOG = $startupLog
Start-Process -FilePath $pythonw -ArgumentList @("`"$(Join-Path $root 'start_app.py')`"") -WorkingDirectory $root | Out-Null

$deadline = (Get-Date).AddSeconds($ReadyTimeoutSec)
while ((Get-Date) -lt $deadline) {
    if (Test-JarvisBackendReady) {
        Write-StartupLog "JARVIS backend is ready at http://127.0.0.1:5002."
        exit 0
    }
    if (-not (Get-JarvisProcesses)) {
        Write-StartupLog "ERROR: JARVIS exited during startup. See $startupLog."
        exit 1
    }
    Start-Sleep -Seconds 2
}
Write-StartupLog "WARNING: backend not ready after $ReadyTimeoutSec s; JARVIS is still starting. See $startupLog."
exit 0
