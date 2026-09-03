# Dot-source: . ./scripts/use-android.ps1
# Ajusta apenas a sessao PowerShell atual, nunca a configuracao global.
$projectAndroidSdk = Join-Path (Split-Path $PSScriptRoot -Parent) '.tools/android-sdk'
if (Test-Path (Join-Path $projectAndroidSdk 'platform-tools/adb.exe')) {
  $env:ANDROID_HOME = (Resolve-Path $projectAndroidSdk).Path
  $env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
  $env:PATH = "$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\cmdline-tools\latest\bin;$env:PATH"
} elseif (-not $env:ANDROID_HOME) {
  throw 'Android SDK ausente. Siga docs/RUNBOOK.md antes de compilar.'
}
