# Local Windows Launcher for Personal AI JobPilot
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Virtual environment not found at $Python. Run setup first."
}

Write-Host "Starting FastAPI backend on http://localhost:8000 ..."
$backend = Start-Process -FilePath $Python -ArgumentList "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $Root -PassThru

Start-Sleep -Seconds 3
Write-Host "Starting Streamlit dashboard on http://localhost:8501 ..."
try {
    & $Python -m streamlit run "frontend/app.py" --server.port 8501 --server.address 127.0.0.1
}
finally {
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force
    }
}
