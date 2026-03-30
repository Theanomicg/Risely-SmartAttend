$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\.."

try {
    docker info | Out-Null
} catch {
    Write-Error "Docker Desktop is not running. Start Docker Desktop, wait until the engine is running, then rerun .\scripts\start-db.ps1"
    exit 1
}

docker compose up -d postgres
