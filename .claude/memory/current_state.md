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

## Problemas abertos conhecidos

- Builders Gen1 (guarda-roupa, cama, sofá, rack, mesas) com medidas embutidas; guarda-roupa com corpo em um bloco.
- Digest do R-18 só cobre o corpo da função listada (fecho transitivo fora) — microfase T0.1.
- Circulação da SUITE 01 reprova antes e depois (preexistente, #351); D-007 (vão = laje) muda a SUITE 02 → decisão do Felipe.
- `cabinet.sketchup.inspect` grava scratch ao lado do `.skp` de entrada (T0.2).
- Room fidelity WARN na planta_74 (8 células × 11 ambientes, open-plan) — honesto, não inventar paredes.

## Oráculos

NOC `:8765` removido (2026-07-24). GPT-Docker `:8899` dormente. Veredito visual: Felipe, no chat.
