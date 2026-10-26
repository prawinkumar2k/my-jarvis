# One-step install: run setup.ps1, create .env if missing, health-check the
# backend, and enable login startup (skip with -NoStartup).
[CmdletBinding()]
param(
    [switch]$Full,
    [switch]$NoStartup,
    [ValidateSet("Shortcut", "TaskScheduler")]
    [string]$StartupMethod = "Shortcut"
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "JarvisCommon.psm1") -Force
$root = Get-JarvisRoot

$build = [Environment]::OSVersion.Version
if ($build.Major -lt 10) {
    Write-Host "ERROR: Windows 10 or 11 is required." -ForegroundColor Red
    exit 1
}

$setupArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "setup.ps1"))
if ($Full) { $setupArgs += "-Full" }
& powershell.exe @setupArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: setup.ps1 failed (exit $LASTEXITCODE). Fix the message above and rerun." -ForegroundColor Red
    exit 1
}

$envFile = Join-Path $root ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $root ".env.example") -Destination $envFile
    Write-Host "Created .env from .env.example."
}
$envText = Get-Content -LiteralPath $envFile -Raw
if ($envText -notmatch '(?m)^\s*(GEMINI_API_KEY|GROQ_API_KEY)\s*=\s*"?[A-Za-z0-9_\-]{10,}') {
    Write-Host "NOTE: no AI key set. Add GEMINI_API_KEY or GROQ_API_KEY to .env (or use the first-run screen)." -ForegroundColor Yellow
}

Write-Host "Running health check..."
$python = Get-JarvisPython
$check = & $python -c "import sys; sys.path.insert(0, r'$root\src\backend'); sys.path.insert(0, r'$root'); import os; os.environ['JARVIS_TEST_MODE']='1'; import asyncio, jarvis_backend as jb; r = asyncio.run(jb.app.test_client().get('/api/status')); print(r.status_code)" 2>$null
if (($check | Select-Object -Last 1) -ne "200") {
    Write-Host "ERROR: backend health check failed. Run: $python $root\src\backend\jarvis_backend.py" -ForegroundColor Red
    exit 1
}
Write-Host "Health check passed (/api/status 200)."

if (-not $NoStartup) {
    & (Join-Path $PSScriptRoot "enable-startup.ps1") -Method $StartupMethod
}

Write-Host ""
Write-Host "Installed. Start:  .\scripts\start-jarvis.ps1"
Write-Host "Microphone: allow desktop apps in Settings > Privacy & security > Microphone."
Write-Host "Auto-start: .\scripts\enable-startup.ps1   Remove: .\scripts\uninstall-startup.ps1"
exit 0
