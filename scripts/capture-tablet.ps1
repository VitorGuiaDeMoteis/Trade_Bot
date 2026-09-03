# Requer o aplicativo aberto em primeiro plano. Captura retrato/paisagem
# quando o dispositivo nao pode ser girado fisicamente, restaurando a rotacao.
param(
  [string]$Device = '1791a20e',
  [ValidatePattern('^[a-zA-Z0-9-]+$')][string]$Prefix = 'm1-tablet-full'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'use-android.ps1')
$artifactDirectory = Join-Path (Split-Path $PSScriptRoot -Parent) '.artifacts'
New-Item -ItemType Directory -Force $artifactDirectory | Out-Null

function Invoke-AdbChecked {
  param([string[]]$Arguments)
  $result = & adb -s $Device @Arguments
  if ($LASTEXITCODE -ne 0) { throw "ADB falhou: $Arguments" }
  return $result
}

$appPid = Invoke-AdbChecked @('shell', 'pidof', 'dev.tradingbot.mobile_app')
if (-not $appPid) { throw 'Inicie o aplicativo com flutter run antes de capturar.' }
$activity = (Invoke-AdbChecked @('shell', 'dumpsys', 'activity', 'activities')) -join "`n"
if ($activity -notmatch 'topResumedActivity=.*dev\.tradingbot\.mobile_app/') {
  throw 'O aplicativo precisa estar em primeiro plano.'
}
$originalMode = (Invoke-AdbChecked @('shell', 'wm', 'user-rotation')).Trim()
$originalRotation = (Invoke-AdbChecked @('shell', 'settings', 'get', 'system', 'user_rotation')).Trim()
if ($originalRotation -notmatch '^[0-3]$') { throw 'Rotacao original desconhecida.' }
if ($originalMode -notmatch '^(free|lock [0-3])$') { throw 'Modo de rotacao desconhecido.' }

try {
  foreach ($rotation in @(@{Value='0'; Name='portrait'}, @{Value='1'; Name='landscape'})) {
    Invoke-AdbChecked @('shell', 'wm', 'user-rotation', 'lock', $rotation.Value)
    Start-Sleep -Seconds 3
    Invoke-AdbChecked @('shell', 'screencap', '-p', '/data/local/tmp/trading-bot-capture.png')
    Invoke-AdbChecked @('pull', '/data/local/tmp/trading-bot-capture.png', (Join-Path $artifactDirectory "$Prefix-$($rotation.Name).png"))
  }
} finally {
  Invoke-AdbChecked @('shell', 'wm', 'user-rotation', 'lock', $originalRotation)
  if ($originalMode -eq 'free') {
    Invoke-AdbChecked @('shell', 'wm', 'user-rotation', 'free')
  }
  Invoke-AdbChecked @('shell', 'rm', '-f', '/data/local/tmp/trading-bot-capture.png')
  Write-Output "Rotacao restaurada: $(Invoke-AdbChecked @('shell', 'wm', 'user-rotation')); user_rotation=$originalRotation"
}
