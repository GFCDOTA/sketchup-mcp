# FP-043 / P3a-04 — material para a decisão D-001 (janela do `quadrado`)

**Isto NÃO decide nada.** Nenhuma referência, fixture ou asset protegido foi alterado; `fixtures/quadrado/` e `docs/specs/_assets/` intactos.
A decisão (A re-baselinar a referência / B alargar a janela / C caso especial) e o `VISUAL_REVIEW` são do Felipe.
Gerado no SketchUp 26.0.429 pelo cliente MCP real (`su_build_shell` → `su_inspect` → `su_render`), escala padrão do quadrado (sem `PT_TO_M`), fechado pelo PID.

| | Referência pinada (`quadrado_canonical_geometry_report.json`) | A — build atual (fixture inalterada) | B — janela de 36 pt ≈ 1,27 m (`consensus_option_B_wide_window.json`, só comparação) |
|---|---|---|---|
| Vidro (`WindowGlass_Group_win_south`) z | 0,90 – 2,10 m (1,20 m) | 1,50 – 2,10 m (0,60 m) | 1,10 – 2,30 m (1,20 m) |
| Vidro x | 4,991 – 6,046 m | 4,991 – 6,046 m | 4,885 – 6,152 m |
| Grupo `WindowSash` | ausente | presente (esquadria/basculante) | janela de correr de 2 folhas com caixa de persiana (regra de janela larga) |
| Resultado do teste condicional `test_quadrado_window_glass_group_exists` | — | **FAIL** (0,60 × 1,20 m) | não avaliado (precisaria da referência re-baselinada) |

Origem da divergência: regra de basculante aprovada em 2026-06-04 sobre a `planta_74` (janela horizontal ≤ 1,20 m → peitoril 1,50 m); a janela do `quadrado` (30 pt ≈ 1,06 m) cai nela por efeito colateral.
Imagens: `reference_canonical_success_render.png`, `A_current_{iso,top}.png`, `B_wide_{iso,top}.png`.
Observação: B muda `fixtures/quadrado/` (protegida) e perde a cobertura de janela estreita; A exige re-baseline da referência. Recomendação anterior (A) mantida, sujeita ao seu OK.
