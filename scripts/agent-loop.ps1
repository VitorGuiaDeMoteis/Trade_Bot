param(
    [switch]$Once,
    [int]$DelaySeconds = 180
)

$ErrorActionPreference = "Continue"

$Repo = "C:\Users\vitor\OneDrive\Documentos\ChatGPT\TradingBot-agent"

$Runtime = Join-Path $env:LOCALAPPDATA "TradingBotAgent"
$StopFile = Join-Path $Runtime "stop.flag"
$StatusFile = Join-Path $Runtime "status.txt"
$PidFile = Join-Path $Runtime "agent.pid"

New-Item -ItemType Directory -Force $Runtime | Out-Null

chcp 65001 > $null

$Utf8 = New-Object System.Text.UTF8Encoding $false

[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Set-Location $Repo

$Branch = (git branch --show-current).Trim()

if ($Branch -ne "agent/autonomous-dev") {
    throw "Safety stop: current branch is $Branch"
}

if (Test-Path $PidFile) {

    $OldPid = Get-Content $PidFile -ErrorAction SilentlyContinue

    if ($OldPid -match '^\d+$') {

        $Existing = Get-Process -Id ([int]$OldPid) -ErrorAction SilentlyContinue

        if ($Existing) {
            throw "Another TradingBot autonomous loop is already running with PID $OldPid"
        }
    }
}

$PID | Set-Content $PidFile -Encoding ASCII

Remove-Item $StopFile -ErrorAction SilentlyContinue

hermes -p cloud config set model.default "stealth/space-bunny-alpha"

$Prompt = "Start ONE SMALL TradingBot autonomous development cycle. Read AGENT_MISSION.md, AGENT_STATE.md and AGENT_LESSONS.md first and obey them exactly. FIRST inspect git status. If the worktree is dirty, enter RECOVERY MODE: do NOT choose a new task; inspect the existing diff, finish/validate the current WIP, update state/lessons, commit locally if safe, confirm a clean tree, report and STOP. Only if the worktree starts clean may you choose ONE new safe high-value task. Prefer targeted reads/tests; never run the full suite at cycle start. Respect the 30-turn budget and reserve the final turns for state, commit and clean-tree verification. Never temporarily break tracked production code. Do not push, read secrets, mutate broker state or mutate the runtime database. Report CYCLE RESULT / TASK / CHANGES / VALIDATION / COMMIT / NEXT CANDIDATE TASK, then STOP."

$Cycle = 0

try {

    while ($true) {

        if (Test-Path $StopFile) {

            "STOPPED $(Get-Date -Format o)" |
                Set-Content $StatusFile -Encoding UTF8

            Write-Host ""
            Write-Host "STOP solicitado. Encerrando agente." -ForegroundColor Yellow

            break
        }

        $Branch = (git branch --show-current).Trim()

        if ($Branch -ne "agent/autonomous-dev") {

            "SAFETY_STOP wrong_branch=$Branch" |
                Set-Content $StatusFile -Encoding UTF8

            throw "Safety stop: branch changed to $Branch"
        }

        $Cycle++

        $Started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

@"
RUNNING
cycle=$Cycle
started=$Started
pid=$PID
repo=$Repo
branch=$Branch
model=stealth/space-bunny-alpha
"@ | Set-Content $StatusFile -Encoding UTF8

        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Cyan
        Write-Host " TRADINGBOT AUTONOMOUS DEV - CICLO $Cycle" -ForegroundColor Cyan
        Write-Host " $Started" -ForegroundColor Cyan
        Write-Host "============================================================" -ForegroundColor Cyan
        Write-Host ""

        hermes -p cloud chat --oneshot --max-turns 30 -q $Prompt

        $ExitCode = $LASTEXITCODE
        $Finished = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

@"
IDLE
cycle=$Cycle
finished=$Finished
last_exit_code=$ExitCode
pid=$PID
repo=$Repo
branch=$Branch
model=stealth/space-bunny-alpha
"@ | Set-Content $StatusFile -Encoding UTF8

        if ($Once) {

            Write-Host ""
            Write-Host "Ciclo único concluído." -ForegroundColor Green

            break
        }

        if ($ExitCode -ne 0) {

            $Wait = 600

            Write-Host ""
            Write-Host "Hermes retornou erro ($ExitCode)." -ForegroundColor Yellow
            Write-Host "Provável limite temporário/provider." -ForegroundColor Yellow
            Write-Host "Nova tentativa em $Wait segundos." -ForegroundColor Yellow
        }
        else {

            $Wait = $DelaySeconds

            Write-Host ""
            Write-Host "Ciclo $Cycle concluído." -ForegroundColor Green
            Write-Host "Próximo ciclo em $Wait segundos." -ForegroundColor DarkGray
        }

        for ($i = 0; $i -lt $Wait; $i++) {

            if (Test-Path $StopFile) {
                break
            }

            Start-Sleep -Seconds 1
        }
    }
}
finally {

    Remove-Item $PidFile -ErrorAction SilentlyContinue
}



