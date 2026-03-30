$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\server"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

$python = if (Test-Path ".venv\Scripts\python.exe") {
    Resolve-Path ".venv\Scripts\python.exe"
} else {
    "python"
}

& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
