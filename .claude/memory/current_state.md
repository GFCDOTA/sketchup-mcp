# Current state — sketchup-mcp

> **Snapshot:** 2026-10-22. Decai rápido — conferir com `git`/`gh` antes de agir em decisão remota.
> Retrato completo e próximos passos: `docs/handoffs/2026-10-22_general_app_handoff.md`.
> Fila de trabalho do core de construção: `docs/specs/construction_core_microphases.md`.

## Branch base & CI

- `develop` @ `a87d2ad` (merge do #355). `main` recebe `develop` só via merge de release.
- CI obrigatório (4 checks): pytest 3.11, pytest 3.12, deterministic fidelity gates, mcp server smoke+stdio.
- Suíte (2026-10-22): `-m "not planta74_scale"` 2555 passed / 30 skipped / 1 xfailed; `PT_TO_M=0.0259 -m planta74_scale` 146 passed.

## O que existe e está provado

- **Arquitetura:** `artifacts/planta_74/planta_74.skp` (shell, escala `PT_TO_M=0.0259` travada) e a versão mobiliada
  `artifacts/planta_74/furnished/planta_74_furnished.skp` — canônicos, protegidos.
- **Módulos por cômodo** (`tools/rooms/<cômodo>/` + `shared/`), ownership e imports cruzados travados no CI (FP-041→045).
- **Especialistas fail-closed:** `specialists.plan()` → binding → capability → `PLAN_READY_NOT_EXECUTED` ou `BLOCKED_*`.
- **5 capacidades L2** (SketchUp 26.0.429): `kitchen.layout.galley`, `shared.cabinet.parametric`, `kitchen.cabinet.plain-fronts`,
  `kitchen.cabinet.shaker-door` (refeita no #358, `4023b78`), `shared.cabinet.front.shaker`. As outras 13 são L1/UNTESTED.
- **Regressão por cômodo** (FP-047 F1–F3), **placement L1 da cozinha** (FP-050, piloto não integrado),
  **contrato de alvo por móvel** (FP-052 T0–T1, piloto `DRAFT_BLOCKED`).
- **Aparência:** nada aprovado em L3 (18 × `NOT_REVIEWED`). Pacote da Shaker aguardando o Felipe (#356).

## Sessão de reorganização (2026-10-22, PRs #360–#369)

- #360 instruções do agente (CLAUDE.md com imports consertados, `.claude/rules/`, 22 skills) · #361 handoff geral + mapa de
  microfases · #363 **T0.1**: prova L2 cobre o fecho transitivo (`closure_digests`, `EVIDENCE_CLOSURE_STALE`) ·
  #364 imports do código vivo zerados + handoff por arquivo (`docs/reports/file_audit/`) · #365 índice dos cômodos na raiz ·
  #366 **fragmentos de especialista** (20, em `tools/rooms/<cômodo>/fragments/`) · #367 SOLID: `shared/parts.py` ·
  #368 raiz: D-002/D-005 executadas + "O que mora na raiz" · #369 desempenho: snapshot 5,25 s → 2,84 s, saída idêntica.
- Ferramentas novas: `tools.navigation.{register_evidence,file_audit,rooms_index,builder_detail_audit}`,
  `tools.rooms.{evidence_closure,specialist_fragments}`.

## Problemas abertos conhecidos

- Builders Gen1 (guarda-roupa, cama, sofá, rack, mesas) com medidas embutidas; guarda-roupa com corpo em um bloco.
- Circulação da SUITE 01 reprova antes e depois (preexistente, #351); D-007 (vão = laje) muda a SUITE 02 → decisão do Felipe.
- `cabinet.sketchup.inspect` grava scratch ao lado do `.skp` de entrada (T0.2).
- Room fidelity WARN na planta_74 (8 células × 11 ambientes, open-plan) — honesto, não inventar paredes.

## Oráculos

NOC `:8765` removido (2026-07-24). GPT-Docker `:8899` dormente. Veredito visual: Felipe, no chat.
