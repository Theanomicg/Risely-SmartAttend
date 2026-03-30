$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\kiosk"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

python main.py

