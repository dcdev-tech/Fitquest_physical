$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = Join-Path $root 'venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  Write-Error "Python not found at $python"
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$python' -m uvicorn common_backend.app:app --host 127.0.0.1 --port 8000 --reload"
Start-Sleep -Seconds 2
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; & '$python' -m streamlit run common_frontend/streamlit_app.py --server.port 8501"

Write-Host 'Started backend (8000) and frontend (8501) in separate windows.'
