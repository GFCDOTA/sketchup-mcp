# Regression Summary — planta_74

Verdict: IMPROVED

## SKP canônico atual (2026-06-04) — esquadrias de janela

**VISUAL_REVIEW = IMPROVED** (Felipe, 2026-06-04: "ficou daora demais").

### Mudança desta rodada — janelas viram esquadria de verdade
Antes as janelas eram "buraco + vidro plano". Agora:

1. **Janelas de quarto** (h_o008 2,06m / h_o010 1,80m): esquadria de **correr 2
   folhas** (moldura branca + montante central + vidro verde) + **caixa de
   persiana** branca no topo. Peitoril **1,10m** → verga 2,10m (janela 1,00m).
2. **Basculantes** (h_o007 / h_o009, 0,73m): **folha de vidro inclinada** abrindo
   pra fora (pivota no topo), peitoril alto **1,50m** → 0,60m de altura (quadrado),
   parede sólida abaixo. Carve só na altura do basculante (sem bloco de
   preenchimento). Folha num grupo separado (`WindowSash_Group`) pra não deslocar
   o centroide do vão no position_fidelity.

Tudo **perfil fixo** (não distorce em vão nenhum), calibrado pelos componentes do
3DW ("Janela 1/4" + "basculante") que o Felipe baixou — estilo replicado, tamanho
do PDF. **Largura/posição do PDF; altura/peitoril de norma** (pesquisa web).

### Mantido das rodadas anteriores
- **Guarda-corpo de vidro** na varanda (mureta + vidro + corrimão).
- **Notch-removal** (15 toquinhos das junções de parede).

### Fonte
- `tools/build_plan_shell_skp.rb` — `build_window_frame_h` (esquadria + persiana),
  `build_window_basculante_h` (folha inclinada), `build_window_aperture_3d` (carve
  condicional do sill por tipo); constantes `WINDOW_*` / `BASCULANTE_*` /
  `WINDOW_SILL_M=1,10`.
- `tools/run_skp_visual_review.py` — `_check_window_height` reconhece basculante
  (janela baixa legítima quando z_min ≥ 1,3m); não afrouxa pra janela normal.
- consensus **intocado** (composição é do builder).

### Gates
- deterministic gates: **PASS** (overall) — opening_host, wall_overlap,
  render_bbox, wall_presence, railing_match, parapet, position_fidelity.
- pytest: **365 green** (visual_oracle `bad_window_aperture` atualizado p/ basculante).
- canonical sha `53155bc6`.

### Evidência visual
- `artifacts/review/planta_74/janelas-esquadria/` (antes/depois + basculante).
