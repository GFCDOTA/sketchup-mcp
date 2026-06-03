# Regression Summary — planta_74

Verdict: IMPROVED

## SKP canônico atual (2026-06-03)

Guarda-corpo da varanda reproduz o **prédio real** (Living Grand Wish): **mureta de
concreto na base** (chão → 0,45m) **+ grade metálica em cima** (0,45m → 1,10m), com
materiais distintos (concreto cinza-claro `plan_parapet` embaixo, metal escuro
`plan_railing` em cima). Felipe **VISUAL_REVIEW = IMPROVED** (gate PDF × ANTES × AGORA).

### Antes → Agora
- **Antes:** grade de balaústres do chão (0,03m) ao topo (1,10m), sem base sólida.
- **Agora:** o `h_sb000` (peitoril `render_as=grade`) gera mureta sólida na base +
  grade metálica acima — o "cimento embaixo da grade" do prédio.

### Geometria / gates
- deterministic gates: **PASS** (opening_host, wall_overlap, render_bbox,
  wall_presence sidecar_exact, railing, position_fidelity)
- `_drop_coincident` + IDs únicos (m020) preservados do rebuild anterior.

### Fonte
- builder: `tools/build_plan_shell_skp.rb` — bloco `render_grade` (mureta + grade).
- consensus: `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`
  (intocado; `h_sb000` segue `render_as=grade`, a composição é do builder).
