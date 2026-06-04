# Regression Summary — planta_74

Verdict: IMPROVED

## SKP canônico atual (2026-06-04) — janelas: esquadria + proporção

**VISUAL_REVIEW = IMPROVED** (Felipe, 2026-06-04).

### Esta rodada — proporção das janelas de quarto (1,80 × 1,20m)
Ajuste de altura/peitoril das janelas de dormitório, validado por consulta ao
GPT + foto real (tour Matterport da SUITE 02):
- Peitoril **1,10m** → verga **2,30m** → janela de **1,20m** de altura.
- SUITE 02 (h_o010, largura 1,80m do PDF) = **1,5:1**.
- SUITE 01 (h_o008, largura 2,06m do PDF) = 1,72:1 — mesma altura/peitoril; a
  largura é do PDF (não inventada).
- Verga do BASCULANTE separada (2,10m) → basculantes intocados (0,73 × 0,60m).

> **PREMISSA ARQUITETÔNICA PROVÁVEL** (não dimensão normativa obrigatória): a
> altura não consta no PDF; adotada por consulta ao GPT + prática de apto
> residencial médio-alto + referência visual da foto real. Largura/posição = PDF.

### Mantido das rodadas anteriores
- Esquadria de janela: correr 2 folhas (moldura + montante + vidro verde) +
  caixa de persiana; basculante com folha de vidro inclinada (banheiros).
- Guarda-corpo de vidro na varanda (mureta + vidro + corrimão).
- Notch-removal (toquinhos das junções de parede).

### Fonte
- `tools/build_plan_shell_skp.rb` — `WINDOW_SILL_M=1.10` / `WINDOW_HEAD_M=2.30`
  (correr 1,20m); `BASCULANTE_SILL_IN=1.50` / `BASCULANTE_HEAD_IN=2.10`
  (basculante 0,60m); `build_window_frame_h` / `build_window_basculante_h`.
- `tools/run_skp_visual_review.py` — `_check_window_height` reconhece basculante.
- consensus **intocado**.

### Gates
- deterministic gates: **PASS** (overall).
- pytest: **365 green**.
- canonical sha `301d3361`.

### Evidência
- `artifacts/review/planta_74/bedroom-window-ratio/` + `janelas-esquadria/`.
