# claude-bridge — sobe o oracle Claude (server.py) em :8765. Motor: claude -p (ASSINATURA).
#
# SETUP (1x):
#   claude setup-token        # gera token OAuth (requer assinatura Claude)
#   # cole o token em  tools\claude_bridge\.oauth_token  (gitignorado, NAO compartilhe)
#
# USO:
#   .\start.ps1 -SelfTest     # testa a auth/chamada (espera 'PONG'), sem subir o server
#   .\start.ps1               # sobe o oracle em :8765 (gate ja chama essa porta)
#   .\start.ps1 -Port 8766    # outra porta

param([switch]$SelfTest, [int]$Port = 8765)

$ErrorActionPreference = "Stop"
$here      = $PSScriptRoot
$repo      = (Resolve-Path (Join-Path $here "..\..")).Path
$server    = Join-Path $here "server.py"
$tokenFile = Join-Path $here ".oauth_token"

# Python: venv do repo, senao 'python' do PATH.
$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

# Token OAuth (assinatura, sem API key).
if (-not $env:CLAUDE_CODE_OAUTH_TOKEN) {
    if (Test-Path $tokenFile) {
        $env:CLAUDE_CODE_OAUTH_TOKEN = (Get-Content $tokenFile -Raw).Trim()
        Write-Host "[start] token OAuth carregado de .oauth_token"
    } else {
        Write-Warning "Sem CLAUDE_CODE_OAUTH_TOKEN e sem .oauth_token."
        Write-Warning "Rode 'claude setup-token' e cole o token em $tokenFile."
        return
    }
}

if ($SelfTest) { & $py $server --selftest; return }

Write-Host "[start] oracle Claude em http://127.0.0.1:$Port (motor: claude -p, assinatura)"
& $py $server --port $Port
