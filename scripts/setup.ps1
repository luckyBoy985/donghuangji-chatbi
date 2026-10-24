$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
$Python = if ($env:PYTHON) {
    $env:PYTHON
} else {
    (Get-Command python -ErrorAction Stop).Source
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "找不到指定 Python：$Python"
}

if (-not (Test-Path -LiteralPath (Join-Path $Root ".env"))) {
    Copy-Item -LiteralPath (Join-Path $Root ".env.example") -Destination (Join-Path $Root ".env")
    Write-Warning "已从 .env.example 创建 .env，请填写 DEEPSEEK_API_KEY。"
}

Push-Location (Join-Path $Root "backend")
try {
    & $Python -m pip install -e ".[test]"
} finally {
    Pop-Location
}

Push-Location (Join-Path $Root "frontend")
try {
    npm install
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath (Join-Path $Root "data\runtime\catalog.json"))) {
    throw "缺少 data/runtime/catalog.json。请使用 scripts/import-data.ps1 -Source <数据目录> 导入自有语料。"
}

Write-Host "环境准备完成。" -ForegroundColor Green
