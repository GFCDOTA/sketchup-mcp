# FP-056 P3b — o pré-voo vê a varredura real da folha (R5) (2026-10-24)

Parte técnica da #435 (a decisão visual é a #486, não aplicada). `room_collisions.audit` ganhou `door_sweep_hits`: peça —
inclusive tapete (`SOFT`) e acabamento de piso — dentro da **varredura real** da folha (união da folha de 4 cm de 0° a 90°, a
mesma geometria do movimento que o validador do construído mede). A folha é construída de z = 0 a 2,10 m, sem folga inferior,
então nenhum acabamento é "caminhável" para ela.

- O quarto de círculo antigo (`door_swings_pt`) é menor que a varredura (0,398 × 0,427 m² na h_o003) e o pré-voo isentava topo ≤ 2 cm:
  o conflito só aparecia no gêmeo/SketchUp. O antigo `door_swing_hits` ficou como estava.
- Medido na planta_74: exatamente 2 achados, `h_o003|rug` (516 cm²) e `h_o004|rug` (2559 cm²) — os R5 do baseline (49° e 16°).
- Baseline conhecido: `docs/governance/known_gaps.json: door_sweep` (Issue #486). O pré-voo passa com esses dois; **peça nova na varredura
  reprova**; o gate de geometria reprova registro que não existe mais (limpar quando a #486 for decidida).
- Não muda geometria, layout, limiar nem catálogo L2. Aparência: `PENDING_HUMAN`.
