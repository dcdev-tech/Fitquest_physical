$ErrorActionPreference = 'SilentlyContinue'

Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match 'python(.exe)?' -and $_.CommandLine -match 'uvicorn common_backend.app:app|streamlit run common_frontend/streamlit_app.py' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host 'Stopped backend/frontend processes (if running).'
