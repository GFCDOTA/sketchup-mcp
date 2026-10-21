# FP-045 — F0/F1: baseline reproduzível e reconciliação (snapshot datado)

**Data:** 2026-10-21 · **Commit:** `develop@2af60b0274356292f2b7f6dc7d869b9858f35e2b` · **Spec:** [FP-045](../specs/FP-045_specialists_knowledge_and_room_modularization.md) (PR #339)
**Escopo:** só leitura e medição. Nenhum código, fixture, canônico ou geometria foi alterado. L2/L3 **não** executados.

Este snapshot **complementa** — não substitui — [FP-043_final_validation](FP-043_final_validation.md) e
[FP-044_final_validation](FP-044_final_validation.md) (R-27): aqueles relatórios são registro histórico do dia em que foram escritos.

## 1. Reconciliação com o relatório FP-044

| Item | FP-044_final_validation (2026-10-20, F7) | Atual (`2af60b0`) | Origem da diferença |
|---|---|---|---|
| Fachadas soltas em `tools/*.py` | 15 | **14** | PR #337 moveu `_grid_sheet` para `tools/rooms/shared/contact_sheet.py` e removeu `tools/sofa_class_matrix.py` |
| D-012 (`bed_class` → living pela fachada) | aberta | **RESOLVIDA** | idem |
| D-007 (guarda-roupa sintético ~4,5 cm na parede) | aberta | aberta — diagnóstico no PR #338, correção **não** aplicada (afeta SUITE 02) | — |
| D-011 (4 fachadas lidas pelo `harness-app`) | aberta | aberta — exige PR no repositório do harness | — |

As 14 atuais (`tools/PUBLIC_API.md`): **8** públicas (`furnish_apartment`, `geometry_sanity`, `furniture_overlap_gate`, `finding_router`, `circulation_gate`, `correction_loop`, `spatial_model`, `room_type`) + **4** D-011 (`reference_db`, `rag_embed_backend`, `ollama_bridge`, `run_deterministic_gates`) + **2** por decisão do Felipe (`furnish_plan` D-003, `trace_view` D-004). Quando as 4 de D-011 saírem: 14 → 10.

## 2. Medidas reproduzíveis

| Medida | Valor | Como reproduzir |
|---|---|---|
| Blobs rastreados | 2.128 = 2.124 no inventário FP-042 + 4 `CONTROL_PATHS` | `python -m tools.rooms.inventory_gate --strict` |
| Perfis de especialista | 9 (18 JSON: `specialist.v1.json` + `knowledge/index.v1.json`) | `ls tools/rooms/*/specialist.v1.json` |
| Capabilities | 16: **3** `L2_PASS`, **12** `L1_PASS`, **1** `UNTESTED`; visual `NOT_REVIEWED` nas 16 | `python -m tools.rooms.capability_catalog` |
| Bindings | 15: 8 com capability, **7 sem** (`bind.kitchen.{shaker,drawer,countertop,sink-cutout}`, `bind.balcony.pergola`, `bind.closet.sliding`, `bind.home_office.desk`) | idem |
| Recipes | 8 de vídeo + 11 de ambiente, todas `KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP` | `references/sketchup/knowledge/*.v1.json` |
| Fontes de conhecimento | 3 de vídeo + 10 de ambiente; evidência: `OFFICIAL_DOCUMENTATION_READ` 7, `TRANSCRIPT_AND_VISUAL_WALKTHROUGH` 2, `PUBLIC_DESCRIPTION_ONLY` 3, `TRANSCRIPT_AND_DESCRIPTION_ONLY` 1 | idem |
| Tools MCP | 18 | `python -m tools.mcp_server.smoke` |
| CI no head | `success` nos 4 jobs (workflow `ci` #234) | GitHub Actions run 39415240475 |

## 3. Gates L1 executados neste snapshot (todos exit 0)

`inventory_gate --strict` · `ownership_audit` (99 arquivos, 0 violações; escopo `NEW_ROOM_PACKAGES_ONLY`, `legacy_migration_complete: false`) · `capability_catalog` · `p0_map --check` (190 itens) · `docs_check` · `asset_provenance` · `reference_provenance` · `run_deterministic_gates --fixture quadrado` e `--fixture planta_74` · `mcp_server.smoke` · `mcp_server.stdio_check` · `pytest -m "not planta74_scale"` (2.288 passed, 1 xfailed) · `PT_TO_M=0.0259 pytest -m planta74_scale` (111 passed).

Isto é **L1**. Prova de geometria no SketchUp (L2) e aparência (L3) permanecem como nos relatórios FP-043/FP-044.

## 4. Achados da validação da spec (corrigidos na spec v1.1.0)

1. A própria spec não estava no inventário FP-042 (R-11) → `UNREGISTERED_FILES` e 3 checks vermelhos no PR #339.
2. O payload de exemplo da spec dava `BLOCKED_TECHNIQUE_UNRESOLVED` em `specialists.plan`: `technique` casa com `binding.id`/`recipe_id`, e os inputs reais da capability são `dimensions.*` (+15 chaves).
3. `PENDING_VISION` não existe; o estado equivalente já no código é `PENDING_HUMAN`.
4. `inventory_gate` conta `tracked − CONTROL_PATHS`; qualquer doc novo precisa de linha no `fp042_inventory.v1.json` (e estar no índice do git antes do gate).

## 5. Próximas fases (ver spec §2.1)

| Fase | Estado | Bloqueio |
|---|---|---|
| F2 (D-011) | pendente | PR no `GFCDOTA/harness-app` |
| F3 (D-007) | pendente | afeta SUITE 02 → `VISUAL_REVIEW` do Felipe |
| F4 | guarda de proveniência em PR próprio (#340) | — |
| F5/F6/F7 | pendentes | F6 exige SketchUp real (L2) e, se muda aparência, L3 |
| F8 (D-002..D-005, D-008, D-009) | `BLOCKED_DECISION` | decisão do Felipe |
