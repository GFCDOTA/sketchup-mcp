# Launcher do event_bridge (Issue #589, fase 1: dry-run). Sem bash/MSYS. Sem segredos: usa o `gh auth` ja existente do executor.
# Uso:  powershell -File tools\orchestration\run_event_bridge.ps1 [-Once] [-IntervalSeconds 120] [-Execute]
# Log:  runs\governance\event_bridge.log (uma linha JSON por ciclo). Parar: Ctrl+C ou encerrar a tarefa agendada.
# Agendador de Tarefas (logon do usuario, so roda com o PC ligado e a sessao ativa):
#   schtasks /Create /TN "sketchup-mcp event bridge" /SC ONLOGON /TR "powershell -NoProfile -File <repo>\tools\orchestration\run_event_bridge.ps1"
param([switch]$Once, [int]$IntervalSeconds = 120, [string]$ExpectedLogin = "fmodesto30", [switch]$Execute)
$ErrorActionPreference = "Stop"
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
# Sem -Execute: so ingestao (fase 1, dry-run). Com -Execute: event_executor consome a fila e roda o Claude local (fase 2).
if ($Execute) { $argsList = @("-m", "tools.orchestration.event_executor", "run", "--interval", $IntervalSeconds, "--execute") }
else { $argsList = @("-m", "tools.orchestration.event_executor", "run", "--interval", $IntervalSeconds) }
if ($Once) { $argsList += "--once" }
Push-Location $repo
try { & $py @argsList 2>&1 | Tee-Object -FilePath $log -Append } finally { Pop-Location }
exit $LASTEXITCODE
