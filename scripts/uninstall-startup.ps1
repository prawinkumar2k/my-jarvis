# Remove every JARVIS startup integration and stop the running app.
# User data in %LOCALAPPDATA%\Jarvis, .env, and the project folder are kept.
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
& (Join-Path $PSScriptRoot "stop-jarvis.ps1")
& (Join-Path $PSScriptRoot "disable-startup.ps1")
Import-Module (Join-Path $PSScriptRoot "JarvisCommon.psm1") -Force
Write-Host "Startup integration removed. Data kept in $(Get-JarvisDataDir); project kept in $(Get-JarvisRoot)."
exit 0
