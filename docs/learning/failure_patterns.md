# Failure Patterns

> Anti-patterns to never repeat. Each entry has a unique ID, a clear
> "do not" rule, and links to the lesson learned that would prevent
> recurrence.

## FP-001 — Opening SketchUp inside a tight dev loop

**Symptom:** 60-90s per loop iteration. Frustrating during debug.
Cache misses every time because each minor edit changes the consensus.

**Root cause:** No cheap gate before SU. No content-based cache.

**Rule:** Never invoke `tools.skp_from_consensus` in a loop. Use
`scripts/smoke/smoke_skp_export.py` which runs cheap gates first
(JSON validation, preview PNG, content-hash cache) and only spawns
SU when needed. See `docs/validation/sketchup_smoke_workflow.md`.

**See also:** `LL-001`, `LL-008`.

## FP-002 — Forgetting Pillow / matplotlib / scipy in pyproject deps

**Symptom:** PR passes locally on Windows, fails CI on ubuntu with
`ModuleNotFoundError`.

**Root cause:** Phantom transitive dependencies in the dev's local
venv. Especially common with `Pillow` (pulled by matplotlib),
`scipy` (pulled by scikit-image), `requests` (pulled by gh tooling).

**Rule:** When the pipeline imports a package, that package MUST be
in `[project].dependencies` in `pyproject.toml`. Reproduce CI
locally in a fresh venv before opening the PR.

**See also:** `LL-002`.

## FP-003 — Direct push to main

**Symptom:** main breaks; multiple in-flight PRs need to rebase;
CI is now red on the default branch.

**Root cause:** Fast iteration culture without develop branch.

**Rule:** All PRs go to `develop`. Only `develop → main` PRs touch
main. The hook `pre_bash_guard.py` blocks `git push origin main`.

**See also:** `LL-003`.

## FP-004 — `ruff --fix` over the whole repo

**Symptom:** Massive diff with mixed concerns (import order,
unused removals, style). Impossible to review.

**Root cause:** Treating ruff as an autoformatter instead of a linter.

**Rule:** Configure ruff with conservative selects (E, F, I) but
NEVER run `ruff --fix .` or `ruff format`. Cleanup is dedicated,
scoped PRs. The hook `pre_bash_guard.py` blocks repo-wide
autoformat commands.

**See also:** `LL-004`.

## FP-005 — Triplication of geometry in .skp

**Symptom:** Wall_dark1, wall_dark2 materials appear; 99 wall groups
for 33 walls; z-fighting on every wall. Diagnosed in
`docs/diagnostics/2026-05-02_planta_74_skp_inspection.md`.

**Root cause:** `consume_consensus.rb` was being executed multiple
times in the same SketchUp session without `model.entities.clear!`
between runs.

**Rule:** `consume_consensus.rb` always calls `reset_model()` at
the start. Never bypass this. The autorun plugin always closes SU
after a successful save (via `Sketchup.quit` in a 2s timer) so
state can't accumulate.

## FP-006 — Parapets covering walls ("rodapé branco")

**Symptom:** 1.10m colored band running along exterior walls,
covering them as if they were wallpaper.

**Root cause:** `tools/build_vector_consensus.py:_extract_building_outline`
emits soft_barriers from stroked outlines that often coincide with
the building exterior. The `_midpoint_inside_any?` filter only
checked the midpoint with tol_in=0.5, so parallel-offset peitoris
slipped through.

**Rule:** Use 3-pt sampling (p1, midpoint, p2) with tol_in=1.0 inch
in `_segment_overlaps_wall?`. Documented in commit `7fbd531`.
Future PRs that reduce tol_in or revert to single-point sampling
must justify empirically.

## FP-007 — Welcome dialog blocking SU2026 plugin firing

**Symptom:** SU spawns, exits with code 0 or 1 in seconds, no
plugin log written.

**Root cause:** SU2026 trial shows Welcome dialog when launched
without a positional .skp, blocking startup. The autorun plugin
never gets evaluated.

**Rule:** Always pass a positional .skp on the SU command line.
`skp_from_consensus.py` does this automatically: picks most recent
.skp in out_dir as bootstrap. If out_dir is empty, copy a template
from `C:\Program Files\SketchUp\SketchUp 2026\SketchUp\resources\en-US\Templates\`.

**See also:** `LL-009`.

## FP-008 — Mass branch deletion losing uncommitted work

**Symptom:** `git branch -D feat/svg-ingest` would have nuked 80
commits + 1 file with uncommitted changes in another worktree.

**Root cause:** Not checking worktree status before deletion.

**Rule:** Always `git worktree list` and `git -C <path> status`
before deleting any branch checked out in another worktree. Always
write a textual backup of branches to be deleted (name, SHA,
subject, unique commits) outside the repo.

**See also:** `LL-005`.

## FP-009 — Specialist agents granted write permission

**Symptom:** Hard to tell what the agent decided vs what the human
approved. Silent code changes.

**Root cause:** Conflating "find" and "fix" responsibilities.

**Rule:** Specialists are read-only over their scope by default.
Only `docs-maintainer` writes (narrowly, to docs/) and `ci-guardian`
proposes via PR drafts. All other findings are reports/PR comments.

**See also:** `LL-007`.

## FP-010 — Hidden CI deselects masking real regressions

**Symptom:** CI green but actually 3+ tests are silently skipped
because the deselect set is too broad.

**Root cause:** Adding tests to `--deselect` to "make CI green"
without documenting WHY each one is deselected.

**Rule:** Every test in the CI deselect set must be categorized
(HARD_EXTERNAL_DEPS or BASELINE_KNOWN_FAILURES) and listed in a
YAML comment in `.github/workflows/ci.yml` AND in
`docs/repo_hardening_plan.md`. Never deselect to mask a regression
introduced by the current PR.

## FP-011 — Ground-truth leaked into validator LLM prompt (2026-05-XX)

**Date:** 2026-05-04
**Discovered in:** `validator/vision.py:46` (commit history: pre-2026-05-04).
**Pattern:** The `_build_prompt` function hardcoded the string `"extraida de uma planta de 74 m2"`, leaking the ground-truth area of the canonical fixture into the LLM critic's prompt. This violates CLAUDE.md §2.6 ("Leak ground-truth into the extractor output. Scores are observational only.") and risked making the validator silently PDF-coupled (CLAUDE.md §2.4).
**Anti-pattern signal:** Any literal numeric value or filename in a prompt template that originates from a known fixture is a candidate leak. Watch for `74`, `planta_74`, `proto_p10`, `p12`.
**Resolution:** Tracked in branch `validate/no-gt-leak` (Stream B of the 2026-05-04 wave). Replaces hardcoded value with optional `expected_area_m2` from external config.

## FP-012 — Convex-hull room clip leaks watershed into exterior

**Date:** 2026-05-07
**Discovered in:** `tools/rooms_from_seeds.py:163-169`, surfaced
during Cycle 7 ground-truth expansion of `planta_74_micro.json`.

**Symptom:** SUITE 01 polygon on `planta_74` is **69.91 m²** in a
nominally 74 m² apartment. Sum of all 11 rooms ≈ 182 m² (~2.5×
nominal). BANHO 02's audited adjacencies include `SUITE 01` and
`LAVABO`, neither of which are architecturally true.

**Pattern:** When the building footprint is non-convex (L/C-shaped
or has a far-flung wing — `planta_74` has BANHO 01 sitting at the
far right with a wide unwalled exterior strip between it and the
rest of the apartment), `cv2.convexHull(wall_pts)` overshoots and
the watershed assigns the exterior to whichever seed is nearest.
The room nearest that strip becomes the "vacuum cleaner" for all
unclaimed exterior area.

**Anti-pattern signal:** Per-room polygon area > ~40 m² in a
< 100 m² floor; total room area > 1.3× nominal floor area;
`expected_adjacent_labels` for one or more rooms keeps surfacing
implausible neighbours.

**Rule (until fix lands):**
1. Do NOT silently shrink an inflated room polygon to "make a
   gate pass" — that hides the bug. Document instead.
2. When authoring `ground_truth/<plant>_micro.json` for a planta
   exhibiting this pattern, omit `expected_adjacent_labels` for
   any room whose only detected adjacency is implausible (Cycle 7
   COZINHA entry is the exemplar).
3. The Plan Truth Gate (`tests/test_planta_74_truth_gate.py`)
   does not yet assert per-room area caps. Until FP-012 is fixed,
   either land Option C from the diagnostic doc (regression
   `assert max(rooms_areas_m2) < 50`), or accept that the gate
   will not catch a recurrence in another corpus PDF.

**Resolution:** **Open.** Diagnostic + three fix paths (alpha-shape
hull, soft-barrier outer outline, per-room area cap) documented in
`docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.md`.
Recommended next step: spike Option A behind `--use-concave-hull`
flag default-off. Promote default only after `tests/baselines/
planta_74.json` is updated in a single dedicated PR.

**See also:** `LL-XXX` lesson to be filed once a fix lands.

## FP-013 — adjacency_f1 plateau lives upstream in room polygon quality

**Date:** 2026-05-08
**Discovered in:** `tools/classify_openings_by_room_context.py` post-Cycle-8b empirical analysis. Full diagnostic in `docs/diagnostics/2026-05-08_cycle6alt_adjacency_f1_analysis.md`.

**Symptom:** Fidelity Engine v1 reports `adjacency_f1 ∈ [0.65, 0.70]` on `planta_74` even after FP-012 was fixed. The metric stops improving regardless of changes to the classifier. Specific failures (FN: LAVABO↔SALA DE JANTAR, SALA DE ESTAR↔SALA DE JANTAR; FP: A.S.↔SALA DE ESTAR, A.S.↔TERRACO SOCIAL, BANHO 02↔LAVABO, BANHO 02↔SUITE 01).

**Pattern:** When the adjacency metric is below 0.80 but above the hard-fail floor of 0.60, the natural next step is to "tighten the classifier". **Don't.** Each remaining mismatch traces to one of:
- Room polygon LEAKING beyond actual room boundaries (e.g., SUITE 01 still spans into LAVABO area even at concave-hull r=0.50). Causes FPs.
- Room polygon SHRINKING short of host wall (canonicalization or tight concave hull). Causes the polygon-containment lookup to fail, fallback nearest-seed picks the wrong neighbour. Causes FNs.
- Two rooms architecturally adjacent via an OPEN PASSAGE (no door object). The classifier has nothing to attribute the adjacency to. Causes FNs that are unfixable in `classify_*` by design.

All three are upstream defects in `rooms_from_seeds.py` polygon shape OR in the lack of a "synthetic open_passage" opening.

**Anti-pattern signal:** changing `eps`, swapping nearest-seed for nearest-vertex, or special-casing self-adjacent disambiguation in `classify_openings_by_room_context.py` to chase adjacency_f1 above 0.70 without touching `rooms_from_seeds.py`. None of those work.

**Rule (until fix lands):** treat `adjacency_f1 ∈ [0.60, 0.80]` as the expected plateau on `planta_74`. The fidelity engine surfaces it as a warning by design. Investigate root cause in room polygon shape, NOT in the classifier. Cycle 8c candidates: polygon grow-by-thickness; alpha-shape per room; synthetic open_passage opening for shared polygon edges.

**Anti-pattern signal:** lowering the hard-fail threshold from 0.60 to "make it pass" — that violates CLAUDE.md §1 and the operational protocol's "alterar threshold para fazer passar" RED rule.

**Resolution:** Open. Documented in this entry and in `docs/diagnostics/2026-05-08_cycle6alt_adjacency_f1_analysis.md`. Cycle 8c will fix the underlying polygon quality issues; this is the unblocking work, not a classifier change.

**See also:** `FP-012` (convex-hull room clip — fixed in Cycle 8b but exposed this layer of plateau); LL-011 (empirical evidence overrides parametric guesses).

## FP-014 — Orphan autorun_control.txt clobbering opened .skp (autorun_control_files) (2026-05-20)

**Symptom (user-visible):** opening a `.skp` produced by our pipeline
"corrupts" or "closes" SketchUp. Reports range over: SU window
disappears 5–10 s after opening; the model becomes empty; the file
is silently overwritten with content from a different consensus.

**Root cause:** every autorun plugin in
`%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins\` reads its
companion `*_control.txt` on every SU launch and, if the file is
present, fires its script. The launchers
(`tools/skp_from_consensus.py`, `tools/build_room_ring_skp.py`)
write `autorun_control.txt` to arm the autorun, but historically
**did not remove it on the way out**. Any subsequent SU launch —
including the user double-clicking the `.skp` to inspect it — fires
the same autorun against stale paths. The autorun's script calls
`model.entities.clear!`, `model.save(out_skp)` and (in the case of
`render_skp_axon_and_inspect.rb` used by the inspector autorun)
`Sketchup.quit`. The opened file is gone before the user can see it.

A second instance of the same class: `autorun_inspector_control.txt`
left behind by `tools/render_skp_axon_and_inspect.rb` from an old
session. Removing only one launcher's control file isn't enough —
any orphan from any sibling launcher reproduces the bug.

**Rule:**

1. **Disarm before every SU launch.** Launchers must call
   `disarm_sketchup_autoruns.disarm(plugins_dir)` BEFORE arming
   their own control file. This catches orphans from sibling
   launchers or crashed sessions.
2. **Disarm in a `try / finally`.** Every code path out of `run()`
   — success, premature SU exit, timeout, exception — must remove
   the control file the launcher wrote. Cleanup-on-success-only is
   the trap: a SU crash, Ctrl-C, or `out_skp` already-exists race
   leaves the trap armed.
3. **Remove every `*control.txt`, not just yours.** Use the shared
   `disarm` helper so future launchers inherit the same hygiene
   without forking the logic. Forgotten cleanup in a single launcher
   contaminates every other launcher's SU launches.
4. **Treat "SU is doing something to my file" as an autorun bug
   until proven otherwise.** First diagnostic step is `ls`
   `%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins\*control.txt`.
   If anything matches, that's the prime suspect.

**Anti-pattern signal:** writing `autorun_control.txt` (or any
sibling `*_control.txt`) without a matching cleanup in the same
function, in a `finally` block, with a wider glob than just the
file you wrote.

**Repair landed:** `fix/disarm-sketchup-autoruns` —
adds `tools/disarm_sketchup_autoruns.py` (library + CLI),
wires it into `tools/skp_from_consensus.py` (pre-launch +
post-run cleanup in `try / finally`), and migrates
`tools/build_room_ring_skp.py` to the same helper.

**See also:** `FP-007` (welcome dialog) — same surface area
(SU2026 launch ergonomics) but unrelated cause.

## FP-015 — Door leaf hinge_world wrong for vertical walls in plan_shell (2026-05-20)

**Symptom:** opening the `runs/planta_74_plan_shell/model.skp`
produced after PR #141 (Phase 2 visual parity) showed two brown
door leaves "floating" in mid-air below the wall shell. The doors
on horizontal walls rendered correctly; the doors on vertical walls
ended up several metres from their host openings, parked over open
space or other rooms.

**Root cause:** in `tools/build_plan_shell_skp.rb` `build_door_leaf`,
the rotation pivot was computed as

```ruby
hinge_world = Geom::Point3d.new(
  hinge_along * PT_TO_IN,
  (axis_idx == 0 ? cross_base : hinge_along) * PT_TO_IN,
  0,
)
```

For horizontal walls (`axis_idx == 0`) the Y component is
`cross_base` (correct — perpendicular to the wall axis). For
vertical walls (`axis_idx == 1`) the Y component falls back to
`hinge_along` — duplicating the X value. The pivot ended up on a
diagonal in world space, often metres from the door's actual
hinge edge. The leaf's footprint was built correctly; it was the
30° rotation around that off-axis pivot that translated the leaf
into open space.

**Rule:** for any rotation around a wall-perpendicular hinge in a
generic axis-aligned exporter, the pivot must dispatch on
`axis_idx` BOTH for X and Y:

  - `axis_idx == 0` (horizontal wall): pivot at `(hinge_along, cross_base, 0)`
  - `axis_idx == 1` (vertical wall):  pivot at `(cross_base, hinge_along, 0)`

Sanity check: every door leaf bbox center must sit within
≈ opening width + rotation displacement of its host opening
center. We pin 1 m as the ceiling (real value is ≤ 0.5 m for
healthy leaves).

**Anti-pattern signal:** ternaries that pick ONE coordinate
component based on `axis_idx` without picking the symmetric pair
on the other component. The Y-only conditional in the buggy line
was the smell — both X and Y need the dispatch.

**Repair landed:** `fix/door-leaf-hinge-world-vertical-walls` —
splits the `hinge_world` computation into explicit
`axis_idx == 0` and `axis_idx == 1` branches, both setting BOTH
coordinates correctly. Adds
`tests/test_plan_shell_invariants.py::test_door_leaf_stays_near_its_opening_center`
as the regression gate (max 1 m distance from opening center).

**See also:** ADR-003 §3 (Phase 2 visual parity, where the bug
shipped); FP-014 (autorun cleanup — same author's pattern of bugs
that "look fine in tests but fail visually in SU").

## FP-023 — Python subprocess.terminate of SU confuses user about SKP stability (2026-05-23)

**Symptom:** User reports "abriu o SketchUp e fechou rápido" when
opening an SKP that the agent had just generated. Agent verifies
SU launches and stays alive 27+ seconds via `cmd /c start`; SKP is
structurally valid; inspector reports correct topology. Disconnect.

**Root cause:** Agent's helper Python launchers
(`_run_add_window.py`, `_render_view.py`, `_inspect_skp.py`,
`_reframe.py`) all follow the same pattern:
```python
proc = subprocess.Popen([SU, target_skp])
... poll for done marker ...
proc.terminate()    # ← kills SU
```
The user opening the SKP manually in parallel saw an SU instance
appear (could be theirs OR the agent's), then disappear when one
of the agent's helpers fired its `proc.terminate()`. The agent
attributed the close to a bug in the SKP; the user attributed it
to the agent's previous "broken" output.

**Rule:** When the agent's workflow uses SU as a headless renderer
(launch → run plugin → terminate), declare it loudly in the
session log. The user must know:

- "I'm about to launch SU on `target.skp` and terminate it after
  the plugin writes the done marker (~5–15s)."
- "If you have SU open right now or open it during this command,
  my terminate may catch your instance too."

For long-form interactive work (user opens SKP to inspect), the
agent must NOT have a pending `proc.terminate()`. Kill any
agent-launched SU explicitly with `taskkill /IM SketchUp.exe /F`
BEFORE telling the user "now open the file".

**Anti-pattern signal:** generating a sequence of agent SU runs in
the same session where the user might be trying to open the output
SKP in parallel; reporting "SU opens fine in my tests" without
mentioning that the agent's tests TERMINATE SU as part of the run.

**Repair pattern:**
```python
# Always log the lifecycle
print(f"[agent] launching SU on {target}")
proc = subprocess.Popen([SU, target])
...
proc.terminate()
print(f"[agent] terminated SU PID {proc.pid}")
# Before handing off to user:
subprocess.run(["taskkill", "/IM", "SketchUp.exe", "/F"])
print("[agent] all SU instances killed; safe to open manually")
```

### Formal runner-mode protocol (2026-05-23, user-mandated)

Every SU runner (Python launcher, helper, harness) MUST declare its
runtime mode and behave accordingly. **Safe default is `interactive`
— do NOT terminate SU automatically.**

| Mode | When to use | Termination behaviour |
|---|---|---|
| `headless` / `ci` | Automated CI; agent self-tests; smoke gates | MAY terminate the child process the runner itself launched. NEVER `taskkill /IM` other SU instances. |
| `interactive` / `debug` | Local development; agent in a user session | MUST NOT terminate. Print done marker, wait for user to close SU. |
| `attach` / `manual` | User opened SU; runner just consumes events | NEVER touch any SU process. No `Popen`, no `terminate`, no `taskkill`. |

The marker file (`_*_done.txt`) means **"artifact ready"**, NOT
"kill SU". Termination is a separate decision driven by mode.

### Implementation requirements

Every `_run_*.py`, `*launcher*.py`, or tool that calls `Popen` on
`SketchUp.exe` must:

1. Read mode from `RUN_MODE` env var OR `--mode {headless,interactive,attach}` CLI flag OR `--no-terminate` shorthand.
2. Default to `interactive` when neither is set.
3. Print the chosen mode at launch: `[su-runner] mode=interactive; will NOT terminate SU on done`.
4. In docstring/help: declare whether the runner is destructive to external SU processes.
5. In `headless` mode, only terminate `proc.pid` (own child); never `taskkill /IM`.

### Reference helper

`tools/su_runner_safety.py` provides `parse_mode`,
`should_terminate(mode) -> bool`, `is_attach(mode) -> bool`, and
`log_mode(mode)`. Every SU launcher imports it and respects the
chosen mode. Covered by 35 unit tests in
`tests/test_su_runner_safety.py`.

**See also:** FP-007 (welcome dialog — also a SU2026 launch
ergonomics issue); LL-009 (bootstrap .skp pattern); LL-015 (runner
mode protocol, the positive rule complementing this FP).

## FP-024 — Window modelled as full-height void + 3-band infill (door-like shaft) (2026-05-24)

**Symptom:** Looking at a rendered .skp (quadrado canonical fixture
and planta_74), windows appear as **vertical shafts** with three
stacked sub-volumes: a gray block at the bottom, a translucent blue
panel in the middle, a gray block at the top. The wall structurally
"breaks" at the window position — there's no continuous wall mass
between sill and floor or between head and ceiling. Visually reads
as "door with infill" or "elevator shaft," not as "wall with
aperture."

**Root cause:** `tools/build_plan_shell_skp.{py,rb}` (and the
legacy `tools/consume_consensus.rb add_window_panel`) treated every
opening uniformly:

1. Python: subtracts a `width × wall_thickness` rectangle from the
   2D wall shell polygon BEFORE extrusion (function
   `opening_carve_rect`).
2. Ruby: extrudes the carved shell to `WALL_HEIGHT_IN` — the 2D-
   carved region becomes a full-height floor-to-ceiling void.
3. Ruby `build_window_panel` then emits THREE sub-groups inside
   that void: `Window_Group_<id>_sill` (z ∈ [0, 0.9 m], material
   PARAPET_RGB), `Window_Group_<id>_glass` (z ∈ [0.9, 2.1 m],
   material GLASS_RGB), `Window_Group_<id>_lintel` (z ∈ [2.1, 2.7 m],
   material LINTEL_RGB).

The semantic contract of a window — **wall-hosted partial-height
aperture; wall mass continuous below the sill (peitoril) and above
the head (verga)** — is violated. The "sill" and "lintel" boxes
exist but they are independent volumes with their own materials,
NOT the wall continuing past the aperture.

**Why it survived for a while:** Aggregate fidelity scores looked
fine — wall area, opening count, classification accuracy were all
correct. The bug was purely **structural / visual** and required
explicit human review of the rendered SKP to surface.

**Repair pattern (ADR-007):**

1. Distinguish `WINDOW_APERTURE_KINDS = {"window"}` from
   `FULL_HEIGHT_CARVE_KINDS = {interior_door, door_arc, door,
   interior_passage, open_passage, passage, glazed_balcony}`.
2. In Python, skip windows from `carve_rects`; route them to a
   separate `window_apertures` list (top-level field in the
   serialized `_shell_polygon.json`).
3. In Ruby, after extruding the solid wall shell, call
   `build_window_aperture_3d` per aperture:
   - Find the host wall lateral face (full wall-height span).
   - Read its fixed coord from the model (LL-014 — never hardcode).
   - Add a coplanar rectangle at z ∈ [WINDOW_SILL_IN, WINDOW_HEAD_IN].
     SU auto-splits the host face — the wall material above head
     and below sill REMAINS as the perimeter remainder.
   - `pushpull(-real_thickness_in)` through the wall; SU merges
     with the opposite face on exact match, creating a real
     through-hole.
   - Emit `WindowGlass_Group_<id>` at mid-thickness — the ONLY
     window-specific element. Wall material is wall material.

**Detection signature (anti-regression):**

The geometry report from a healthy build will have:
- `groups_diagnostic[*]` containing `PlanShell_Group` with
  `bbox_m.max.z == WALL_HEIGHT_M` (~2.70 m).
- `WindowGlass_Group_<id>` per window, bbox_m.z = [0.9, 2.1].
- **No** `Window_Group_*_sill` or `Window_Group_*_lintel` entries.

The bug signature is the opposite: legacy sill/lintel groups
present, often with `bbox_m.z = [0, 0.9]` (sill on the floor)
which is the architectural "shaft" appearance.

**Validation gates** (test files):
- `tests/test_window_aperture_contract.py` — Python contract.
  Windows must NOT appear in `openings_carved`; the kind sets are
  disjoint; planta_74's 4 windows must all route to the 3D path.
- `tests/test_window_aperture_geometry.py` — SKP geometry. Wall
  height preserved; glass at sill-to-head only; legacy `_sill` /
  `_lintel` groups absent.

**See also:** ADR-007 (the decision document); LL-016 (the
positive rule); ADR-003 (`build_plan_shell_skp` overall design —
this fix is a Phase 2.5 refinement); LL-014 (read coords from
the actual model, never hardcode — applied in the 3D carve);
`docs/specs/quadrado_demo_spec.md` §6.4 (the in-place edit pattern
that `build_window_aperture_3d` adopts).

## FP-025 — Wall shell outer corners have L-shape notches ("tecos") after `unary_union` of perpendicular wall boxes (2026-05-24)

**Symptom:** Rendered SKP from `build_plan_shell_skp` shows the
quadrado canonical fixture (and any other axis-aligned rectangular
room) with **stepped outer corners** instead of clean L-shapes.
Each corner has a small 2.7 × 2.7 pt notch (wall thickness 5.4 pt,
half = 2.7) cut OUT of the outer wall material. The wall reads as
"4 bars assembled" rather than "1 continuous frame."

In the serialised `_shell_polygon.json`, the canonical 4-wall
quadrado outer ring carried **12 vertices instead of 4** — three
vertices per corner forming the L-shape notch:
- (100, 97.3) — south wall outer at x = wall start
- (100, 100)  — corner step
- (97.3, 100) — left wall outer at y = wall start

**Root cause:** `wall_footprint(wall)` in `tools/build_plan_shell_skp.py`
built each wall's 2D rectangle exactly between the wall's start
and end points along the wall axis:

```python
# horizontal wall
x0, x1 = min(s[0], e[0]), max(s[0], e[0])  # NO extension
return box(x0, cy - half, x1, cy + half)
```

At every junction where two perpendicular walls met, each wall
extended `half = thickness/2` past the OTHER wall's centerline
(via its own perpendicular thickness), but neither extended past
its own centerline endpoint along its own axis. The result: the
union covered everything EXCEPT the small `2*half × 2*half`
square at each outer corner — exactly the L-shape notch.

**Why earlier visual checks missed it:** the notches are
**2*half × 2*half ≈ 0.19 m × 0.19 m** — visible on the quadrado
(where the wall is small relative to the room), much less obvious
on planta_74 (where wall thickness is small relative to the
30+ wall complex geometry). The bug was always there.

**Why `shapely.simplify` didn't fix it:** the L-shape notch
produces real, non-collinear vertices (the corner step goes
+x then -y). `simplify` only collapses collinear sequences;
it cannot remove a real notch.

**Repair pattern (LL-017):**

1. **Extend each wall by half-thickness at BOTH endpoints along
   its own axis.** For a horizontal wall: `x0 = min(s.x, e.x) - half`,
   `x1 = max(s.x, e.x) + half`. The two perpendicular walls now
   fully overlap in the `2*half × 2*half` corner cell — `unary_union`
   produces a clean outer corner.

2. **Add an axis-aligned canonicalisation pass** after union and
   carve. `_canonicalise_axis_aligned_ring` drops any vertex
   sandwiched between two edges with the same cardinal direction
   (both horizontal or both vertical). Safety net for edge cases
   where extension alone leaves a redundant vertex (mid-wall door
   carves that intersect the outer ring, etc.).

3. **Stats counter `redundant_vertices_dropped`** is surfaced in
   `_shell_polygon.json`. On a healthy build it equals zero after
   the wall-extension fix (the union is already canonical). Non-zero
   indicates the canonicaliser earned its keep.

**Detection signature (anti-regression):**

For the quadrado canonical fixture:
- `polygons[0].exterior` has **4 vertices** (not 12).
- All 4 at corners `(97.3, 97.3)`, `(216.384, 97.3)`,
  `(216.384, 216.384)`, `(97.3, 216.384)`.
- `polygons[0].interiors[0]` has **4 vertices**.
- All edges axis-aligned (dx=0 OR dy=0).

For planta_74:
- `slivers_removed == 0`.
- Each piece passes `is_valid` and `area > MIN_SLIVER_AREA_PTS2`.
- All edges axis-aligned.

**Validation gates** (`tests/test_wall_shell_canonical.py`, 15 tests):
- `wall_footprint` extends by half at both endpoints (h and v).
- Quadrado outer ring = 4 vertices at canonical positions.
- All edges axis-aligned.
- Canonicaliser idempotent (drops 0 on a second pass).
- Planta_74 has 0 slivers and 0 leftover redundant vertices.
- Window aperture (ADR-007) does not pollute the outer ring.

**See also:** LL-017 (the positive rule); ADR-007 (window aperture
fix landed first; this corner fix complements it); ADR-003
(`build_plan_shell_skp` overall design); FP-006 (wall/peitoril
overlap filter — also depends on clean wall footprints).
