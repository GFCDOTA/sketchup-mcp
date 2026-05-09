# Current State — 2026-05-09 (post autonomous-loop wave + dogfood)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `chore/post-loop-handoff-refresh-2026-05-09` (this commit)
- **develop @** `f7ee221` — PR #99 (Slice 5d sub_scores_delta) merged
- **Active CI:** `ci.yml`, `skp_fidelity_gate.yml`, `rubocop.yml`,
  `quality_gates.yml`. Last 11 develop runs all green.
- **Open PRs:** none.

## Autonomous-loop wave — 10 PRs end-to-end (#90–#99)

| PR | Title | SHA |
|---|---|---|
| #90 | Cycle 5 — gate_g2 inspector v2 consumer | `cfd7f8a` |
| #91 | Cycle 13 — proposed_actions producer | `86cb1f3` |
| #92 | Slice 4 — Review tab consumes proposed_actions | `dc8048d` |
| #93 | Cycle 13b — gate_f0_pa smoke integration (opt-in) | `1789227` |
| #94 | Slice 5a — gate_e_amend writes amended_observed | `c469d00` |
| #95 | Slice 5b — gate_e_fidelity_amended | `341e2c8` |
| #96 | Slice 5c — gate F0 prefers amended report | `08bb8e7` |
| #97 | Slice 4-extra — cockpit shows pre/post/Δ | `bc5281c` |
| #98 | sys.path bootstrap fix + dogfood report | `d01bc76` |
| #99 | Slice 5d — sub_scores_delta surfaced | `f7ee221` |

## Override-aware F0 verdict — END-TO-END LIVE

```
Cockpit Review tab writes review_overrides.json
  ↓
Smoke gate E2 → amended_observed.json (Slice 5a)
  ↓
Smoke gate E3 → fidelity_report_amended.json (Slice 5b; both pre + post)
  ↓
Smoke gate F0 prefers amended → pre/post/Δ + sub_scores_Δ (5c, 5d)
  ↓
Cockpit pre_skp_review() propagates all amended fields (4-extra)
  ↓
Cockpit Pre-SKP pane shows pre/post/Δ + collapsible sub-score Δ (5d)
```

**Proven on real data** — PR #98 dogfooded the path on the
canonical planta_74 baseline with 3 real overrides:
- consensus sha256 byte-identical before/after (ADR §2.10.1 ✓)
- detector path overrides-blind throughout (ADR §2.10.8 ✓)
- adjacency_score moved -0.088 (honestly reported per §2.10.5 ✓)

## Cockpit feature matrix — full board

| Slice | Status | What |
|---|---|---|
| 12 — MVP | ✅ | SVG overlay + 4 layer toggles + 4 inspector tabs |
| 12b — PDF underlay | ✅ | pypdfium2 raster behind SVG; opacity + DPI sliders |
| 12c — hover highlight | ✅ | `<title>` tooltips + CSS `:hover`; no JS |
| 12d — expected_model overlay | ✅ | 5-state status palette; catches FP-012 visually |
| 12e — diff view | ✅ | Run A vs run B; dashed magenta + Diff tab |
| 12f — History/Pre-SKP Review | ✅ | Multi-run history + advisory verdict |
| 12g — thumbnails on-demand | ✅ | PIL-direct rasteriser; mtime cache |
| 12h — SVG `source: manual` + delete UI | ✅ | Cycle 12c hover + override delete |
| Slice 2 — overrides.py + Review tab | ✅ | All 7 v1 override types live |
| Slice 3 — apply_overrides + gate_f0 | ✅ | First override consumer in pipeline |
| Slice 4 — proposed_actions chips | ✅ | Cycle 13 producer + cockpit chips |
| Slice 4-extra — pre/post/Δ in cockpit | ✅ | PR #97 |
| Slice 5a — gate_e_amend | ✅ | PR #94 |
| Slice 5b — gate_e_fidelity_amended | ✅ | PR #95 |
| Slice 5c — F0 prefers amended | ✅ | PR #96 |
| **Slice 5d — sub_scores_delta** | ✅ | **PR #99 (this wave's last)** |
| Slice 2 (FastAPI Phase 3) | 🟡 deferred per ADR §5C |
| Slice 3 (proposed_actions auto-apply) | ❌ ADR explicitly forbids |

## Smoke harness gate sequence (final)

```
A → B → C → D → E → E2 → E3 → F0 → F0pa → F → G → G2 → H
```

Cheap gates first (A–E). E2/E3 amend + recompute fidelity when
overrides exist (auto-default). F0 verdict prefers amended. F0pa
emits proposed_actions (opt-in). F is the SKP spawn (last gate).
G2 reads inspect_report.json (Stage 1.6 Cycle 5; SKIPs until
Cycle 6 wires the producer).

## Active tools (refreshed)

| Tool | Status |
|---|---|
| `tools/coherence_audit.py` | ✓ stable |
| `tools/micro_truth_gate.py` | ✓ stable |
| `tools/skp_inspection_report.py` | ✓ stable |
| `tools/classify_openings_by_room_context.py` | ✓ stable |
| `tools/inspect_walls_report.rb` | ✓ v2 schema |
| `tools/fidelity/compare_generated_to_expected.py` | ✓ apply_overrides=True mode (Slice 3) |
| `tools/fidelity/synth_from_expected.py` | ✓ round-trip helper |
| `tools/rooms_from_seeds.py` | ✓ DEFAULT concave-hull |
| `tools/synth/make_synthetic_vector_pdf.py` | ✓ 4 SPECs (L/T/+/hall5) at fidelity 1.0 |
| `tools/apply_overrides.py` | ✓ amended_observed_v1 |
| **`tools/propose_skp_actions.py`** | **✓ NEW — proposed_actions_v1 producer (Cycle 13)** |
| `scripts/smoke/smoke_skp_export.py` | ✓ A–H + F0 + F0pa + E2 + E3 + G2 (sys.path bootstrap fixed PR #98) |
| `cockpit/render_overlay.py` | ✓ MVP + PdfUnderlay + expected_match + diff + hover/title + status_color_map |
| `cockpit/app.py` | ✓ 7 sidebar groups + 7 inspector tabs + Review tab with chips + Δ expander |
| `cockpit/overrides.py` | ✓ 7 override types + audit trail + inline remove + source_proposed_action_id |
| **`cockpit/proposed_actions.py`** | **✓ NEW — Slice 4 chip consumer + apply convenience** |
| `cockpit/thumbnails.py` | ✓ on-demand PIL rasteriser + cache |
| `cockpit/history_view.py` | ✓ Multi-run history + Pre-SKP Review with all amended fields |

## Test counts

- Pre-Cycle-12 develop (start of arc): 568 PASS
- After cockpit read-only slice (12 / 12b / 12c / 12d / 12e / 12f): 626 PASS
- After parallel waves + ADR-001 + Slices 2/3/4: 832 PASS
- After mutation-surface wave (Slices 5a/5b/5c/5d/4-extra/12g/12h/Stage 1.6 audit): **889 PASS** (+321 vs baseline)
- 17 FAIL (CLAUDE.md §10 raster legacy, unchanged), 8 SKIP

## Tooling notes

- **gh CLI** at `C:\Program Files\GitHub CLI\gh.exe`; not on Bash
  PATH. Always invoke via absolute path + `--repo GFCDOTA/sketchup-mcp`.
  Auth keyring (account `fmodesto30`, scope `repo`).
  See `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`.
- Cockpit launch: `pip install -e ".[cockpit]"` then
  `streamlit run cockpit/app.py`.
- Smoke harness override-aware flow: `python scripts/smoke/smoke_skp_export.py
  --consensus <path> --skip-skp --emit-proposed-actions --expected-model
  ground_truth/<plant>/expected_model.json`.

## Top of next-session queue

1. 🟡 **P1 — ADR-002 (room_polygon_override)** — dogfood UX gap #2
   needs architectural decision. Schema-extending change; deserves
   focused session, not autonomous-loop chaining.
2. 🟡 P1 — Cycle 6 (Stage 1.6 SU integration) — wire autorun
   inspector into gate_f. SU runtime, needs focused session.
3. 🟢 P2 — Cycle 7: promote `--inspect-strict` default (after Cycle 6).
4. 🟡 P3 — Cockpit Phase 3 (FastAPI POST + multi-user) — deferred
   per ADR-001 §5C until first real review case.
5. 🔴 — REAL multi-PDF (Felipe must provide PDFs).

## Recommendation

End the autonomous loop. The cockpit + smoke override-aware stack
is feature-complete + dogfooded on real data. Remaining items
(ADR-002, Cycle 6, Phase 3, multi-PDF) are either RED-blocked or
deserve focused fresh sessions with deliberate scope. Continuing
the autonomous loop risks inventing work just to keep going (CLAUDE.md
§17 "DONE IS NOT STOP has a ceiling" rule).
