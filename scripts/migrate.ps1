param(
    [string]$Owner = "admin",
    [string]$LegacyFile = "data\legacy\chatbi-v1.db"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$LegacyPath = Join-Path $Root $LegacyFile

if (-not (Test-Path -LiteralPath $LegacyPath)) {
    throw "未找到旧版 SQLite：$LegacyPath"
}

Push-Location $Root
try {
    docker compose exec -T api python backend/scripts/migrate_legacy_sqlite.py `
        --sqlite /legacy/chatbi-v1.db `
        --owner $Owner
    if ($LASTEXITCODE -ne 0) { throw "旧数据迁移失败" }
} finally {
    Pop-Location
}
