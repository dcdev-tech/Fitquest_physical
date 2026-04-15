$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  Write-Error "Python not found at $python"
}

$mongoUri = $env:MONGO_URI
$mongoDbName = $env:MONGO_DB_NAME
$backendUrl = $env:BACKEND_URL

$backendEnvPrefix = ""
if ($mongoUri) {
  $backendEnvPrefix += "`$env:MONGO_URI='$mongoUri'; "
}
if ($mongoDbName) {
  $backendEnvPrefix += "`$env:MONGO_DB_NAME='$mongoDbName'; "
}
if ($backendUrl) {
  $backendEnvPrefix += "`$env:BACKEND_URL='$backendUrl'; "
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; ${backendEnvPrefix}& '$python' -m uvicorn common_backend.app:app --host 127.0.0.1 --port 8000 --reload"
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; ${backendEnvPrefix}& '$python' -m streamlit run common_frontend/streamlit_app.py --server.port 8501"

Write-Host 'Started backend (8000) and frontend (8501) in separate windows.'
