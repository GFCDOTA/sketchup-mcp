# Launcher do ciclo padrao de PR (FP-060 MT-17): reconcilia a cada 30 s (pronto -> revisor solicitado -> REVIEW_REQUESTED) e revisa com o Codex real.
# So ASCII (Windows PowerShell 5.1 le .ps1 sem BOM como ANSI). Sem segredos no arquivo: o token do REVISOR (CODEX_REVIEWER_GH_TOKEN) vem do registro do usuario,
# e so e posto no ambiente DESTE processo; o `gh` do executor vem do keyring (GH_TOKEN fica de fora).
# Uso:  powershell -File tools\orchestration\run_pr_lifecycle.ps1 [-IntervalSeconds 30] [-Execute] [-Workers 3] [-AutoMerge]
#   sem -Execute: so planeja (nada e escrito no GitHub nem no EventStore, nenhum Codex roda).
#   -Workers N (1..3): revisoes independentes em paralelo (nunca duas no mesmo PR).
#   -AutoMerge: liga o merge protegido (AUTOMERGE_ENABLED=1) para os PRs aprovados; so mescla com a protecao da branch exigindo aprovacao independente.
# KILL SWITCH: criar o arquivo runs\governance\PR_LIFECYCLE_DISABLED (ao lado do estado do bridge) para o ciclo (nada novo e escrito, enfileirado ou revisado; as
#   revisoes em andamento terminam) e AUTOMERGE_DISABLED para o merge. Remover o arquivo retoma sozinho.
# Log:  runs\governance\pr_lifecycle.log (uma linha JSON por evento do ciclo). Parar: encerrar a tarefa ou este processo (a trava de instancia impede duas).
param([int]$IntervalSeconds = 30, [string]$ExpectedLogin = "fmodesto30", [switch]$Execute, [int]$Workers = 3, [switch]$AutoMerge)
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
# Fail-closed: tem de ser a conta EXECUTORA (nunca o revisor)
$login = (& $gh api user --jq .login).Trim()
if ($login -ne $ExpectedLogin) { [Console]::Error.WriteLine("gh autenticado como '$login'; o ciclo so roda como '$ExpectedLogin'"); exit 3 }
if ($Execute) {
    $tok = [Environment]::GetEnvironmentVariable("CODEX_REVIEWER_GH_TOKEN", "User")
    if (-not $tok) { [Console]::Error.WriteLine("CODEX_REVIEWER_GH_TOKEN ausente no registro do usuario: o revisor independente nao pode publicar"); exit 3 }
    $env:CODEX_REVIEWER_GH_TOKEN = $tok.Trim([char]0xFEFF).Trim()
}
$logDir = Join-Path $repo "runs\governance"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "pr_lifecycle.log"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$argsList = @("-m", "tools.orchestration.pr_lifecycle", "run", "--interval", $IntervalSeconds, "--watch-pid", $PID, "--workers", $Workers)
if ($Execute) { $argsList += "--execute" }
if ($AutoMerge -and $Execute) { $env:AUTOMERGE_ENABLED = "1" } else { Remove-Item Env:AUTOMERGE_ENABLED -ErrorAction SilentlyContinue }
Push-Location $repo
$ErrorActionPreference = "Continue"
try {
    & $py @argsList 2>&1 | ForEach-Object { Add-Content -Path $log -Value "$_" -Encoding UTF8 }
} finally { Pop-Location }
exit $LASTEXITCODE
