$Runtime = Join-Path $env:LOCALAPPDATA "TradingBotAgent"

New-Item -ItemType Directory -Force $Runtime | Out-Null

$StopFile = Join-Path $Runtime "stop.flag"

New-Item -ItemType File -Force $StopFile | Out-Null

Write-Host "Sinal de parada enviado." -ForegroundColor Yellow
Write-Host "O agente vai parar assim que o ciclo atual terminar." -ForegroundColor Yellow
