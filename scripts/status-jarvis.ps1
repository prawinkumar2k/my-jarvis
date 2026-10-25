# Report whether JARVIS is running, ready, and set to start at sign-in.
[CmdletBinding()]
param([switch]$Json)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "JarvisCommon.psm1") -Force

$procs = @(Get-JarvisProcesses)
$shortcut = Get-JarvisStartupShortcutPath
$task = Get-JarvisStartupTask
$status = [ordered]@{
    installed        = [bool](Get-JarvisPython)
    running          = ($procs.Count -gt 0)
    backend_ready    = (Test-JarvisBackendReady)
    process_ids      = @($procs | ForEach-Object ProcessId)
    startup_shortcut = (Test-Path -LiteralPath $shortcut)
    startup_task     = [bool]$task
    startup_enabled  = ((Test-Path -LiteralPath $shortcut) -or [bool]($task -and $task.State -ne "Disabled"))
    log_dir          = (Get-JarvisLogDir)
}

if ($Json) {
    $status | ConvertTo-Json -Compress
    exit 0
}
$status.GetEnumerator() | ForEach-Object { "{0,-17} {1}" -f $_.Key, ($_.Value -join ", ") }
