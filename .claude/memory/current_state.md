# Current state — sketchup-mcp

> **Snapshot:** 2026-10-18. Verificar com `git`/`gh` antes de agir em
> decisões remotas — este arquivo decai rápido.

## Branch base & release

`develop` é a integration branch. `main` só recebe `develop` via merge
(Hard Rule #4 — nunca commitar/push direto em `main`).

- **`develop`** — último merge funcional = PR #249 (`ba91c03`, 2026-10-18).
- **`main`** — recebe este estado no release `develop -> main` de 2026-10-18
  (o 2º do dia; o 1º foi `09d9321`). Conferir com
  `git diff --quiet origin/main origin/develop`.
- **CI** (`.github/workflows/ci.yml`, jobs `pytest` [3.11+3.12] ·
  `fidelity-gates` · `mcp-server`) **verde** em `develop`.
- **Suíte:** 126 arquivos de teste. Medido 2026-10-18 (py3.13):
  `-m "not planta74_scale"` = **1521 passed, 9 skipped**;
  `PT_TO_M=0.0259 -m planta74_scale` = **74 passed**
  (skips = precisam de SketchUp ou Qdrant/Ollama).

## O que landou em 2026-10-18 (Gate A — fechamento dos PRs)

- **#248** docs de memória (`current_state`/`active_work`/`next_actions`).
- **#247** brain do cômodo SERVICE + `.skp` mobiliado regerado — VISUAL_REVIEW
  aprovado pelo Felipe na conversa.
- **#249** especialista SketchUp no MCP: 9 tools `su_*` em `tools/sketchup/`
  (status/open/close/inspect/render/apply_edits/build_shell/furnish/render_vray).
  **`proof_state = UNVERIFIED_ON_SKETCHUP`** — nada rodou num SketchUp real
  (checklist no corpo do PR). `su_render_vray` RECUSA até o launcher legado
  (`taskkill /F /IM`) ser portado. Passou por 3 rodadas de revisão adversarial.
- **#250** porta os 2 bugs reais do #245: cadeira fantasma no
  `circulation_gate` (agora 1 entrada por box `kind="seat"`) e `kb_lixeira`
  dentro do vaso em BANHO 01/02 (removida; **VISUAL_REVIEW** na próxima
  regeneração do furnish — os 2 banhos ficam sem lixeira).
- **#245** fechado como superado (11 de 13 mudanças já estavam no develop;
  `d09da3d` quebrava 5 testes da escala default).
- **FP-041** (SketchUp Tooling Specialist Agent): plano rev. 3 aprovado
  arquiteturalmente; **Gate B (implementação) NÃO autorizado ainda**.

## O que landou desde o último snapshot (jul/07 → set/20)

- **NOC/cockpit `:8765` APOSENTADO** (`4ddfaf7`, pedido do Felipe 2026-07-24)
  — saíram `claude_bridge` server, dispatcher/feeder/curation, dashboards
  (`:8782`) e vitrine. **Oráculo de decisão agora = GPT-Docker `:8899`**
  (`ops/gpt-docker/`, skill `gpt-docker-consult`). Ficaram: stack de visão,
  todo o RAG/write-back, `_paths`/`skp_inventory`. Lições em
  `E:\Claude\LESSONS-NOC.md`.
- **Estúdio / Ateliê 74** — `ops/estudio-front/` (:8788) com chat RAG de
  preferências + `knowledge_ingest.py`; merge `feat/estudio-banheiro`.
- **Domínio compartilhado** (PR #243) — `core/domain/` (ids, contratos,
  `retrieval_trace`, `room_registry`).
- **Contrato semântico de geometria** — `core/spatial_semantics.py`
  (`geometry_intent`/`shape_policy`/`interaction_policy`) +
  `core/project_policy.py` (`NumericPolicy`) + 3 gates novos
  (`semantic_geometry_contract_gate`, `collision_envelope_gate`,
  `optimizer_consistency_gate`). ADR `docs/adr/0001-*`.
- **CI 100% verde** (ago/11-12) — teto `mcp<2.0`, `PT_TO_M` por invocação,
  bugs reais em `circulation_gate`/`bed_placement_gate`/`geometry_sanity`.
- **AI Pipeline Inspector** (PR #246) — `core/observability/` (eventos JSONL
  v1, taxonomia RAG derivada, sink, redact, replay; desligado por padrão,
  `INSPECTOR=1` liga). Spec + ADR-001 em `docs/specs/AI_PIPELINE_INSPECTOR.md`.
  O host desktop (JavaFX + React) **saiu para repo próprio**
  `GFCDOTA/harness-app` (consome `.ai_bridge/traces/*.jsonl`).

## PRs abertos (2026-10-18)

Nenhum em `sketchup-mcp` nem em `harness-app` depois do Gate A.

## Programa anterior — FP-032 → 040 (jun/28 → jul/04)

Stack autônomo de melhoria de planta, sob a regra dura: máquina emite
`findings` tipados + roda gates determinísticos; veredito estético
`IMPROVED/SAME/WORSE` continua **só do Felipe** (VISUAL_REVIEW).

- **FP-032 Vision ACL** — rota `/ask-vision` no `:8765` (servidor
  aposentado em jul/24; a stack de visão ficou).
- **FP-033 Correction Loop** (live) — detect→classifica→conserta o
  determinístico→re-checa; aparência sobe pro Felipe.
- **FP-034 Variant Sweep** (live) — eixos tipados + varredura SU-free +
  corpus julgado (nunca fabrica veredito → `PENDING_VISION`).
- **FP-035 RAG de design** — landou: `reference_db.retrieve()` +
  `DesignSpecBundle.v1` injetado no prompt do arquiteto + freshness guard +
  backend embed Qdrant/Ollama (FP-037 Camada 1-2).
- **FP-036/037/038 Material de verdade** (done) — textura real por peça no
  `.skp` + material por (família, peça) + câmera de prova por cômodo.
- **FP-039 Fingerprint honesto v2** (done) — tiers reliable/advisory/forbidden.
- **FP-040 Bridge hardening** / **Night loop** (`night_feeder`,
  `variant-vision-drain`) — **removidos** junto com o `:8765` (jul/24).

## Baselines estáveis (não retrabalhar)

- **planta_74 canonical:** `artifacts/planta_74/planta_74.skp` (shell,
  escala `PT_TO_M=0.0259` travada 09/jun) + renders + report. Deliverable.
- **planta_74 mobiliada:** `artifacts/planta_74/furnished/planta_74_furnished.skp`
  (textura madeira no rack/mesa, FP-037, 01/jul).
- **quadrado canonical**, **runs/ vs artifacts/ convention**,
  **`--mode headless` proibido em dev local**, **opening routing invariants**
  pinados (4 windows / 7 doors / 1 glazed_balcony / 8 carves), **Constitution
  + #8 No-SKP-no-progress**.
- **`ops/latest/` (workspace)** espelha o último `.skp` gerado (hook Stop).

## Problemas abertos

- **Room fidelity = WARN** para `planta_74`: 8 cells fechadas vs 11 ambientes
  semânticos (open-plan funde r001/r002) — geometricamente honesto, não
  inventar paredes. Overlay `semantic_zones` landou (jul/06); validação
  end-to-end precisa de SketchUp (não disponível em sessão remota).
- **DIFF-001** (consensus = autoria humana, sem extrator PDF→consensus, HIGH)
  — DEFERRED/roadmap (M4).
- **Branches remotas soltas:** `backup/stash-0..4` (sem PR) — decidir
  arquivar/deletar com o Felipe.

## TODO — verificar live

- [ ] `git worktree list` — confirmar agentes ativos ANTES de op de
      branch/worktree (o tree principal `E:/Claude/apps/sketchup-mcp` pode
      estar em branch stale; ler fonte-da-verdade via `git show develop:<path>`).
- [ ] GPT-Docker `:8899` → `/health` antes de rotear decisão pelo gate.
