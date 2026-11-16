# Launcher do event_bridge (Issue #589, fase 1: dry-run). Sem bash/MSYS. Sem segredos: usa o `gh auth` ja existente do executor.
# Uso:  powershell -File tools\orchestration\run_event_bridge.ps1 [-Once] [-IntervalSeconds 120] [-Execute]
# Log:  runs\governance\event_bridge.log (uma linha JSON por ciclo, UTF-8 sem BOM; ver event_bridge_log.ps1). Parar: Ctrl+C ou encerrar a tarefa agendada.
# Agendador de Tarefas: use tools\orchestration\install_event_bridge_task.ps1 (dry-run por padrao).
param([switch]$Once, [int]$IntervalSeconds = 120, [string]$ExpectedLogin = "fmodesto30", [switch]$Execute)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "event_bridge_log.ps1")
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { [Console]::Error.WriteLine("venv canonico ausente: $py (rode uv sync --locked --extra dev)"); exit 2 }
$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) { $gh = "C:\Program Files\GitHub CLI\gh.exe" }
# `gh` ausente/indisponivel NAO encerra o launcher: o loop Python trata isso como falha transitoria (backoff) e volta sozinho quando o executavel reaparecer; sair aqui
# gastaria os 3 reinicios da tarefa agendada sem nunca chegar a recuperacao.
if (Test-Path $gh) { $env:GH_BIN = $gh } else { [Console]::Error.WriteLine("gh CLI nao encontrado agora: o loop tentara de novo com backoff") }
Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
# A IDENTIDADE (login = executor, nunca o revisor) e verificada pelo PROCESSO PYTHON, fail-closed e com recuperacao: `event_executor run` espera o backoff persistido ANTES de
# qualquer chamada ao GitHub e, se o GitHub/`gh` estiver indisponivel no logon ou no reinicio, repete com backoff em vez de sair (a tarefa agendada tem so 3 reinicios).
# So uma conta ERRADA e fatal (codigo 3). Este launcher NAO chama `gh` para isso: uma indisponibilidade no logon o derrubaria antes de chegar a essa recuperacao.
$logDir = Join-Path $repo "runs\governance"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "event_bridge.log"
Initialize-BridgeLog -Path $log
# Sem -Execute: so ingestao (fase 1, dry-run). Com -Execute: event_executor consome a fila e roda o Claude local (fase 2).
if ($Execute) { $argsList = @("-m", "tools.orchestration.event_executor", "run", "--interval", $IntervalSeconds, "--watch-pid", $PID, "--execute") }
else { $argsList = @("-m", "tools.orchestration.event_executor", "run", "--interval", $IntervalSeconds, "--watch-pid", $PID) }
if ($Once) { $argsList += "--once" }
# Python em UTF-8 e o console decodifica UTF-8; o log e gravado por Write-BridgeLog (nunca Tee-Object: grava UTF-16 no PS 5.1).
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }
Push-Location $repo
$ErrorActionPreference = "Continue"                                         # stderr do filho (2>&1) nao pode virar erro terminante no PS 5.1
try { & $py @argsList 2>&1 | ForEach-Object { $line = "$_"; Write-BridgeLog -Path $log -Line $line; $line } } finally { Pop-Location }
exit $LASTEXITCODE
