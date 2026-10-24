param()

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent

if (-not (Test-Path -LiteralPath (Join-Path $Root ".env"))) {
    throw "缺少 .env。请复制 .env.production.example 并填写安全配置。"
}

Push-Location $Root
try {
    powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts/check-config.ps1")
    if ($LASTEXITCODE -ne 0) { throw "环境配置检查失败" }
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose 启动失败" }
    docker compose ps
    $Port = (Get-Content (Join-Path $Root ".env") |
        Where-Object { $_ -match '^HTTP_PORT=' } |
        Select-Object -First 1) -replace '^HTTP_PORT=', ''
    if (-not $Port) { $Port = "8080" }
    Write-Host "ChatBI: http://127.0.0.1:$Port" -ForegroundColor Green
    Write-Host "首次使用请在网页创建平台管理员。" -ForegroundColor Yellow
} finally {
    Pop-Location
}
