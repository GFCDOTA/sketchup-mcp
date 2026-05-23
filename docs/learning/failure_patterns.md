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

## FP-016 — Path proliferation: creating parallel artifacts outside canonical run dir (2026-05-23)

**Symptom:** Agent asked to "add a window to the quadrado" creates
`E:/Claude/quadrado_delivery/` outside the project tree, copies the
SKP there, generates a new consensus there with shifted origin
(2.7,2.7 instead of 100,100), produces matplotlib-only renders
called `quadrado_4x4_with_window_iso.png`. User confused because
the "real" canonical quadrado lives at
`runs/quadrado_demo/quadrado.skp` and its consensus uses
`dimension_mode: inner_clear` with walls at 100–213 pt.

**Root cause:** Agent treated each task as a fresh workspace
instead of operating on the existing canonical artifact. Three
specific drift triggers:

1. "I'll put outputs in `quadrado_delivery/`" — invents a delivery
   folder that doesn't exist in the project structure.
2. "I'll write a new consensus with cleaner coords" — shifts origin
   from (100,100) to (2.7,2.7) "for simplicity"; this changes the
   model fundamentally.
3. "Let me render via matplotlib for a quick visual" — produces a
   PNG that has nothing to do with the actual SKP geometry.

**Rule:** Outputs of any task against an existing artifact live in
the **same directory as the canonical artifact**. For
`runs/quadrado_demo/quadrado.skp`, all derivatives go to
`runs/quadrado_demo/quadrado_with_window.skp`,
`runs/quadrado_demo/quadrado_with_window_render.png`, etc. No
parallel "delivery" folders, no synthetic consensus with shifted
origin, no matplotlib-only "como ficaria" when the target is an
SKP that must open in SU.

**Anti-pattern signal:** creating a new directory outside
`runs/<existing_run>/` for outputs of a task against an existing
canonical artifact; mentioning "delivery" / "demo" / "visualization"
folders that aren't already in the tree.

**Repair landed:** LL-013 (canonical artifact rule); user MEMORY
`feedback_canonical_artifact_rule.md` (priority ROOT_RULE).

**See also:** FP-017 (rebuilding instead of in-place edit — the
sibling failure pattern that often triggers together with this one).

## FP-017 — Rebuild via consume_consensus.rb when in-place edit was correct (2026-05-23)

**Symptom:** Asked to add a window to an existing working SKP,
agent reaches for `tools.skp_from_consensus` which runs
`consume_consensus.rb` which calls `model.entities.clear!` and
rebuilds the entire model from the consensus JSON. The existing
working baseline (`quadrado.skp` with 34 raw entities in Layer0,
opens clean) is discarded; the rebuilt SKP uses a fundamentally
different topology (grouped walls + boolean carving) that exhibits
"abre o SU e fecha rápido" symptoms for the user.

**Root cause:** `consume_consensus.rb` is the **builder** pipeline,
not an editor. Its contract is: consensus.json → SKP from scratch.
When the goal is "add ONE element to an existing SKP", calling
`consume_consensus.rb` discards the validated topology in favour of
the consensus → SKP grammar, which produces a different
(legitimately different, but for THIS purpose wrong) SKP.

**Rule:** To **add** features (window, door, furniture) to an
existing SKP, **open the SKP and edit in-place** via SU Ruby API
(push/pull, add_face, add_line, intersect_with, erase_entities).
Never use `consume_consensus.rb`, which is `entities.clear!`-based
and only correct when the consensus IS the source of truth and you
want to rebuild from it.

**Repair pattern** (validated in quadrado window POC,
`runs/quadrado_demo/_add_window.rb`):
```ruby
m = Sketchup.active_model   # SU launched with target .skp as positional
ents = m.active_entities
# Find existing face by bbox criteria
target_face = ents.grep(Sketchup::Face).find { |f| ... }
m.start_operation('edit', true)
# Modify in-place: add_face for coplanar rect, intersect_with to
# force split, pushpull to carve, erase_entities for cleanup
m.commit_operation
m.save(out_path)
```

**Anti-pattern signal:** reaching for `tools.skp_from_consensus` or
`consume_consensus.rb` when the task description is "add X to
existing Y.skp"; any flow where the input SKP is touched only as
the launcher's positional argument (bootstrap) while the actual
geometry comes from a consensus rebuild.

**See also:** LL-013 (canonical artifact rule §5-step flow);
FP-016 (path proliferation, sibling).

## FP-018 — Hardcoded coordinates cause intersect_with float drift (2026-05-23)

**Symptom:** In-place window cut via `entities.intersect_with`
appeared to succeed (invariants_report passed 7/8) but left
vestigial slabs of 0.92 in² and a redundant coplanar 2232 in² face,
plus the inner wall area didn't change as expected.

**Root cause:** Wall coordinates hardcoded in the Ruby (`y_in =
142.284` from `134.784 + 7.5"` theoretical thickness) didn't match
what SU actually stored (`y_in = 142.26`, a 0.02" / 0.5 mm drift).
`intersect_with` requires float-exact coplanarity to merge faces;
the drift caused SU to create a thin extra slab between the two
"near-coplanar" planes instead of merging them.

**Rule:** Any geometry edit on an existing SKP must **read
coordinates from the model**, never hardcode them from theoretical
conversion constants. For wall thickness:
```ruby
south_faces = ents.grep(Sketchup::Face).select { |f|
  bb = f.bounds
  bb.min.y < 145 && (bb.max.y - bb.min.y).abs < 0.1 && bb.max.z > 100
}
outer = south_faces.min_by { |f| f.bounds.min.y }
inner = south_faces.max_by { |f| f.bounds.min.y }
wall_thick = inner.bounds.min.y - outer.bounds.min.y   # real value
```

Same principle applies to floor z=0, ceiling z=height, room
polygon vertices, etc. The model is the source of truth, not the
conversion math.

**Anti-pattern signal:** wall thickness, room dimensions, or any
edit coordinate computed via `0.19 * 39.3701` or `PT_TO_M * something`
without a `face.bounds.min.x` cross-check. Especially dangerous
combined with `intersect_with`, `Face#pushpull`, or any operation
that depends on float-exact alignment.

**See also:** LL-014 (read coordinates from model); LL-013
(canonical artifact rule §"sem reinterpretar dimensão/unidade").

## FP-019 — Python subprocess.terminate of SU confuses user about SKP stability (2026-05-23)

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

**See also:** FP-007 (welcome dialog — also a SU2026 launch
ergonomics issue); LL-009 (bootstrap .skp pattern).
