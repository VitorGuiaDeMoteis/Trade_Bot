param([switch]$Database)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent

function Invoke-Checked {
  param([string]$Program, [string[]]$Arguments)
  & $Program @Arguments
  if ($LASTEXITCODE -ne 0) { throw "$Program falhou: exit $LASTEXITCODE" }
}

Push-Location $projectRoot
try {
  Invoke-Checked uv @('sync', '--locked')
  Invoke-Checked uv @('run', 'ruff', 'format', '--check', '.')
  Invoke-Checked uv @('run', 'ruff', 'check', '.')
  Invoke-Checked uv @('run', 'mypy')
  Invoke-Checked uv @('run', 'pytest', '-m', 'not integration')
  Invoke-Checked docker @('compose', 'config', '--quiet')
  if ($Database) {
    Invoke-Checked docker @('compose', '--profile', 'test', 'up', '-d', '--wait', 'postgres_test')
    $previousDbTestFlag = $env:RUN_DB_TESTS
    try {
      $env:RUN_DB_TESTS = '1'
      Invoke-Checked uv @('run', 'pytest', '-m', 'integration')
    } finally {
      $env:RUN_DB_TESTS = $previousDbTestFlag
    }
  }
  Push-Location apps/mobile_app
  try {
    Invoke-Checked flutter @('pub', 'get', '--enforce-lockfile')
    Invoke-Checked dart @('format', '--output=none', '--set-exit-if-changed', 'lib', 'test', 'integration_test', 'test_driver')
    Invoke-Checked flutter @('analyze', '--fatal-infos', '--fatal-warnings')
    Invoke-Checked flutter @('test')
  } finally { Pop-Location }
} finally { Pop-Location }
