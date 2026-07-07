# Autonomous Planta Prep — o "turno da noite" (2026-06-29)

> Doutrina: o que o sistema pode processar SOZINHO (sem sessão Claude interativa) pra
> deixar a planta adiantada. Mapeado lendo o código + rodando de verdade. Princípio
> inegociável: **todo job de fundo só PREPARA evidência; o veredito visual
> (IMPROVED/SAME/WORSE) é SÓ do Felipe/GPT, nunca da máquina.**

## Verdade honesta — real × stub (estado em 2026-06-29)

### ✅ REAL hoje (roda sozinho, provado)
- **Suite determinística headless** (sem SketchUp, sem rede, sem PDF): `run_deterministic_gates.py`
  (provei `planta_74` → `overall=PASS`, opening_host 0/12, wall_overlap 0). Junto:
  `geometry_sanity.py`, `furniture_overlap_gate.py`, `kitchen_validation.py`,
  `position_fidelity_gate.py`, `opening_host_audit.py`, `wall_overlap_audit.py`. Idempotentes.
- **`regenerate_consensus.py`** — merge de paredes colineares + re-host de aberturas; escreve
  CANDIDATO em `runs/`, **nunca sobrescreve a fixture**.
- **Atuador `noc_dispatcher.py`** — REAL e já AGIU (ledger `.ai_bridge/noc/actions.jsonl` tem
  T1/T2 `COMMITTED`): pega task segura da fila → worktree off `develop` → `claude -p` isolado →
  verify → commit+push de BRANCH (NUNCA `main`); aparência → enfileira `VISUAL_REVIEW`.
- **Ollama VIVO** com todos os modelos do pipeline (deepseek-r1:14b, llama3.1:8b, qwen2.5-coder,
  interior-designer) → `architect_program.py` (propor mobiliário) e `kind:local_llm` rodam a custo-zero.
- **`reference_db`** (SQLite) indexa referências por cômodo/tema; **`render_parts_iso.py`** faz
  pré-check de proporção de móvel SEM SketchUp.

### ❌ STUB / parado (NÃO chamar de pronto)
- **Cockpit runner (:8782) = STUB TOTAL.** `cockpit_api.py` `_runner()` só faz `time.sleep` +
  logs FAKE + falha pseudo-aleatória no step `verify`; auto-marcado `stub=True`. NÃO chama build,
  NÃO dispara gate, NÃO gera render. `/api/.../run` é vidro com teatro atrás.
- **Oráculo :8765 — UPDATE 2026-07-01: VIVO, com `/ask-vision` LIGADO (FP-032 deploy).** O
  crash-loop por BOM descrito abaixo foi CONSERTADO (job 0 ✅). Instabilidade RESIDUAL: episódios
  de kill-loop por **Windows Defender** (ThreatID 2147941383) matando spawns
  `powershell -ExecutionPolicy Bypass` do watchdog — 16.753 DOWNs / 10.743 relaunches em 27 dias
  (diagnóstico no watchdog.log; agravante: 2 watchdogs em paralelo, sem singleton). Exclusões
  Tier A/B aplicadas 2026-07-01; Tier C (powershell.exe) pendente de decisão do Felipe; hardening
  formal (singleton, observabilidade de spawn, backoff, task legada) = spec FP-040 a escrever.
  [Diagnóstico original de 2026-06-29, mantido como histórico:] Causa-raiz CONFIRMADA:
  `ops/bridge/.oauth_token` tinha **BOM UTF-8** (`ef bb bf`) e o `gate-watchdog-loop.ps1` fazia só
  `.Trim()` (não tira BOM) → Bearer corrompido → `claude -p` não autenticava → `/health` nunca
  passava → relançava a cada ~49s.
- **`noc-watchdog` (keepalive do atuador) = PARADO** (última sweep 2026-06-09). Sem ele a fila
  NOC não é drenada — o atuador real fica inerte.
- **`broker.py` (auto-respondedor) = nunca rodou em produção** (só 1 selftest 2026-05-30).
- **Ninguém enche a fila NOC automaticamente** (sem git hook, sem scheduled task). Tráfego = zero.
- **`autonomous-fidelity-loop`** é skill REAL mas invocada por uma sessão Claude, não é daemon.
- `ops/bridge/{broker,server}.py` vivem FORA do git (sem CI/audit) — risco operacional.

## Detection — a gotcha-raiz do :8765
```
head -c 3 ops/bridge/.oauth_token | xxd   # ef bb bf  → BOM presente
```
`.Trim()` em PowerShell remove whitespace, NÃO o BOM. O Bearer vira `﻿<token>` → 401.

## Night-shift design (ROI decrescente)

| # | Job | Sem SU? | Pré-estagia | Trigger | Esforço |
|---|---|---|---|---|---|
| 0 | ✅ **FEITO 2026-07-01** — oráculo :8765 reparado E estendido (`/ask-vision` vivo, FP-032; discriminação provada em produção) | ✓ | destravou o eixo autônomo (gate/NOC/broker + OLHO) | — | — |
| 1 | **Pre-flight de planta**: roda a suite determinística por fixture → `runs/preflight/<plant>.json` com PASS/FAIL itemizado | ✓ | Claude já sabe SE passa e ONDE falha, sem gastar ciclo; verde = pré-req do VISUAL_REVIEW | watcher no `consensus_*.json` / cron | baixo |
| 2 | **Indexador de referência**: watchdog em `artifacts/reference_lab/` → `reference_db ingest` (idempotente por sha256) | ✓ | referência já indexada por cômodo/tema; tira o "architect_blocked por falta de ref" | FileSystemWatcher / cron leve | baixo |
| 3 | **Watcher de consensus**: ao detectar parede fragmentada, roda `regenerate_consensus.py` → candidato em `runs/` + gates nele + diff (X→Y paredes). NUNCA promove | ✓ | consensus reparado-candidato + relatório esperando; Claude só decide promover (após visual) | watcher mtime / NOC `kind=consensus-repair` | médio |
| 4 | **Wirar a fila NOC**: botão/endpoint no cockpit que ESCREVE task em `queue.jsonl` (só kinds SEGUROS: docs, fixture-regen-candidate, summarize_log, gate-run) + religar o `noc-watchdog` | ✓ | tarefas determinísticas viram BRANCHES prontas pra revisar/mergear | cockpit-button + noc-watchdog (já existe) | médio |
| 5 | **Pré-propor mobiliário** com Architect local (Ollama): pros cômodos com ref curada, `architect_program.propose_and_save` + `auditor` → `proposals/pending/*.json` | ✓ | Felipe chega e já tem propostas + gaps esperando curadoria; token=0 | após indexador / NOC `kind=local_llm` | médio |

## Night-shift narrative (com o que existe + jobs 0 e 4)
22:00 reparo do bridge (job 0) → :8765 vivo · 22:10 pre-flight determinista por planta ·
22:20 candidato de consensus reparado + diff · 22:40 referências indexadas · 23:00 propostas de
mobiliário locais (token 0) · 23:30 fila NOC drenada → branches commitadas. **Manhã:** Claude
encontra vereditos por planta, consensus-candidato, refs indexadas, propostas + gaps, branches pra
revisar. **Nenhuma decisão visual foi tomada pela máquina.**

## Hard rails (quebrar = RED)
1. **Candidato ≠ canônico.** `regenerate_consensus`/`architect` produzem CANDIDATOS em `runs/`.
   Fixture só muda com `VISUAL_REVIEW` humano (Constitution Hard Rule #3). Nunca auto-promover.
2. **Veredito visual nunca vaza pra job de fundo.** `negative_dogfood` provou que auto-veredito
   visual é não-confiável. Job só prepara evidência.
3. **Worker NOC: proibido `main`/`merge`**, worktree isolado, lock TTL, verify antes de manter,
   só kinds comprovadamente seguros.
4. **Sem o :8765 vivo, não wirar a fila** — qualquer job com `claude -p` falha por auth.
   (2026-07-01: :8765 vivo ✅; pré-condição satisfeita ENQUANTO o hardening FP-040 não regride.)

## Recommended first
~~Job 0~~ ✅ feito (2026-07-01). **Próximos: Job 1 (pre-flight determinístico) + Job 4 (wirar a
fila NOC)** — e o motor pros kinds seguros JÁ EXISTE: `tools/correction_loop.py` (FP-033, landado
2026-07-01) roda DETECT→CLASSIFY→FIX→RE-CHECK sem sessão, com candidata no `--out` e aparência
sempre em `VISUAL_REVIEW_QUEUED`. Job 4 = enfileirar `kind=correction_cycle` + religar noc-watchdog.

## Reference
- NOC dispatcher / bridge: memória `reference_noc_dispatcher`, `reference_sketchup_cockpit_gate`
- Gotcha do BOM: `.claude/specs` / `security.md` (utf-8-sig mata o Bearer)
- Loop autônomo: `.claude/skills/autonomous-fidelity-loop/SKILL.md`
- Veredito visual humano: `.claude/specs/room_furnishing_method.md`
