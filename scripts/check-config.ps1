param(
    [string]$EnvFile
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
if (-not $EnvFile) {
    $EnvFile = Join-Path $Root ".env"
}
if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Environment file is missing: $EnvFile"
}

Push-Location $Root
try {
    $tracked = git ls-files -- ".env"
    if ($tracked) {
        throw ".env must not be tracked by Git"
    }
} finally {
    Pop-Location
}

$values = @{}
Get-Content -LiteralPath $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$') {
        $values[$matches[1]] = $matches[2].Trim().Trim('"')
    }
}

$required = @(
    "HTTP_PORT",
    "APP_ENV",
    "POSTGRES_PASSWORD",
    "MINIO_ROOT_PASSWORD",
    "SECRET_KEY",
    "BOOTSTRAP_ADMIN_TOKEN",
    "MCP_ACCESS_TOKEN",
    "DEEPSEEK_API_KEY"
)
$missing = $required | Where-Object { -not $values[$_] }
if ($missing) {
    throw "Missing configuration: $($missing -join ', ')"
}

$placeholders = $values.GetEnumerator() | Where-Object {
    $_.Value -match '^replace-with-' -or
    $_.Value -eq 'development-only-change-this-secret-key'
} | Select-Object -ExpandProperty Key
if ($placeholders) {
    throw "Placeholder configuration is still in use: $($placeholders -join ', ')"
}

$minimumLengths = @{
    POSTGRES_PASSWORD = 16
    MINIO_ROOT_PASSWORD = 16
    SECRET_KEY = 32
    BOOTSTRAP_ADMIN_TOKEN = 32
    MCP_ACCESS_TOKEN = 32
    DEEPSEEK_API_KEY = 20
}
$weak = $minimumLengths.Keys | Where-Object {
    $values[$_].Length -lt $minimumLengths[$_]
}
if ($weak) {
    throw "Secret is too short: $($weak -join ', ')"
}

if ($values["ALLOWED_ORIGIN"] -match '^https://' -and
    $values["SESSION_COOKIE_SECURE"] -ne "true") {
    throw "HTTPS deployment requires SESSION_COOKIE_SECURE=true"
}

Write-Host "Environment configuration check passed." -ForegroundColor Green
