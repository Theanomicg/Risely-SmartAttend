$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\server"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

$serverHost = "127.0.0.1"
$serverPort = 8000

foreach ($line in Get-Content ".env") {
    if ([string]::IsNullOrWhiteSpace($line) -or $line.TrimStart().StartsWith("#")) {
        continue
    }

    $parts = $line.Split("=", 2)
    if ($parts.Length -ne 2) {
        continue
    }

    $key = $parts[0].Trim()
    $value = $parts[1].Trim().Trim("'").Trim('"')

    switch ($key) {
        "SERVER_HOST" {
            if ($value) {
                $serverHost = $value
            }
        }
        "SERVER_PORT" {
            $parsedPort = 0
            if ([int]::TryParse($value, [ref]$parsedPort)) {
                $serverPort = $parsedPort
            }
        }
    }
}

$python = if (Test-Path ".venv\Scripts\python.exe") {
    Resolve-Path ".venv\Scripts\python.exe"
} else {
    "python"
}

& $python -m uvicorn app.main:app --host $serverHost --port $serverPort
