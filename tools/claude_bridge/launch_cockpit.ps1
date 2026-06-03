# launch_cockpit.ps1 — clique-pra-subir o GATE (:8765 oracle) + COCKPIT (dashboard)
#
# O atalho da area de trabalho aponta pra ca. Um processo so serve as duas coisas:
#   - oracle  : POST http://127.0.0.1:8765/ask   (modo B, decide bifurcacoes tecnicas)
#   - cockpit : GET  http://127.0.0.1:8765/       (command center GREEN/YELLOW/RED)
#
# Comportamento:
#   - se ja estiver de pe  -> so abre o dashboard no browser
#   - se nao               -> sobe o gate nesta janela e abre o browser quando /health responder
#
# FECHAR esta janela DERRUBA o gate. Deixe aberta enquanto trabalha.

$ErrorActionPreference = "SilentlyContinue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8765
$url  = "http://127.0.0.1:$port/"

function Test-Gate {
    try { return (Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200 }
    catch { return $false }
}

Write-Host ""
Write-Host "  ===  SketchUp Cockpit + Gate  ===" -ForegroundColor Cyan
Write-Host "  dashboard : $url" -ForegroundColor DarkCyan
Write-Host "  oracle    : POST $url`ask  (modo B)" -ForegroundColor DarkCyan
Write-Host ""

if (Test-Gate) {
    Write-Host "[cockpit] gate JA esta de pe -> abrindo o dashboard no browser." -ForegroundColor Green
    Start-Process $url
    Start-Sleep -Seconds 2
    Write-Host "[cockpit] (este atalho nao precisa ficar aberto; o gate ja roda em outra janela)" -ForegroundColor DarkGray
    return
}

Write-Host "[cockpit] subindo o gate + cockpit ..." -ForegroundColor Yellow

# Abre o dashboard no browser assim que o /health responder (em paralelo, nao bloqueia).
Start-Job -ArgumentList $port, $url -ScriptBlock {
    param($port, $url)
    for ($i = 0; $i -lt 40; $i++) {
        try {
            if ((Invoke-WebRequest "http://127.0.0.1:$port/health" -TimeoutSec 2 -UseBasicParsing).StatusCode -eq 200) {
                Start-Process $url; break
            }
        } catch {}
        Start-Sleep -Milliseconds 700
    }
} | Out-Null

# Sobe o gate NESTA janela (bloqueia ate fechar). start.ps1 carrega o .oauth_token + a venv do repo.
& (Join-Path $here "start.ps1")
