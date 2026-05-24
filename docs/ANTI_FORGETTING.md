# ANTI_FORGETTING — permanent rules that must survive every session

> **Status:** Canonical
> **Type:** Permanent rules with reasoning
> **Updated:** 2026-05-24
> **Companion docs:** [`PROJECT_STATE.md`](PROJECT_STATE.md),
> [`../CLAUDE.md`](../CLAUDE.md) §§19, 20 (constitution),
> [`adr/`](adr/) (decision records).

This file exists because rules that live only in chat history,
session memory, or feature branches get re-discovered the hard way.
Each rule below has:

- the **rule** itself (the do-not),
- **why** (the past incident or principle that proves it),
- **how to apply** (when this rule fires),
- **gates** that enforce it,
- **canonical references** (paths / ADRs / CLAUDE.md sections).

These rules apply to humans, agents, and CI alike. If a rule below
disagrees with a `.md` you found elsewhere, this file wins (except
[`../CLAUDE.md`](../CLAUDE.md) §0–§3, which are inviolable).

---

## Rule 1 — Wall shell must be continuous from ring/polygon logic

> **Wall footprints extend by half-thickness at BOTH endpoints along
> the wall's own axis. After `unary_union` and any carve, the
> resulting polygon passes through
> `canonicalise_axis_aligned_polygon(poly)` which drops every vertex
> sandwiched between two same-cardinal-direction edges. Axis-aligned
> wall input must produce axis-aligned output with NO stepped notches,
> NO slivers, NO overhanging segments.**

**Why.** A wall shell built from independent bars (each cut exactly
at its centerline endpoint) leaves a `2*half × 2*half` L-shape notch
at every outer corner where two perpendicular walls meet. On the
quadrado canonical fixture this produced 12 outer-ring vertices
instead of the canonical 4 — the "tecos" signature (FP-025). Without
the corner extension + post-union canonicalisation, every plant with
right-angle corners regresses to the same defect.

**How to apply.** Any code path that builds a wall shell from
individual wall segments — whether via union, offset, boolean, or
explicit polygon construction — must satisfy both:
(a) corner extension (`wall_footprint(extend_endpoints=True)` by
default), and (b) post-step canonicalisation
(`canonicalise_axis_aligned_polygon`). Opt-out (`extend_endpoints=False`)
is allowed ONLY in unit tests that need the raw rectangle.

**Gates.** `pytest tests/test_wall_shell_canonical.py -v` (15 tests +
planta_74 regression). `slivers_removed > 0` on planta_74 is the
regression signature.

**Canonical references.** [`../CLAUDE.md`](../CLAUDE.md) §20 (on
`feature/window-aperture-semantics`),
`tools/build_plan_shell_skp.py wall_footprint()` +
`canonicalise_axis_aligned_polygon()`, LL-017, FP-025.

---

## Rule 2 — Windows are partial-height apertures hosted by walls

> **Window openings are wall-hosted partial-height openings.
> They preserve wall mass below (peitoril) and above (verga) the
> opening and are NEVER represented as door-like full-height voids
> unless explicitly classified as doors.**

**Why.** The Ruby exporter historically carved every opening as a 2D
full-height rectangle pre-extrude, then refilled windows with three
stacked sub-volumes (sill / glass / lintel). Structurally that is
three boxes inside a floor-to-ceiling void — semantically a door with
infill, not a window. Affected the quadrado canonical fixture AND all
4 windows on planta_74. The fix routes `kind_v5 == "window"` to a
separate `window_apertures` list and adds a coplanar rect at sill-to-
head only after extrusion (SU auto-splits — perimeter remainder
preserves wall mass).

**How to apply.** Any code that translates an opening into a 3D solid
modification MUST consult `kind_v5`:

| `kind_v5` | 2D pre-extrude carve | 3D post-extrude carve |
|---|---|---|
| `interior_door` | full-height | — |
| `interior_passage` | full-height | — |
| `glazed_balcony` (porta-vidro) | full-height | — |
| `window` | **NEVER** | **`build_window_aperture_3d`** |

Glass for windows sits at mid-thickness as a separate top-level
`WindowGlass_Group_<id>`. No sill/lintel sub-groups.

**Gates.** `pytest tests/test_window_aperture_contract.py -v` (15
tests), `pytest tests/test_window_aperture_geometry.py -v` (9 tests).
Failure signatures: `Window_Group_<id>_sill` at `bbox_m.z = [0, 0.9]`,
any `Window_Group_<id>_lintel`, or `PlanShell_Group.bbox_m.max.z <
WALL_HEIGHT_M`.

**Canonical references.** [`../CLAUDE.md`](../CLAUDE.md) §19 (on
`feature/window-aperture-semantics`), ADR-007 (on same feature
branch),
`tools/build_plan_shell_skp.{py,rb}`, LL-016, FP-024.

---

## Rule 3 — Post-boolean cleanup is mandatory

> **After any carving / offset / boolean / union that produces a wall
> shell, a canonicalisation pass must run. Without it, axis-aligned
> input can produce non-axis-aligned output, redundant collinear
> vertices, or stepped corners.**

**Why.** Boolean operations on shapely polygons can introduce
collinear vertices that are correct geometrically but a regression
semantically (the shell should look like a clean architectural
rectangle, not a polyline with redundant points). Without the
canonicaliser, downstream consumers see extra vertices and can
fragment the shell further.

**How to apply.** Every union / difference / intersect / offset call
that yields the canonical wall shell or floor polygon is followed by
`canonicalise_axis_aligned_polygon(poly)`. The function is idempotent
— calling it twice yields the same output. Stats carry
`redundant_vertices_dropped` so regressions are visible in the build
artifact.

**Gates.** Same as Rule 1
(`tests/test_wall_shell_canonical.py`). Idempotency check is
explicit.

**Canonical references.** Same as Rule 1.

---

## Rule 4 — Quadrado is THE canonical fixture for wall-shell + window

> **When validating a wall-shell or window-aperture pipeline change,
> use the versioned inputs at `fixtures/quadrado/*.json` and compare
> against the versioned reference outputs at `docs/specs/_assets/*`.
> NEVER invent a parallel fixture under `runs/` (gitignored) and call
> it canonical.**

**Why.** Several earlier cycles invented one-off demos under `runs/`
to "prove" a change worked, then those demos disappeared (gitignored)
and the next session reinvented them. Each reinvention is a vector
for accidentally moving the goalposts. The quadrado is small enough
to be hand-verifiable and exercises every load-bearing primitive
(4-vertex outer ring, 1 window aperture, peitoril + verga
preservation).

**How to apply.** Any PR that touches wall-shell or window-aperture
logic MUST cite a quadrado test result in its body. New parallel
fixtures are allowed ONLY when they extend coverage (different
topology — L, T, +, hall) and are committed alongside their
reference outputs. New fixtures live in `fixtures/<name>/`; their
reference outputs live in `docs/specs/_assets/`.

**Gates.** `pytest tests/test_quadrado_canonical_smoke.py -v` (14
tests, CI-ready). If a reference output needs to change, the PR body
must justify — `docs/specs/quadrado_demo_spec.md` calls this out.

**Canonical references.** `fixtures/quadrado/`,
`docs/specs/quadrado_demo_spec.md`,
`docs/specs/_assets/quadrado_canonical_*`.

---

## Rule 5 — Real plants start from canonical artifacts

> **When working on a real plant (e.g., `planta_74`), reuse the
> canonical artifacts already in `fixtures/<plant>/` and
> `ground_truth/<plant>/`. Do not create a new "demo" pipeline that
> diverges from the canonical one.**

**Why.** `planta_74` already has: a vector consensus pipeline
documented in `OVERVIEW.md` §4.4, a versioned baseline at
`tests/baselines/planta_74.json`, ground-truth files at
`ground_truth/planta_74/` and `ground_truth/planta_74_micro.json`,
human-annotated openings at
`fixtures/planta_74/human_openings_annotation.png`, and an augmented
consensus at
`fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`.
A parallel demo discards every gate written against this baseline.

**How to apply.** Before touching pipeline code for a known plant,
read `PROJECT_STATE.md` §4 to find the canonical artifacts. Run the
documented pipeline. If you genuinely need a different artifact (e.g.,
a new variant of the human annotation), it lives under
`fixtures/<plant>/` next to the existing one.

**Gates.** Plan Truth Gate
(`pytest tests/test_planta_74_truth_gate.py -v`). Fidelity Engine v1.
Both reference the canonical baselines.

**Canonical references.**
[`PROJECT_STATE.md`](PROJECT_STATE.md) §4,
[`HANDOFF.md`](HANDOFF.md) §2.4.

---

## Rule 6 — Progress is what lands as test / fixture / gate / ADR / doc / commit

> **A finding, fix, decision, or experiment counts as progress only
> when it lives as one or more of: a test, a fixture, a gate, an ADR,
> a `CLAUDE.md` rule, an entry in `PROJECT_STATE.md`, or a tracked
> commit. Anything that lives only in chat history or in a local
> untracked file is NOT progress — it is at risk of being forgotten
> the next session or on the next machine.**

**Why.** Multiple prior cycles produced fixes locally that never made
it into a test or doc, and the next session re-discovered the same
bug. The 2026-05-13 "operator verbal waiver" pattern is the canonical
example: a verbal "trust me, looks fine" satisfied the gate at the
time, then the policy correctly hardened to require the 7 visual
evidence artifacts. The verbal pattern is now superseded by the
artifact requirement.

**How to apply.** At the end of every cycle, ask: "what changed that
the next agent on a clean clone would need to know?" If the answer is
"the consensus file on my machine has X" — that's not progress. Land
the change as a tracked fixture, test, or doc.

**Gates.** `python scripts/project_state_check.py` flags missing
canonical docs / fixtures / gates. The end-of-cycle checklist in
[`HANDOFF.md`](HANDOFF.md) §6 enforces six required outputs per
cycle.

**Canonical references.** [`../CLAUDE.md`](../CLAUDE.md) §14
(autonomous continuation protocol), §17 (twelve-question stop gate).

---

## Rule 7 — Pipeline invariants (from AGENTS.md §2 / CLAUDE.md §2)

> **The pipeline must NEVER: invent rooms or walls; mask `rooms=0`;
> use bounding box as a substitute for a room; couple to a specific
> PDF; skip required debug artifacts; leak ground truth into the
> extractor output.**

**Why.** Each of these was a real failure mode in early cycles.
Inventing rooms produced false PASS verdicts on plants that genuinely
had `rooms=[]`. Masking `rooms=0` hid pipeline regressions. Using
bbox-as-room produced rectangular "rooms" that bore no relation to
the actual floor plan. Hardcoded thresholds for `planta_74` made
every other plant a regression.

**How to apply.** If your change "would resolve the case" by
violating any invariant, **STOP** and report the trade-off. The case
is honest evidence, not a problem to make go away.

**Gates.** Implicit in every test that asserts the pipeline output
matches the input. Schema validation
(`tests/test_schema_v2.py`). Debug artifact existence checks.

**Canonical references.** [`../CLAUDE.md`](../CLAUDE.md) §2,
[`../AGENTS.md`](../AGENTS.md) §2.

---

## Rule 8 — Git flow: develop-first, no direct commits to main/develop

> **Always branch from `develop`. PRs land into `develop`. `main`
> only receives PRs that come from `develop`. NEVER commit directly
> on `main` or `develop`. NEVER force-push either branch.**

**Why.** Direct commits and force-pushes have lost work and broken
the deploy chain on multiple projects. The hook
`.claude/hooks/pre_bash_guard.py` enforces this fence in Claude
Code sessions.

**How to apply.** Branch naming: `feature/`, `fix/`, `chore/`,
`docs/`, `perf/`, `refactor/`, `test/`, `agents/`, `tooling/`,
`validate/`, `hotfix/`. Delete a feature branch (local + remote)
after its PR is merged.

**Gates.** `pre_bash_guard.py` rejects forbidden commands. Code
review enforces PR-into-develop discipline.

**Canonical references.** [`../CLAUDE.md`](../CLAUDE.md) §0,
[`git_workflow.md`](git_workflow.md).

---

## Rule 9 — SketchUp is the LAST gate, not the first

> **Run the cheap gates (lint, pytest, plan-truth, coherence, micro,
> fidelity) before spawning SketchUp. Use content-hash caching to
> skip SU when the consensus has not changed.**

**Why.** SketchUp spawn costs 5–90s (GUI process) and is fragile
across versions. Running it on every iteration burns wall-clock time
and risks interfering with a concurrent human SU session.

**How to apply.** `tools/skp_from_consensus.py` writes a sidecar
`<out_skp>.metadata.json` with the consensus sha256; reruns short-
circuit when the sha matches. `--force-skp` bypasses. The smoke
harness `scripts/smoke/smoke_skp_export.py` enforces the order.

**Gates.** Implicit: any pipeline test that spawns SU should also
honor `--skip-skp` and the cache.

**Canonical references.** [`../CLAUDE.md`](../CLAUDE.md) §3,
`docs/performance/skip_unchanged_skp.md`,
`docs/validation/sketchup_smoke_workflow.md`.

---

## Rule 10 — SU runner mode protocol (LL-015 / FP-023)

> **Every Python/Ruby tool that calls `Popen` on `SketchUp.exe` MUST
> declare a runtime mode (`headless` / `interactive` / `attach`) and
> respect the termination policy. Default mode is `interactive`
> (no termination). NEVER `taskkill /IM SketchUp.exe`.**

**Why.** A subprocess.terminate of SU during a smoke run confused
operators about whether the resulting `.skp` was stable. The fix:
modes + a reference helper.

**How to apply.** Use `tools/su_runner_safety.py`:
`parse_mode`, `should_terminate`, `is_attach`, `log_mode`. Print at
launch: `[su-runner] mode=<X>; terminate_on_done=<bool>`. In
headless mode terminate ONLY own `proc.pid` (never broader kill).

**Gates.** `pytest tests/test_su_runner_safety.py -v` (35 tests).

**Canonical references.** [`../CLAUDE.md`](../CLAUDE.md) §18,
LL-015, FP-023.

---

## Update log

| Date | Commit | What changed |
|---|---|---|
| 2026-05-24 | (this commit) | Initial canonical anti-forgetting doc. 10 permanent rules consolidated from CLAUDE.md, AGENTS.md, ADRs 001–007, and the 2026-05-24 quadrado / wall-shell / window aperture cycle. |
