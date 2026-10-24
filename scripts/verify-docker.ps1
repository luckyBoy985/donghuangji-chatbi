$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Port = (Get-Content (Join-Path $Root ".env") |
    Where-Object { $_ -match '^HTTP_PORT=' } |
    Select-Object -First 1) -replace '^HTTP_PORT=', ''
if (-not $Port) { $Port = "8080" }

Push-Location $Root
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health"
    if ($health.status -ne "ok") { throw "API 健康检查失败" }
    if ($health.index.status -ne "ready") { throw "检索索引不可用" }
    if ($health.bge.status -ne "ready") { throw "BGE-M3 模型目录不可用" }
    if ($health.reranker.status -ne "ready") { throw "Reranker 模型目录不可用" }
    $services = docker compose ps --format "{{.Service}} {{.Status}}"
    $services
    if ($LASTEXITCODE -ne 0) { throw "无法读取 Docker 服务状态" }
    foreach ($required in @("api", "worker", "beat", "postgres", "redis", "minio", "nginx")) {
        if (-not ($services -match "^$required\s")) {
            throw "Docker 服务未运行：$required"
        }
    }

    $redis = docker compose exec -T redis redis-cli ping
    if ($LASTEXITCODE -ne 0 -or $redis.Trim() -ne "PONG") {
        throw "Redis 健康检查失败"
    }
    docker compose exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL 健康检查失败" }
    docker compose exec -T minio curl -fsS http://localhost:9000/minio/health/live | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "MinIO 健康检查失败" }
    $workerPing = docker compose exec -T worker celery `
        -A backend.app.core.workers.celery_app inspect ping -t 5 2>&1
    if ($LASTEXITCODE -ne 0 -or -not ($workerPing -match "pong")) {
        throw "Celery Worker 健康检查失败"
    }
    Write-Host "Docker 健康检查通过。" -ForegroundColor Green
} finally {
    Pop-Location
}
