# Visual Fidelity Mismatches — PR B1 template

- generated_at: `2026-05-14T02:57:22Z`
- consensus_path: `fixtures\planta_74\consensus_with_human_walls_and_soft_barriers.json`
- walls: 35
- rooms: 8
- openings: 12
- soft_barriers: 9

> **Status:** PR B1 template. Every check below starts at `not_yet_checked`. PR B3 (`tools/visual_fidelity_gate.py`) fills these in with `pass` / `fail` + per-element IDs.

## Eight failure conditions

- [ ] **door_without_opening** — Door drawn without a real opening in its host wall.
  - status: `not_yet_checked`
  - failing_elements: `[]`
  - notes: _populated by PR B3._

- [ ] **door_crossing_or_displaced** — Door crossing the wall (no carve) or displaced from the gap.
  - status: `not_yet_checked`
  - failing_elements: `[]`
  - notes: _populated by PR B3._

- [ ] **door_swing_diverges** — Door swing / orientation diverges from the PDF arc.
  - status: `not_yet_checked`
  - failing_elements: `[]`
  - notes: _populated by PR B3._

- [ ] **room_polygon_not_closed** — Room with a non-closed polygon.
  - status: `not_yet_checked`
  - failing_elements: `[]`
  - notes: _populated by PR B3._

- [ ] **room_polygon_bleeds_outside** — Room polygon bleeding outside the building outline.
  - status: `not_yet_checked`
  - failing_elements: `[]`
  - notes: _populated by PR B3._

- [ ] **invented_or_wrong_height_exterior** — Exterior wall / esquadria / peitoril invented or wrong height.
  - status: `not_yet_checked`
  - failing_elements: `[]`
  - notes: _populated by PR B3._

- [ ] **wet_or_terrace_adjacency_wrong** — Bathroom / lavabo / A.S. / terraço with wrong adjacency.
  - status: `not_yet_checked`
  - failing_elements: `[]`
  - notes: _populated by PR B3._

- [ ] **room_rendered_as_bbox** — Room rendered as a bounding box / block instead of real geometry.
  - status: `not_yet_checked`
  - failing_elements: `[]`
  - notes: _populated by PR B3._

## Cross-reference

- Protocol: [`docs/protocols/visual_fidelity_gate_protocol.md`](../../docs/protocols/visual_fidelity_gate_protocol.md)
- Gate entrypoint: `tools/verify_fidelities.py --require-visual-evidence`
