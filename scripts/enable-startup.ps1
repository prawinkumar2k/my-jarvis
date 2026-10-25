# Start JARVIS automatically after the current user signs in to Windows.
#   -Method Shortcut       (default) visible JARVIS.lnk in shell:startup
#   -Method TaskScheduler  per-user logon task with a short delay
# Neither needs administrator rights. Runs only after sign-in, never before.
[CmdletBinding()]
param(
    [ValidateSet("Shortcut", "TaskScheduler")]
    [string]$Method = "Shortcut",
    [int]$DelaySec = 20
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "JarvisCommon.psm1") -Force

if (-not (Get-JarvisPython)) {
    Write-Host "ERROR: JARVIS is not installed here. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

$command = Get-JarvisStartScriptCommand
$root = Get-JarvisRoot

if ($Method -eq "Shortcut") {
    $path = Get-JarvisStartupShortcutPath
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $command.Executable
    $link.Arguments = $command.Arguments
    $link.WorkingDirectory = $root
    $link.WindowStyle = 7  # minimized
    $link.Description = "Start JARVIS after sign-in (remove with scripts\disable-startup.ps1)"
    $icon = Join-Path $root "media\jarvis.ico"
    if (Test-Path -LiteralPath $icon) { $link.IconLocation = $icon }
    $link.Save()
    Write-Host "Login startup enabled (Startup folder shortcut): $path"
} else {
    $action = New-ScheduledTaskAction -Execute $command.Executable -Argument $command.Arguments -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $trigger.Delay = "PT{0}S" -f [Math]::Max(0, $DelaySec)
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName (Get-JarvisTaskName) -Description (Get-JarvisTaskDescription) -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host "Login startup enabled (Task Scheduler task '$(Get-JarvisTaskName)', ${DelaySec}s after sign-in)."
}
exit 0
