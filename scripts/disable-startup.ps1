# Stop JARVIS from starting at sign-in. Removes only JARVIS's own shortcut and
# logon task; the app, settings and data stay installed.
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "JarvisCommon.psm1") -Force

$removed = @()
$shortcut = Get-JarvisStartupShortcutPath
if (Test-Path -LiteralPath $shortcut) {
    Remove-Item -LiteralPath $shortcut -Force
    $removed += "Startup shortcut"
}
if (Get-JarvisStartupTask) {
    Unregister-ScheduledTask -TaskName (Get-JarvisTaskName) -Confirm:$false
    $removed += "Task Scheduler task"
}

if ($removed.Count -eq 0) {
    Write-Host "Login startup was already disabled."
} else {
    Write-Host ("Login startup disabled: removed {0}." -f ($removed -join " and "))
}
exit 0
