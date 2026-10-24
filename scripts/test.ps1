param(
    [switch]$SkipEval
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
    & $Python -m pytest backend/tests -q
    if ($LASTEXITCODE -ne 0) { throw "后端测试失败" }

    Push-Location (Join-Path $Root "frontend")
    try {
        npm test -- --run
        if ($LASTEXITCODE -ne 0) { throw "前端测试失败" }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "前端构建失败" }
        npm audit --audit-level=high
        if ($LASTEXITCODE -ne 0) { throw "前端依赖审计失败" }
    } finally {
        Pop-Location
    }

    if (-not $SkipEval) {
        & $Python "backend/scripts/evaluate_retrieval.py" `
            --output (Join-Path $Root "data/eval_results.json")
        if ($LASTEXITCODE -ne 0) { throw "检索评测未达到 Hit@5 门槛" }
    }
} finally {
    Pop-Location
}

Write-Host "全部验证通过。" -ForegroundColor Green
