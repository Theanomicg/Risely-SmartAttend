$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\dashboard"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

npm run dev

