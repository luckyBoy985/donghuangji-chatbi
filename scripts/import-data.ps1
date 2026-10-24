param(
    [Parameter(Mandatory = $true)]
    [string]$Source
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Python = if ($env:PYTHON) {
    $env:PYTHON
} else {
    (Get-Command python -ErrorAction Stop).Source
}

Push-Location $Root
try {
    & $Python "backend\scripts\import_data.py" `
        --source $Source `
        --destination (Join-Path $Root "data\runtime")
} finally {
    Pop-Location
}

Write-Host "Data baseline imported." -ForegroundColor Green
