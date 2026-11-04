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
if (-not (Test-Path $gh)) { [Console]::Error.WriteLine("gh CLI nao encontrado"); exit 2 }
$env:GH_BIN = $gh
Remove-Item Env:GH_TOKEN -ErrorAction SilentlyContinue
& $gh auth status *> $null
if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine("gh sem login: rode 'gh auth login' como o executor"); exit 3 }
# Fail-closed: estar logado nao basta, tem de ser a conta EXECUTORA (nunca o revisor fmmodesto nem outra)
$login = (& $gh api user --jq .login).Trim()
if ($login -ne $ExpectedLogin) { [Console]::Error.WriteLine("gh autenticado como '$login'; o bridge so roda como '$ExpectedLogin'"); exit 3 }
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
