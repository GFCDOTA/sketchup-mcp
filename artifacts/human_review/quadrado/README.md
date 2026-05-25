# Quadrado canonical artifact (human-reviewable)

> **Status:** Canonical
> **Type:** Human-facing deliverable (`.skp` + render)
> **Updated:** 2026-05-25
> **Policy:** [`../../../docs/ARTIFACT_POLICY.md`](../../../docs/ARTIFACT_POLICY.md)

This folder holds the human-reviewable artifacts for the quadrado
canonical reference — the proof that the wall-shell + window-aperture
pipeline produces a correct `.skp`. **Open `quadrado_canonical_with_window.skp`
in SketchUp 2026 to review the geometry directly.** The PNG is the
quick visual confirmation; the SKP is the deliverable.

## Files

| File | Role |
|---|---|
| `quadrado_canonical_with_window.skp` | The canonical `.skp` produced by the post-#164 wall-shell + window-aperture pipeline. Open in SU 2026 to inspect. |
| `quadrado_canonical_with_window.png` | Top-axon render of the SKP. Identical content to `docs/specs/_assets/quadrado_canonical_success_render.png` (the spec's canonical reference image), copied here so this folder is self-contained for Felipe's review. |
| `README.md` | This doc. |

## What this `.skp` contains

Per `docs/specs/_assets/quadrado_canonical_geometry_report.json`:

- **PlanShell_Group**: 14 faces, 36 edges, 4 faces with holes (one is the window opening).
- **Floor_Group_r_main**: 1 face, area 14.516 m² (one rectangular room).
- **WindowGlass_Group**: separate top-level group, glass at mid-thickness, bbox z ∈ [0.9, 2.1 m].
- **Wall heights**: PlanShell extends [0, 2.70 m]; window aperture preserves wall mass below sill (peitoril) and above head (verga).
- **Outer ring**: canonical 4-vertex outer (no L-shape notches per LL-017 / FP-025).

## Provenance

| Field | Value |
|---|---|
| SKP sha256 | `28fdddde872e84e8dd6004e1d27a2fe92610bc77fbe7d0e3c70598c415b5a9cf` |
| Size | 66,609 bytes |
| Built at | 2026-05-24 03:20 (local time, machine that ran the export) |
| Promoted to `artifacts/` | 2026-05-25 (this commit) |
| Source consensus | `fixtures/quadrado/consensus_with_window.json` |
| Built by | `tools/build_plan_shell_skp.py` (post-ADR-007 wall-shell + window-aperture code path) |
| Built on develop after | PR #164 `b01b194` (window semantics + wall shell + quadrado) |

## How to regenerate (any machine with SU 2026)

```bash
# From repo root:
python -m tools.build_plan_shell_skp \
       fixtures/quadrado/consensus_with_window.json \
       --out runs/quadrado_v4_canonical/quadrado.skp
```

Then compare against the canonical via the smoke gate:

```bash
pytest tests/test_quadrado_canonical_smoke.py -v        # 14 tests
pytest tests/test_wall_shell_canonical.py -v            # 15 tests
pytest tests/test_window_aperture_contract.py -v        # 15 tests
```

Geometry-level invariants are locked by
`docs/specs/_assets/quadrado_canonical_shell_polygon.json` +
`docs/specs/_assets/quadrado_canonical_geometry_report.json`.

## When to update this artifact

Update the `.skp` here when:

1. A PR intentionally changes the wall-shell or window-aperture pipeline
   such that the canonical render legitimately moves (rare; must be
   justified in the PR body + ADR update).
2. SketchUp version itself changes the byte representation enough that
   downstream tools diverge (rebuild with new SU, commit the new SKP,
   note the SU version in this README).

Do NOT update the `.skp` for:
- Unrelated pipeline changes (the .skp is byte-content; should be stable
  across non-geometry changes).
- "I just rebuilt and got a different byte size" (open a separate
  investigation issue first).

## Spec cross-references

- [`../../../docs/specs/quadrado_demo_spec.md`](../../../docs/specs/quadrado_demo_spec.md) — full spec
- [`../../../docs/adr/ADR-007-window-aperture-3d-carve.md`](../../../docs/adr/ADR-007-window-aperture-3d-carve.md) — window aperture decision
- [`../../../CLAUDE.md`](../../../CLAUDE.md) §19 (window semantics) + §20 (wall shell)
