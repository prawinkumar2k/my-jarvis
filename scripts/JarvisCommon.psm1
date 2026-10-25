# Shared helpers for the JARVIS Windows control scripts.
# Everything is per-user: no administrator rights, no services, nothing hidden.

Set-StrictMode -Version Latest

$script:RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$script:ShortcutName = "JARVIS.lnk"
$script:TaskName = "JARVIS Assistant (user logon)"
$script:TaskDescription = "Starts the JARVIS desktop assistant after this user signs in. Created by scripts\enable-startup.ps1; remove with scripts\disable-startup.ps1."

function Get-JarvisRoot { return $script:RepoRoot }

function Get-JarvisPython {
    param([switch]$Windowless)
    $name = if ($Windowless) { "pythonw.exe" } else { "python.exe" }
    $path = Join-Path $script:RepoRoot "venv\Scripts\$name"
    if (Test-Path -LiteralPath $path -PathType Leaf) { return $path }
    return $null
}

function Get-JarvisDataDir {
    $explicit = if ($env:JARVIS_DATA_DIR) { $env:JARVIS_DATA_DIR } elseif ($env:JARVIS_RUNTIME_DIR) { $env:JARVIS_RUNTIME_DIR } else { "" }
    if ($explicit) { return $explicit }
    $base = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME "AppData\Local" }
    return (Join-Path $base "Jarvis")
}

function Get-JarvisLogDir {
    $dir = Join-Path (Get-JarvisDataDir) "logs"
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    return $dir
}

function Get-JarvisStartupShortcutPath {
    return (Join-Path ([Environment]::GetFolderPath("Startup")) $script:ShortcutName)
}

function Get-JarvisTaskName { return $script:TaskName }

function Get-JarvisTaskDescription { return $script:TaskDescription }

function Get-JarvisStartupTask {
    try {
        return Get-ScheduledTask -TaskName $script:TaskName -ErrorAction Stop
    } catch {
        return $null
    }
}

function Get-JarvisStartScriptCommand {
    # Arguments for powershell.exe; quoted so paths with spaces work.
    $startScript = Join-Path $script:RepoRoot "scripts\start-jarvis.ps1"
    return @{
        Executable = (Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe")
        Arguments  = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScript`" -AutoStart"
    }
}

function Get-JarvisProcesses {
    # Only processes whose command line points at THIS checkout.
    $root = $script:RepoRoot.ToLowerInvariant()
    $desktop = (Join-Path $script:RepoRoot "start_app.py").ToLowerInvariant()
    $backend = (Join-Path $script:RepoRoot "src\backend\jarvis_backend.py").ToLowerInvariant()
    Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $cmd = [string]$_.CommandLine
            if (-not $cmd) { return $false }
            $lower = $cmd.ToLowerInvariant()
            ($lower.Contains($desktop) -or $lower.Contains($backend)) -and $lower.Contains($root)
        } |
        ForEach-Object {
            $cmd = ([string]$_.CommandLine).ToLowerInvariant()
            [pscustomobject]@{
                ProcessId = $_.ProcessId
                Role      = if ($cmd.Contains($backend)) { "backend" } else { "desktop" }
            }
        }
}

function Test-JarvisBackendReady {
    param([int]$Port = 5002, [int]$TimeoutSec = 2)
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/status" -UseBasicParsing -TimeoutSec $TimeoutSec
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

Export-ModuleMember -Function *
