# Regression Summary — planta_74

Verdict: IMPROVED

## SKP canônico atual (2026-06-03)

Dois fixes de fidelidade aprovados pelo Felipe (VISUAL_REVIEW = IMPROVED):

1. **Guarda-corpo do prédio real** — mureta de concreto na base (chão → 0,45m) + grade
   metálica em cima (0,45m → 1,10m), reproduzindo o "cimento embaixo da grade" da fachada.
   Materiais distintos (`plan_parapet` concreto / `plan_railing` metal).
2. **Notch-removal** — remoção de **15 corner-notches** (degraus de meia-espessura ~2,7pt)
   das junções de parede, os "toquinhos". `_remove_small_teeth` na `canonicalise`, **só
   dentes SIMÉTRICOS** (base reconectada fica axis-aligned, nunca diagonal). As **jambas de
   vão de porta** (assimétricas, laterais = largura da porta, em m015/m016/m018) foram
   **preservadas** — não são toquinhos, removê-las apagaria as bordas das portas.

### Gates
- deterministic gates: **PASS** (opening_host, wall_overlap, render_bbox, wall_presence
  sidecar_exact, railing, position_fidelity)
- pytest **365 verde**; 0 paredes tortas (axis-aligned mantido; micro-test verificado).

### Fonte
- `tools/build_plan_shell_skp.rb` — bloco `render_grade` (mureta + grade).
- `tools/build_plan_shell_skp.py` — `_remove_small_teeth` na `canonicalise_axis_aligned_polygon`.
- consensus intocado (composição é do builder).
