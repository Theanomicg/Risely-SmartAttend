$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\kiosk"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

$python = if (Test-Path ".venv\Scripts\python.exe") {
    Resolve-Path ".venv\Scripts\python.exe"
} else {
    "python"
}

& $python "main.py"
