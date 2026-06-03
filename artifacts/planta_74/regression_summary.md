# Regression Summary — planta_74

Verdict: IMPROVED

## SKP canônico atual (2026-06-03) — guarda-corpo de VIDRO

**VISUAL_REVIEW = IMPROVED** (Felipe, 2026-06-03: "achei o DEPOIS melhor").

### Mudança desta rodada
Guarda-corpo da varanda trocado de **grade de balaústres densos** (parecia
cerca de ferro) para **guarda-corpo de vidro**, replicando o componente
"Peitoril de vidro" do 3D Warehouse que o Felipe baixou:

1. **Painel de vidro** translúcido azulado — material `plan_glass`,
   cor `[124,138,181]`, alpha `0.45` (extraídos do .skp do 3DW por inspeção).
2. **Montantes tubulares** metálicos espaçados (~1,0m).
3. **Corrimão** de cano no topo (1,02m → 1,10m).
4. **Mureta** de concreto na base preservada (chão → 0,45m, aprovada antes).
5. Altura total **1,10m** (PDF).

O componente do 3DW **não** foi importado cru — vinha com uma figura de
escala ("Sree", boneco padrão do SketchUp) + duplicado em 2 trechos +
montantes a 0,84m. Foi usado como **molde**: bounds/material extraídos por
inspeção (`autorun_inspector` + `.claude/scratch/inspect_peitoril.rb`), e o
estilo replicado **proceduralmente** seguindo a polilinha real da varanda.

### Mantido das rodadas anteriores
- **Notch-removal** — 15 corner-notches (toquinhos) removidos das junções; só
  dentes SIMÉTRICOS (base fica axis-aligned). Jambas de vão de porta
  (m015/m016/m018) preservadas. (`_remove_small_teeth` no `.py`.)

### Fonte
- `tools/build_plan_shell_skp.rb` — `build_soft_barrier` bloco `render_grade`
  (corrimão + painel de vidro + montantes); material `plan_glass`; constantes
  `GLASS_THICK_IN` / `GLASS_RGB` / `GLASS_ALPHA` / `GRADE_POST_SIZE_IN` /
  `GRADE_POST_SPACING_IN`.
- consensus **intocado** (composição é do builder).
- canonical before = grade (sha 7c645074) → after = vidro (sha 10af9940).

### Gates
- deterministic gates: **PASS** (overall) — opening_host, wall_overlap,
  render_bbox, wall_presence (sidecar_exact), railing_match, parapet_fallback,
  position_fidelity.
- geometry_report diff BEFORE→AFTER: **idêntico** (walls=20, openings_carved=8,
  window_apertures_3d=4, gates_self_check todos True, groups iguais). A troca
  grade→vidro acontece **dentro** do `SoftBarrier_Group`; nada estrutural mudou.
- pytest: **364 passed / 5 skipped / 1 failed**. A falha
  (`test_dashboard_html_serves_the_spa`) é **pré-existente e não-relacionada**
  (dashboard/cockpit, não o builder). O `.rb` não é exercitado por pytest; o
  Python ficou intocado nesta mudança.

### Evidência visual
- BEFORE (grade) vs AFTER (vidro): `artifacts/review/planta_74/glass-railing-3dw/`.
- Render canônico: `artifacts/planta_74/planta_74_iso.png` / `_top.png`.
