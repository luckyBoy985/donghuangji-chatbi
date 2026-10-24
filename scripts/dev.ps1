$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Logs = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

& (Join-Path $PSScriptRoot "start.ps1")
$Web = Start-Process -FilePath "npm.cmd" `
    -ArgumentList @("run", "dev") `
    -WorkingDirectory (Join-Path $Root "frontend") `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Logs "web.out.log") `
    -RedirectStandardError (Join-Path $Logs "web.err.log") `
    -PassThru

Write-Host "Vite: http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "按 Ctrl+C 结束前端开发服务。"
try {
    Wait-Process -Id $Web.Id
} finally {
    if (-not $Web.HasExited) { Stop-Process -Id $Web.Id -Force }
}
