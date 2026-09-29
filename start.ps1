param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $root 'backend'
$frontendRoot = Join-Path $root 'frontend'

$pythonExe = 'C:\Users\smalmi\AppData\Local\Programs\Python\Python312\python.exe'
$npmCmd = 'C:\Users\smalmi\AppData\Local\Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.15.0-win-x64\npm.cmd'

Write-Host 'Starting Välituki...'

Write-Host 'Starting backend on http://localhost:8000'
Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-Command',
    "Set-Location '$backendRoot'; & '$pythonExe' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
) -WorkingDirectory $backendRoot

Write-Host 'Starting frontend on http://localhost:5173'
Start-Process powershell -ArgumentList @(
    '-NoExit',
    '-Command',
    "Set-Location '$frontendRoot'; `$env:VITE_PROXY_TARGET='http://127.0.0.1:8000'; & '$npmCmd' run dev -- --port 5173"
) -WorkingDirectory $frontendRoot

Write-Host ''
Write-Host 'Open the frontend at: http://localhost:5173'
Write-Host 'Backend health endpoint: http://localhost:8000/api/health'

if (-not $NoBrowser) {
    try {
        Start-Process 'http://localhost:5173'
    }
    catch {
        Write-Host 'Could not open the browser automatically.'
    }
}
