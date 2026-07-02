# FP-040: Hardening do bridge :8765 — de "vivo hoje" a "confiável a noite inteira"

> O `:8765` é o host do OLHO (FP-032 `/ask-vision`), do gate de decisão (LL-024)
> e o heartbeat-sink do loop de correção (FP-033). Todo o eixo autônomo
> (turno-da-noite, FP-034 sweep, NOC) assume ele de pé. Esta spec transforma o
> diagnóstico medido do kill-loop em fixes com gate de aceite honesto.

## Problem (medido, não anedota)

`ops\bridge\watchdog.log` (2026-06-05 → 2026-07-01, 27.561 linhas, 1,2 MB):

- **16.753 `health DOWN` e 10.743 `relaunched oracle` em 27 dias** (~400/dia).
  Pico 2026-06-10: 1.937 DOWNs ≈ **13h de indisponibilidade num único dia**.
- Padrão: **episódios de kill-loop** com cadência exata de ~109s (strike1 →
  +49s strike2 → relaunch → morre → repete) por HORAS, terminando só por
  intervenção manual (PARAR/SUBIR-NOC), nunca por auto-recuperação.
- **`EVICTED=0` no log inteiro** → o server relançado MORRE antes de bindar a
  porta (não é zumbi nem porta tomada; é morte no startup).
- **Watchdogs DUPLICADOS**: pares de `loop v2 START` no mesmo segundo com PIDs
  distintos (06-27 2×, 06-28, 06-30) — dobra relaunches e cria corrida na porta
  (`allow_reuse_address=False`).
- Spawn **cego**: o launch descartava stdout/stderr (`-WindowStyle Hidden`, sem
  redirect) → motivo da morte invisível por 27 dias.

## Root causes (confirmadas)

1. **Windows Defender ThreatID 2147941383** (detector COMPORTAMENTAL de
   `powershell.exe -ExecutionPolicy Bypass ...`) matando spawns — diagnóstico em
   `.ai_bridge/HANDOFF.md` §"Gate :8765 STALE (AV)" + memória
   `reference_av_defender_powershell_flag`. O recurso flagado é a LINHA DE
   COMANDO, não um arquivo → exclusão de path sozinha não cobre.
2. **Topologia de autostart triplicada** (Startup do usuário):
   `claude-gate-autostart.cmd` E `gate-watchdog.cmd` lançavam AMBOS o
   `gate-watchdog-loop.ps1` (→ 2 keepers por login), e `claude-bridge.cmd`
   subia um TERCEIRO server inline via `ops\bridge\start.ps1`, correndo com o
   watchdog pela porta no login.
3. **Sem singleton**: o loop escrevia o pid file mas não checava instância viva
   → a 2ª instância sobrescrevia o pid e as duas rodavam pra sempre.
4. **Sem backoff**: relaunch a cada ~109s pra sempre (1,2 MB de log é o sintoma).
5. `gate-watchdog.ps1` (estilo Scheduled Task, health check fraco só-200,
   timestamps sem data) — a task `SketchUpCreatorGate` NÃO existe mais
   (verificado 2026-07-01); o script ficou órfão.

## Fixes

| # | Fix | Estado | Quem |
|---|---|---|---|
| 1a | Exclusões Defender **Tier A** (`E:\Claude` path) + **Tier B** (`python.exe` da venv) | ✅ APLICADO 2026-07-01 (Felipe, admin) | Felipe |
| 1b | **Tier C** (`powershell.exe` ExclusionProcess) — o único que cala o 2147941383 no spawn do próprio watchdog; tradeoff LOLBin | ⏳ decisão do Felipe; **gatilho = churn voltar no log** | Felipe |
| 2 | **Riser único**: manter só `Startup\gate-watchdog.cmd`; `claude-gate-autostart.cmd` (duplicata) e `claude-bridge.cmd` (3º riser) → `archive\startup-disabled-2026-07-01\` (arquivar > deletar) | esta sessão | sessão |
| 3 | **Watchdog v3** (`tools/claude_bridge/gate-watchdog-loop.ps1`, fonte de verdade NO REPO; deploy = cópia pro ops): singleton por pid-file+commandline; fast-first-launch (boot não espera 2 strikes — cobre o gap deixado pelo fix 2); stdout/stderr do spawn capturados em `server-{stdout,stderr}.log`; backoff 45→300s + linha ALERTA com o stderr; rotação do log em 512KB; token BOM-safe | esta sessão | sessão |
| 4 | **Identidade de build no `/health`** (`server_sha12` + `server_mtime` do server.py servido) — distingue "vivo mas velho" de saudável; mata o deploy-invisível | esta sessão | sessão |
| 5 | Arquivar `gate-watchdog.ps1` órfão (task morta; health check fraco poluía o log) | esta sessão | sessão |

## Non-goals

- **NÃO** tocar no `noc-watchdog-loop.ps1` (keeper do ATUADOR — outro processo,
  legítimo, escopo do turno-da-noite job 4).
- **NÃO** ativar o Tier C pela máquina — é postura de segurança da máquina
  inteira; decisão exclusiva do Felipe (o script deixa comentado de propósito).
- **NÃO** mover o server pra Serviço do Windows/NSSM nesta fatia (mudança de
  operação maior; só se o v3 + exclusões não estabilizarem).
- **NÃO** mexer na semântica do gate (tiers, modo B, SKIPPED_OFFLINE intactos).

## Deploy & verificação (procedimento seguro)

1. Repo: landar spec + watchdog v3 + `/health` build-id na develop (FF).
2. `git restore --source=develop --worktree -- tools/claude_bridge/server.py`
   no MAIN (só o arquivo; trabalho alheio intocado — padrão do deploy FP-032).
3. Copiar o watchdog v3 do repo → `ops\bridge\gate-watchdog-loop.ps1`.
4. Arquivar os 2 autostarts redundantes + o `gate-watchdog.ps1` órfão.
5. Swap ao vivo: `Stop-Process` no keeper velho (pid do `gate-watchdog.pid`) →
   subir o v3 destacado (mesmo comando do `gate-watchdog.cmd`) → **prova do
   singleton**: lançar uma 2ª instância e ela DEVE sair sozinha logando
   `singleton: instancia N ja viva`.
6. `Stop-Process` no server :8765 → v3 relança → `/health` novo mostra
   `server_sha12` do build landado + `server-stderr.log` existe (spawn capturado).

## Acceptance (honesto — o log é a prova, não exit 0)

| Critério | PASS | FAIL |
|---|---|---|
| Singleton | 2ª instância sai sozinha com log `singleton:` | duas instâncias em paralelo |
| Spawn observável | morte de spawn deixa stderr legível em `server-stderr.log` | morte silenciosa |
| Deploy visível | `/health.server_sha12` == sha do arquivo servido | deploy invisível |
| Anti-runaway | episódio de falha → backoff crescente + ALERTA no log | cadência fixa ~109s infinita |
| **Estabilidade (o gate real)** | **≥7 dias de `watchdog.log` sem episódio de churn (>3 relaunches/h)** | qualquer episódio → investigar; se assinatura Defender → ativar Tier C (Felipe) |
| Topologia | exatamente 1 keeper do gate por login | keeper duplicado no log |

## Reference

- Diagnóstico completo: sessão 2026-07-01 (leitura integral do watchdog.log) +
  `.ai_bridge/HANDOFF.md` §AV + memória `reference_av_defender_powershell_flag`.
- Launchers: `Startup\gate-watchdog.cmd` (riser único) · `ops\launchers\subir-noc.ps1`
  (SUBIR-NOC manual) · `ops\launchers\add-defender-exclusions.ps1` (Tiers A/B/C).
- Consumidores que assumem o :8765 de pé: FP-032 (`/ask-vision`), FP-033
  (heartbeat), LL-024 (gate), turno-da-noite (`.claude/specs/autonomous_planta_prep.md`).
