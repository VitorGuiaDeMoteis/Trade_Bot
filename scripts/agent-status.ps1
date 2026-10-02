$Runtime = Join-Path $env:LOCALAPPDATA "TradingBotAgent"

$StatusFile = Join-Path $Runtime "status.txt"
$PidFile = Join-Path $Runtime "agent.pid"

Write-Host ""
Write-Host "=== AGENT STATUS ===" -ForegroundColor Cyan

if (Test-Path $StatusFile) {
    Get-Content $StatusFile
}
else {
    Write-Host "Nenhum status registrado."
}

Write-Host ""

if (Test-Path $PidFile) {

    $AgentPid = Get-Content $PidFile -ErrorAction SilentlyContinue

    $Process = Get-Process -Id ([int]$AgentPid) -ErrorAction SilentlyContinue

    if ($Process) {
        Write-Host "Processo do agente ativo: PID $AgentPid" -ForegroundColor Green
    }
    else {
        Write-Host "PID antigo encontrado, mas processo não está ativo." -ForegroundColor Yellow
    }
}
else {
    Write-Host "Nenhum loop ativo detectado."
}

Write-Host ""
Write-Host "=== GIT STATUS ===" -ForegroundColor Cyan

git status --short

Write-Host ""
Write-Host "=== ÚLTIMOS COMMITS ===" -ForegroundColor Cyan

git log --oneline -10
