$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

docker compose up -d postgres

