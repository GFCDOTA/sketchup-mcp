# Watchdog PERSISTENTE do SketchUp Creator (:8765) — v3 (FP-040 hardening).
# Mantem o ORACLE (tools/claude_bridge/server.py) vivo na :8765.
#
# FONTE DE VERDADE: este arquivo no REPO (tools/claude_bridge/). O deploy e uma
# COPIA para E:\Claude\ops\bridge\gate-watchdog-loop.ps1 (o autostart de login
# Startup\gate-watchdog.cmd lanca a copia do ops). Editar so no ops = drift.
#
# v3 sobre a v2 (diagnostico FP-040: 16.753 DOWNs / 10.743 relaunches em 27d):
#  - SINGLETON: se ja ha outra instancia viva (pid file + commandline match),
#    SAI em vez de rodar em paralelo. Causa raiz dos watchdogs duplicados: DOIS
#    .cmd no Startup lancavam este loop (claude-gate-autostart.cmd, removido).
#  - FAST-FIRST-LAUNCH: DOWN no 1o check apos o start do loop (caso boot/login)
#    -> lanca IMEDIATAMENTE, sem esperar 2 strikes (~90s de gap no login).
#  - SPAWN OBSERVAVEL: stdout/stderr do server relancado vao para
#    server-stdout.log / server-stderr.log (motivo da morte deixa de ser cego).
#  - BACKOFF + ALERTA: relaunches consecutivos sem estabilizar -> sleep dobra
#    (45s ate 300s) + linha ALERTA no log (fim do kill-loop de 109s infinito).
#  - ROTACAO: watchdog.log > 512KB -> watchdog.log.1 (evita o log de 1,2MB).
#  - Token lido BOM-safe ([IO.File]::ReadAllText detecta e tira BOM; o .Trim()
#    sozinho NAO tira BOM — gotcha real que ja corrompeu o Bearer).
# Mantido da v2: health check forte (200 + corpo com "oracle"), eviccao de
# impostor na porta, pid file p/ os launchers detectarem o keeper.
$ErrorActionPreference = 'SilentlyContinue'
$log        = 'E:\Claude\ops\bridge\watchdog.log'
$gatePidFile = 'E:\Claude\ops\bridge\gate-watchdog.pid'
$stdoutLog  = 'E:\Claude\ops\bridge\server-stdout.log'
$stderrLog  = 'E:\Claude\ops\bridge\server-stderr.log'
$tokenFile  = 'E:\Claude\ops\bridge\.oauth_token'
$maxLogBytes = 512KB

function L($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [wd] $m" | Out-File -FilePath $log -Append -Encoding utf8 }

function Rotate-Log {
    try {
        $f = Get-Item $log -ErrorAction Stop
        if ($f.Length -gt $maxLogBytes) {
            Move-Item -Force $log "$log.1"
            L "log rotacionado (anterior em watchdog.log.1)"
        }
    } catch { }
}

# --- SINGLETON: nunca rodar dois keepers do gate em paralelo -----------------
if (Test-Path $gatePidFile) {
    $other = (Get-Content $gatePidFile -Raw).Trim()
    if ($other -and $other -ne "$PID") {
        $pr = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $other) -ErrorAction SilentlyContinue
        if ($pr -and $pr.CommandLine -match 'gate-watchdog-loop') {
            L "singleton: instancia $other ja viva -> este pid $PID SAI (nao duplica keeper)"
            exit 0
        }
    }
}
try { "$PID" | Out-File -FilePath $gatePidFile -Encoding ascii -Force } catch { }

# venv PRIMEIRO: server.py importa tools.claude_bridge.* (resolvido pelo editable
# install do venv). uv-python funciona com PYTHONPATH setado (abaixo) — fallback.
$cands = @(
    'E:\Claude\apps\sketchup-mcp\.venv\Scripts\python.exe',
    'C:\Users\felip_local\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe',
    'C:\Users\felip_local\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe'
)
$py  = $cands | Where-Object { Test-Path $_ } | Select-Object -First 1
$srv = 'E:\Claude\apps\sketchup-mcp\tools\claude_bridge\server.py'
$env:PYTHONPATH = 'E:\Claude\apps\sketchup-mcp'

function Launch-Oracle {
    try { $env:CLAUDE_CODE_OAUTH_TOKEN = ([IO.File]::ReadAllText($tokenFile)).Trim() } catch { L "token read FAIL" }
    # stdout/stderr CAPTURADOS (v3): a morte do spawn deixa de ser invisivel.
    try {
        Remove-Item $stdoutLog, $stderrLog -Force -ErrorAction SilentlyContinue
        Start-Process $py -ArgumentList $srv, '--port', '8765' `
            -WorkingDirectory 'E:\Claude\apps\sketchup-mcp' -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog
    } catch {
        # fallback: log em uso por um processo agonizante -> lanca sem redirect
        L "redirect indisponivel ($_); lancando sem captura"
        Start-Process $py -ArgumentList $srv, '--port', '8765' `
            -WorkingDirectory 'E:\Claude\apps\sketchup-mcp' -WindowStyle Hidden
    }
    L "relaunched oracle"
}

function Oracle-Healthy {
    try {
        $r = Invoke-WebRequest 'http://localhost:8765/health' -TimeoutSec 4 -UseBasicParsing
        return ($r.StatusCode -eq 200 -and $r.Content -match '"oracle"')
    } catch { return $false }
}

Rotate-Log
$fails = 0
$consecRelaunch = 0
$firstCheck = $true
L "loop v3 START (py=$py, pid=$PID)"

while ($true) {
    if (Oracle-Healthy) {
        $fails = 0
        if ($consecRelaunch -gt 0) { L "estabilizou apos $consecRelaunch relaunch(es)" }
        $consecRelaunch = 0
        $firstCheck = $false
        Start-Sleep -Seconds 45
        continue
    }

    $fails++
    L "health DOWN (strike $fails)"
    # FAST-FIRST-LAUNCH: boot/login (1o check do loop) nao espera 2 strikes.
    $shouldLaunch = ($fails -ge 2) -or $firstCheck
    $firstCheck = $false
    if (-not $shouldLaunch) { Start-Sleep -Seconds 45; continue }

    # porta tomada mas /health nao-oraculo? -> impostor/zumbi: evicta antes.
    $c = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if ($c) {
        foreach ($op in ($c.OwningProcess | Select-Object -Unique)) {
            try { Stop-Process -Id $op -Force -ErrorAction Stop; L "evicted PID $op (porta tomada, /health nao-oraculo)" } catch { }
        }
        Start-Sleep -Seconds 2
    }

    Launch-Oracle
    Rotate-Log
    $fails = 0
    $consecRelaunch++
    if ($consecRelaunch -ge 3) {
        $err = ""
        try { $err = (Get-Content $stderrLog -Tail 3 -ErrorAction Stop) -join ' | ' } catch { }
        L "ALERTA: $consecRelaunch relaunches consecutivos sem estabilizar. stderr: $err"
    }
    # BACKOFF: 45s -> 90 -> 180 -> 300 (teto). Kill-loop infinito de 109s acabou.
    $sleep = [Math]::Min(45 * [Math]::Pow(2, [Math]::Max(0, $consecRelaunch - 1)), 300)
    Start-Sleep -Seconds $sleep
}
