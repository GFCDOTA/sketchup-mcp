# CLAUDE.md — Constitution for sketchup-mcp

> Loaded automatically every Claude Code session. Operational memory.
> Treat as constitution, not as inspiration. If a request conflicts
> with this file, this file wins.

---

## Mission

Build a reliable pipeline:

```
PDF/floorplan -> extraction -> consensus_model.json -> validation -> renders -> SketchUp .skp
```

The priority is **structural fidelity for furniture/layout planning**,
not perfect CAD precision.

Two extraction tracks coexist:
- **Raster** (`ingest/`, `roi/`, `extract/`, `classify/`, `topology/`,
  `openings/`, `model/`) — legacy, fragments complex plans
- **Vector** (`tools/build_vector_consensus.py`,
  `tools/extract_room_labels.py`, `tools/rooms_from_seeds.py`,
  `tools/extract_openings_vector.py`) — newer, clean for vectorial PDFs

The Ruby/SketchUp side (`tools/consume_consensus.rb`,
`tools/inspect_walls_report.rb`, autorun plugins,
`tools/skp_from_consensus.py`) is the final step. **It is the most
expensive gate** and must run last, only when cheap gates pass.

---

## 0. Git Flow (INVIOLABLE)

- **Always** branch from `develop`. Never directly from `main`.
- **Always** open PRs against `develop`. Never directly to `main`.
- `main` only receives PRs that come from `develop`.
- Hotfix exception: a PR `hotfix/<slug> -> main` is allowed only when
  production is broken AND human approval is on record. After merge,
  immediately open `main -> develop` to sync.
- **Never** `git push --force` `main` or `develop`.
- **Never** `git commit` directly on `main` or `develop`.
- **Never** `git push --no-verify` or `--no-gpg-sign` without explicit
  human authorization.
- Branch naming: `feature/`, `fix/`, `chore/`, `docs/`, `perf/`,
  `refactor/`, `test/`, `agents/`, `tooling/`, `validate/`, `hotfix/`.
- Delete a feature branch (local + remote) after its PR is merged.
  `develop` and `main` are never deleted.

Detailed flow: [`docs/git_workflow.md`](docs/git_workflow.md).

---

## 1. Hard Safety Rules — never do these without explicit human approval

1. Delete or rewrite history under `runs/`, `patches/`, `docs/`,
   `vendor/`, or any baseline/diagnostic artifact.
2. Change the `consensus_model.json` schema (see `docs/SCHEMA-V2.md`).
3. Change geometry thresholds (e.g. `len(strokes) > 200` in
   `classify/service.py:160`, `snap_tolerance` in `topology/service.py`,
   `WALL_HEIGHT_M` / `PARAPET_HEIGHT_M` / `PARAPET_RGB` in
   `tools/consume_consensus.rb`).
4. Modify Ruby/SketchUp exporter logic
   (`tools/consume_consensus.rb`, `tools/inspect_walls_report.rb`,
   `tools/autorun_*.rb`, `tools/su_boot.rb`).
5. Apply patches under `patches/archive/` (07-09 are HIGH risk).
6. Move `tools/` wholesale or any high-risk entrypoint
   (`main.py`, `api/app.py`, `sketchup_mcp_server/server.py`).
7. Run `ruff --fix` over the entire repo.
8. Run any autoformatter over the entire repo.
9. Mix refactor + functional fix + performance optimization in one PR.
10. Skip the validation step (`pytest`, `ruff check`, smoke gates) on
    a PR that touches Python.

---

## 2. Pipeline Invariants (from `AGENTS.md` §2 — also inviolable)

The pipeline must NEVER:

1. **Invent rooms or walls.** If `polygonize` returns `[]`, output is
   `rooms=[]`. That is valid observation.
2. **Mask failures.** `rooms=0` is information; do not substitute by
   bbox or any synthetic fallback.
3. **Use bounding box as a substitute for a room.**
4. **Couple to a specific PDF.** Nothing hardcoded for `planta_74.pdf`,
   `proto_p10.pdf`, etc.
5. **Skip required debug artifacts.** `debug_walls.svg`,
   `debug_junctions.svg`, `connectivity_report.json` are mandatory.
6. **Leak ground-truth into the extractor output.** Scores are
   observational only.

If a change "would resolve the case" by violating an invariant,
**STOP** and report the trade-off.

---

## 3. The SketchUp Rule

SketchUp is the final gate, not the first. The export step spawns
SU 2026 (~5-90s, GUI process). Do not run it in tight loops.

**Before opening SketchUp:**

1. Validate the JSON structurally (walls/rooms/openings shape).
2. Generate cheap previews (top + axon PNG via `tools/render_axon.py`).
3. Run cheap validators (pytest subset, ruff).
4. Compute SHA256 of `consensus_model.json`.
5. Skip SketchUp if the hash matches the previous successful export
   (cache-by-content). `tools/skp_from_consensus.py` writes a
   sidecar `<out_skp>.metadata.json` with the consensus sha256;
   reruns short-circuit when the sha matches. Honor `--force-skp`
   to bypass. See `docs/performance/skip_unchanged_skp.md`.
6. Only then run `python -m tools.skp_from_consensus`.
7. Inspect the `.skp` automatically when possible
   (`tools/inspect_walls_report.rb` via the autorun plugin).
8. Open the `.skp` visually only when needed (final QA step).

The smoke harness `scripts/smoke/smoke_skp_export.py` enforces this
order automatically. Companion doc:
[`docs/validation/sketchup_smoke_workflow.md`](docs/validation/sketchup_smoke_workflow.md).
Honors `--skip-skp` (cheap gates only) and `--force-skp` (bypass
content-hash cache).

---

## 4. PR Standard

Every PR body must include:

```markdown
## Summary
1-3 bullets, what this PR is.

## What changed
List of files + brief reason.

## What did NOT change
Confirm scope: no algorithm, no schema, no thresholds, no Ruby/SU,
or whatever applies.

## Validation
Commands run + expected output (pytest, ruff, smoke, bench).

## Risks
What could go wrong.

## Rollback
Exact git revert / git push --delete commands.

## Next steps
Optional: what should follow this PR.
```

Keep PRs small. One PR = one idea. If a PR diff is > 500 lines and
not pure docs, split it.

---

## 5. Default Decision Rule

When in doubt, choose the conservative path:

- Document instead of changing code.
- Benchmark instead of optimizing blindly.
- Add a guardrail instead of trusting future authors.
- Add a deselect instead of muting an assertion.
- Open a draft PR instead of merging silently.

=======
- **Ask the user only for real blockers. Prefer autonomous
  investigation over questions.** A "real blocker" is one of:
  missing credential, missing required file, destructive risk,
  product decision the agent genuinely cannot infer, security-rule
  conflict, change forbidden by this CLAUDE.md, or operational /
  context-window limit. Anything else — read the code, run the
  tool, write the test, ship the PR.
---

## 6. Operational memory

Versioned learning loop:

```
EXECUTE -> MEASURE -> COMPARE -> RECORD -> UPDATE RULE -> OPEN PR
```

When something is learned, it goes to `docs/learning/`:

- `lessons_learned.md` — positive lessons
- `failure_patterns.md` — anti-patterns to never repeat
- `decision_log.md` — architectural decisions with date + author
- `validation_matrix.md` — what is validated by what
- `prompt_improvements.md` — prompts that worked / didn't
- `prompt_quality_rubric.md` — rubric + Prompt Contract template for autonomous tasks
- `agent_improvements.md` — adjustments to specialist agents

Roadmap of pending work: [`.ai_bridge/TODO_NEXT.md`](.ai_bridge/TODO_NEXT.md).
Historical roadmap archived at `docs/_archive/2026-05-cleanup/ROADMAP.md`.

---

## 7. Specialist agents

Defined in `.claude/agents/*.md`. Each agent has:
- a narrow mission,
- explicit allow/deny lists for files,
- mandatory checks,
- output format,
- examples of safe and forbidden tasks.

Available agents:
- `repo-auditor` — read-only repo health audit
- `geometry-specialist` — review extraction/topology/model changes
- `openings-specialist` — review door/window detection
- `sketchup-specialist` — review Ruby/SU exporter changes
- `performance-specialist` — benchmark + perf regression
- `validator-specialist` — validator/scoring changes
- `ci-guardian` — CI workflow health
- `docs-maintainer` — keeps docs in sync
- `agent-coordinator` — chooses which specialists to invoke

A subagent reads its own file plus this CLAUDE.md. Critical rules
are duplicated inside each agent file so they survive context
compaction.

---

## 8. Slash commands (playbooks)

Defined in `.claude/commands/*.md`:

- `/afk-maintain` — autonomous maintenance loop
- `/validate-skp` — JSON -> SKP via smoke gates
- `/perf-baseline` — capture timing baseline
- `/repo-audit` — run the auditor
- `/prepare-pr` — write a compliant PR body
- `/improve-agents` — propose changes to agent docs

---

## 9. Hooks (the electric fence)

Defined in `.claude/settings.json` + `.claude/hooks/`:

- `pre_bash_guard.py` runs before every Bash tool call. It rejects:
  - `git push origin main` (any path)
  - `git push --force` against `main` or `develop`
  - `git commit` while currently on `main` or `develop`
  - `rm -rf` against `runs/`, `patches/`, `docs/`
  - `ruff --fix .` or `ruff format .` over the whole repo
  - `Remove-Item -Recurse` against the same protected paths
  - destructive edits to `patches/archive/`

Hooks fail closed: when in doubt, block. Override is via the user
explicitly running the command outside Claude.

---

## 10. Pipeline state (for context)

### Visual Fidelity Gate (active policy, 2026-05-14)

> **Aggregate score is not visual fidelity.** A `verdict_top_level:
> PASS` from `tools/verify_fidelities.py` is meaningless unless the
> consensus has been compared to the source PDF and the seven
> visual evidence artifacts exist on disk.

Operational rules:

1. **No aggregate-score promotion to PASS without visual evidence.**
   `tools/verify_fidelities.py --require-visual-evidence` is the
   canonical entrypoint when the report's `verdict_top_level` will
   be acted on (PR gates, releases, end-of-cycle ship checks).
2. **Top-level PASS requires all seven artifacts** under the
   `--visual-evidence-dir`:
   `original_floorplan.png`, `skp_render.png`,
   `overlay_pdf_skp.png`, `diff_walls.png`, `diff_doors.png`,
   `diff_rooms.png`, `mismatches_list.md`. Missing any one
   downgrades the top-level to FAIL with
   `policy_violation: 2026-05-14_visual_fidelity_gate_required`.
3. **Per-axis verdicts are preserved** so the report still says
   which axis was algorithmically PASS/WARN/FAIL. Only the top
   level is downgraded; the operator sees both the raw axes and
   the gate's override reason.
4. **Eight failure conditions** are documented in
   `docs/protocols/visual_fidelity_gate_protocol.md`. Their
   algorithmic checks land in PR B
   (`tools/visual_fidelity_gate.py`). Until PR B ships, the gate
   runs in **artifact-presence mode**: a >0-byte file at the
   expected path counts as `present`.
5. **Backward compatibility** — the flag is opt-in. Calls without
   `--require-visual-evidence` are byte-equivalent to the prior
   contract; existing CI workflows are unaffected.
6. **Aggregate scores still useful** for incremental improvement
   tracking, regression detection, and per-axis triage. They are
   simply not authorized to gate a "ship this consensus" decision
   on their own.

This policy supersedes the 2026-05-13 operator-verbal-waiver
pattern (archived at `docs/_archive/2026-05-cleanup/operator_acknowledgment_2026-05-13.md`).
A verbal "trust me, looks fine" does not satisfy the seven-artifact
requirement.

### Known baseline on `planta_74` (vector pipeline)
- 33 walls, 11 rooms, 11 openings, 8 soft_barriers
- by_kind: 5 interior_door / 2 interior_passage / 2 window / 2 glazed_balcony
- by_decision: 6 clean / 5 debug
- room areas (post-Cycle-8b concave-hull default):
  SALA DE ESTAR 10.82, SALA DE JANTAR 13.07, COZINHA 8.80,
  LAVABO 3.40, A.S. 2.52, SUITE 01 26.75, SUITE 02 14.38,
  BANHO 01 5.48, BANHO 02 6.24, TERRACO SOCIAL 11.70,
  TERRACO TECNICO 1.61
- Total room polygon area: 104.78 m² (apartment nominal 74 m²;
  delta accounts for internal walls + 2 terraços)
- Fidelity Engine v1 baseline: global=0.917, 0 hard_fails,
  2 warnings (TERRACO TECNICO area marginal, adjacency_f1=0.67
  below 0.80 advisory threshold)
- Generated via the 5-step flow (see `OVERVIEW.md` §4.4) with
  the default `--use-concave-hull` flag (Cycle 8b 2026-05-08;
  pass `--no-concave-hull` to recover legacy convex behaviour)

### Known baseline on `planta_74` (raster pipeline, OUTDATED)
- 94 walls, 14 rooms, 7 orphan_components, geometry_score 0.156
- 16 tests fail in main due to gate `len(strokes) > 200` in
  `classify/service.py:160`. Tech debt documented in
  `.github/workflows/ci.yml` deselect list (BASELINE_KNOWN_FAILURES).
  Address only with empirical threshold sweep on planta_74 + p10 + p12.

### Known SketchUp issues
- (none open as of 2026-05-06; previous SHA256 + caminho-A items shipped)

### Canonical success reference — quadrado + window (2026-05-24)

The quadrado canonical fixture is the **reference of a correct
wall-shell + window-aperture pipeline output**. All inputs, expected
outputs, render, and helpers are versioned (do NOT re-derive from
scratch — read these paths first):

| Role | Path |
|---|---|
| Input consensus (with window) | `fixtures/quadrado/consensus_with_window.json` |
| Input consensus (empty room) | `fixtures/quadrado/consensus_empty.json` |
| Expected `_shell_polygon.json` | `docs/specs/_assets/quadrado_canonical_shell_polygon.json` |
| Expected geometry report | `docs/specs/_assets/quadrado_canonical_geometry_report.json` |
| Reference 3D render | `docs/specs/_assets/quadrado_canonical_success_render.png` |
| Render helpers | `tools/quadrado/render_view.{py,rb}` |
| Smoke gate (CI-ready) | `tests/test_quadrado_canonical_smoke.py` (14 tests) |
| Spec | `docs/specs/quadrado_demo_spec.md` |

**Reproduce from a fresh clone:** `python -m tools.build_plan_shell_skp fixtures/quadrado/consensus_with_window.json --out runs/<dir>/quadrado.skp`

**Rule for future agents:** when validating a pipeline change against
the quadrado, ALWAYS use these versioned inputs and compare against the
versioned reference outputs. Never invent a parallel fixture under
`runs/` (gitignored) and call it canonical. If the reference outputs
need to change, justify in the PR body — the spec calls this out
explicitly.

### Recently fixed
- **Wall shell canonicalisation: no more L-shape notches at outer corners**
  (2026-05-24, branch `feature/window-aperture-semantics`):
  `tools/build_plan_shell_skp.py wall_footprint()` was cutting each
  wall's 2D rectangle exactly at its centerline endpoints, leaving
  a `2*half × 2*half` L-shape notch at every outer corner where
  two perpendicular walls met. On the quadrado canonical fixture,
  the outer ring carried 12 vertices instead of the canonical 4.
  Fix: `wall_footprint` now extends by half-thickness at both
  endpoints (default), so adjacent perpendicular walls fully
  overlap in the corner cell. A `canonicalise_axis_aligned_polygon`
  pass after union+carve drops any leftover collinear redundant
  vertices. Stats carry `redundant_vertices_dropped` for visibility.
  Validation: 15 new canonical-shell tests + planta_74 idempotency
  + 92 plan-shell suite tests pass; quadrado now has outer ring
  = 4 canonical-corner vertices; planta_74 dropped from 8 to 7
  shell pieces (corner notches were causing extra fragmentation).
  ADR + LL-017 + FP-025 codify the rule. See §20 for permanent
  guardrail.
- **Window apertures: 3D post-extrude carve (no more door-like voids)**
  (2026-05-24, branch `feature/window-aperture-semantics`):
  `tools/build_plan_shell_skp.{py,rb}` historically carved every
  opening as a 2D full-height rectangle pre-extrude, then refilled
  windows with three stacked sub-volumes (sill / glass / lintel).
  Structurally that's three separate boxes inside a floor-to-ceiling
  void — semantically a door with infill, not a window. Affected
  the quadrado canonical fixture AND all 4 windows on planta_74.
  Fix: Python now routes `kind_v5 == 'window'` to a separate
  `window_apertures` list (NOT the 2D carve). Ruby
  `build_window_aperture_3d` reads that list, finds the host wall
  face after extrusion, adds a coplanar rect at sill-to-head only
  (SU auto-splits — perimeter remainder preserves wall mass), and
  pushpulls through to create a real through-hole. Glass sits at
  mid-thickness as `WindowGlass_Group_<id>` (separate top-level
  group). Door/passage/glazed_balcony stay on the 2D full-height
  path (correct for them).
  Validation: 15 contract tests + 9 geometry tests; planta_74's
  4 windows all route to the 3D path; PlanShell_Group preserves
  full [0, 2.70 m] height; WindowGlass_Group bbox is exactly
  [0.9, 2.1 m]. ADR-007 + LL-016 + FP-024 codify the rule.
  See CLAUDE.md §19 for the permanent guardrail.
- **Human-openings ground-truth pipeline shipped** (2026-05-11, PRs #112+#113+#115+#116):
  When a reviewer paints color blobs (#00ff00 green = interior_door,
  #ff00ff magenta = window, #ffa500 orange = glazed_balcony) on a planta
  render, the painted blobs are **mandatory ground truth** for openings —
  the detector loses every conflict. 5-tool pipeline:
  `tools/extract_human_openings.py` (image -> JSON via cv2 connected
  components + nearest-wall projection),
  `tools/apply_human_openings.py` (truth JSON -> consensus.openings with
  `geometry_origin="human_annotation"`),
  `tools/structural_checks_human.py` (C-H1..C-Hn gates: total + per-kind
  counts + explicit positional constraints),
  `tools/render_human_openings_overlay.py` (visual verification PNG),
  `tools/run_human_openings_pipeline.py` (one-shot runner).
  Schema: `fixtures/planta_74/human_openings_truth.schema.json`.
  Protocol: `docs/learning/human_openings_truth_protocol.md`.
  When `fixtures/planta_74/human_openings_annotation.png` exists, the
  pipeline runs in one command:
  `python -m tools.run_human_openings_pipeline`. **Never infer opening
  positions from the image visually and write them as synthetic — that
  recreates the fidelity-circular hallucination the protocol exists to
  prevent.** The PNG IS the truth.

  Related diagnostics this cycle:
  - `docs/diagnostics/2026-05-11_wall_candidates_audit.md` — refutes
    the wall-threshold-rejection hypothesis (planta_74 cluster 1
    captures 33/37 candidates at 89% tight; rejected filled paths are
    fixtures + legend, not dividers; stroked wall-like paths are
    >70% hatches; centerline polygonize is strictly worse than
    box-difference). The 7-room polygonize ceiling is HONEST given
    the PDF; the missing dividers between A.S./TERRACO SOCIAL/COZINHA/
    TERRACO TECNICO + SALA ESTAR/JANTAR genuinely don't exist as
    geometry, only as semantics. Hence the human-openings protocol.
  - `tools/polygonize_rooms.py` now consumes `consensus.soft_barriers`
    in its `unary_union` (PR #112). `--polygonize-door-max` default
    150pt (PR #113) bridges porta-vidro / glazed-balcony / peitoril
    gaps; planta_74 lifted 2 -> 7 rooms.
  - `tools/render_preflight.py` (PR #114) — visual preflight gate
    (axon + door audit D1..D7 + side-by-side + checklist).

- **Ruby exporter — human_annotation openings ignored by carve + hinge_side field mismatch**
  (2026-05-10, PR fix/consume-consensus-human-annotation-carving):
  Two cirurgical fixes in `tools/consume_consensus.rb`:
  (1) `CARVING_OPENING_ORIGINS` was `['svg_arc', 'svg_segments']` only; added
  `'human_annotation'` so openings injected by a human reviewer (via
  consensus patching) actually CARVE the host wall instead of rendering a
  door leaf stuck on top of solid masonry. (2) `add_door_leaf` was reading
  `opening['hinge']`, but schema 1.0.0 writes `opening['hinge_side']`, so
  every door rendered with the default `'left'` regardless of detector or
  human input. Now reads both with `hinge_side` preferred. Surfaced when
  reviewer-annotated 12-openings consensus produced a structurally broken
  SKP (paredes fragmentadas + portas coladas em paredes maciças). Smoke
  passes (`runs/smoke/20260511T015600Z/`).
- **FP-012 — Convex-hull room clip leaks watershed into exterior**
  (Cycle 8b, 2026-05-08, PR #N): `tools/rooms_from_seeds.py` now
  defaults to `shapely.concave_hull` over wall endpoints (ratio 0.5)
  instead of `cv2.convexHull`. SUITE 01 polygon dropped from
  69.91 m² → 26.75 m². Fidelity Engine v1 step in
  `quality_gates.yml` promoted from advisory (continue-on-error)
  to hard merge blocker. Pass `--no-concave-hull` to recover legacy
  behaviour for plants whose envelope is genuinely convex.
- `inspect_walls_report.rb` now embeds SHA256 + size of the inspected
  `.skp`, plus optional `bounds_check` against a consensus JSON
  (`feature/skp-structural-gate-inspector-v2`, schema_version 1.0).
- door_arc openings are now CARVED into walls (PR #42) and rendered
  with a visible swing leaf + 30° open (PR #44).
- Window detection runs end-to-end. planta_74 yields 0 vector
  windows (drawn inside wall hatch); the 3 wall_gaps detected on it
  are classified by adjacent room context (PR #45 caminho B):
  `interior_door | interior_passage | window | glazed_balcony`.
  See `tools/classify_openings_by_room_context.py`.
- Stage 1 uncertainty contract on each opening:
  `confidence` / `decision` / `hypotheses` / `evidence` (PR #46).
- Versioned baseline regression gate
  `tests/baselines/planta_74.json` + `tests/test_planta_74_truth_gate.py`
  (PR #47, 33/11/11/8 locked).
- First external truth: `ground_truth/planta_74_micro.json` +
  `tools/micro_truth_gate.py` (PR #48, SALA DE ESTAR score 1.0).
- 3-pt parapet/wall coincidence filter
  (`commit 7fbd531`) — eliminates the "rodapé branco" band.

---

## 11. Patches inventory

| Patch | Status | Notes |
|---|---|---|
| `patches/02-density-trigger.py` | NOT applied | Medium risk; first attempt failed |
| `patches/03-quality-score.py` | APPLIED (`b798881`) | Honest scoring |
| `patches/04-roi-fallback-explicit.py` | APPLIED (`7fb1d80`) | Schema-additive |
| `patches/archive/07-reconnect-fragments-FIXED.py` | NOT applied | HIGH risk: new dep, core algorithm change |
| `patches/archive/08-unet-oracle-FIXED.py` | NOT applied | HIGH risk: torch + offline weights |
| `patches/archive/09-afplan-convex-hull.py` | NOT applied | HIGH risk: alternative extractor |

Never apply archive patches without an explicit, signed-off PR plan.

---

## 12. Ferramentas externas úteis (kept for searchability)

- `cv2.createLineSegmentDetector` — LSD real, OpenCV 4.5.4+
- `scipy.spatial.cKDTree` — nearest-neighbor O(n log n)
- `skimage.morphology.skeletonize(method='lee')` — robust on thick walls
- `networkx` — cycle detection, connectivity
- `shapely.polygonize` — closed-room detection
- DL extras (`[dl]`): `torch`, `torchvision`, `gdown`,
  `scikit-image`, `anthropic`. Only the `dl` extra is allowed to
  pull these in.

---

## 13. Last-updated marker

- **2026-05-24** — §20 wall shell canonicalisation added.
  Wall footprints extend by half-thickness at endpoints by default;
  `canonicalise_axis_aligned_polygon` drops collinear redundant
  vertices after union+carve. Quadrado outer ring drops from 12 to
  canonical 4 vertices. Reference: `tools/build_plan_shell_skp.py`
  (`wall_footprint`, `canonicalise_axis_aligned_polygon`),
  `tests/test_wall_shell_canonical.py` (15 tests + planta_74 regression),
  LL-017, FP-025. Locks the no-notches/no-slivers rule.
- **2026-05-24** — §19 window vs door opening semantics added.
  Window apertures are now 3D post-extrude carves; doors and
  passages stay on the 2D full-height path. Reference:
  `tools/build_plan_shell_skp.{py,rb}` (`build_window_aperture_3d`
  + `WINDOW_APERTURE_KINDS`), `tests/test_window_aperture_contract.py`
  (15 tests), `tests/test_window_aperture_geometry.py` (9 tests),
  ADR-007, LL-016, FP-024. Locks the no-door-like-void rule for
  windows on both the quadrado canonical fixture and planta_74.
- **2026-05-23** — §18 SU runner mode protocol added. Three modes
  (`headless`/`interactive`/`attach`) with `interactive` as safe
  default. Reference helper `tools/su_runner_safety.py` exports
  `parse_mode` + `should_terminate` + `is_attach` + `log_mode`; 35
  unit tests in `tests/test_su_runner_safety.py`. Closes the
  anti-pattern documented in FP-023 (subprocess.terminate of SU
  confuses user about SKP stability). Cross-ref: LL-015.
- **2026-05-14** — Visual Fidelity Gate policy added to §10. Aggregate
  score cannot promote `verdict_top_level: PASS` without the seven
  visual evidence artifacts on disk. `tools/verify_fidelities.py`
  gains `--require-visual-evidence` (opt-in flag, default off →
  backward compatible) that FAILs the top-level when artifacts are
  missing/incomplete and stamps the report with
  `policy_violation: 2026-05-14_visual_fidelity_gate_required`.
  Full protocol: `docs/protocols/visual_fidelity_gate_protocol.md`.
  Algorithmic checks land in PR B
  (`tools/visual_fidelity_gate.py`); PR A is artifact-presence only.
  Supersedes the 2026-05-13 operator-verbal-waiver pattern.
- **2026-05-11** — added human-openings ground-truth protocol entry to
  §10. The PNG annotation at
  `fixtures/planta_74/human_openings_annotation.png` is the source of
  truth for openings on planta_74; the detector is subordinate.
  Cross-references the 4-PR FP-014 cycle (#112/#113/#114/#115/#116).
- **2026-05-07** — added §17 Non-Stop Autonomy Rule
  ("DONE IS NOT STOP"); reinforces §14 with explicit twelve-question
  gate before any stop and an end-of-cycle reporting format.
- **2026-05-06** — strengthened §5 wording (autonomous-first); added
  §14 Autonomous Continuation Protocol, §15 Repository Hygiene
  Protocol, §16 Review Frequency.
- **2026-05-03** — converted to constitution form, added agents/hooks
  references, develop-first git flow, SketchUp-as-last-gate rule.
- Previous version: 2026-04-21 (preserved in git history).

---

## 14. Autonomous Continuation Protocol

Claude does NOT stop after completing a single task when there is a
safe, valuable next technical step. The default loop is:

```
READ -> DIAGNOSE -> PLAN -> EXECUTE -> VALIDATE -> RECORD -> COMMIT -> CONTINUE
```

Per cycle, do all of the following:

1. **READ** — at session start, read `CLAUDE.md`, run `git status`,
   identify current branch + recent commits + last reports.
2. **DIAGNOSE** — pick the highest-ROI bottleneck with concrete
   evidence (file path, log line, test output, metric delta).
3. **PLAN** — answer internally before editing:
   - What is the most likely bottleneck?
   - What evidence proves it?
   - What cheap validation can confirm it?
   - What is the smallest safe change?
   - What test prevents regression?
   - What can break?
   - What should be documented?
4. **EXECUTE** — small, verifiable changes on a properly-named
   branch (`feature/`, `fix/`, `chore/`, `docs/`, `refactor/`, etc.).
5. **VALIDATE** — pytest, ruff, smoke, gate run; capture output.
6. **RECORD** — register learning in `docs/learning/` when relevant;
   update `docs/ops/` for long-session snapshots.
7. **COMMIT** — small commit with the standard message format; or
   give an explicit reason for not committing.
8. **CONTINUE** — pick the next ROI item. Do NOT ask the human
   what to do next when there is a safe technical step.

**Specialist agents in parallel** — when work decomposes cleanly
(e.g., one agent audits the consensus while another drafts the test),
launch them in a single multi-tool message.

**Consult GPT (or local LLM) via bridge** when there is an ambiguous
bug, an architectural decision, a hard regression, an uncertain
validation, or a relevant trade-off. Do not consult for trivial calls.

**Stop only on real blockers.** When blocked, the report must list:
current state, evidence, attempts, exact blocker, and the next
commands needed to resume.

**A cycle is complete only when all of the following are true:**
- validation evidence exists (test result / metric / artifact);
- learning recorded if the cycle produced one;
- `git diff` reviewed before commit;
- commit shipped OR explicit reason logged for not committing;
- next-step ROI candidate identified.

---

## 15. Repository Hygiene Protocol

> **Canonical policy:** [`docs/REPO_HYGIENE.md`](docs/REPO_HYGIENE.md).
> **Canonical gate list:** [`docs/GATES.md`](docs/GATES.md) §G-REPO-HEALTH
> + §G-PROJECT-STATE.
> **Automated enforcement:** `tools/repo_health_gate.py` (audit /
> check / fix) + `scripts/project_state_check.py` (canonical-paths
> check). CI: `.github/workflows/repo_health.yml`.
>
> **Frase-regra permanente:** No new artifact without a home, no new
> document without status, no generated output as source of truth,
> and no PR merged without repo health passing.

Every autonomous cycle includes a lightweight repo-hygiene pass.
The agent looks for:

- obsolete `.md` files
- duplicate reports
- stale JSONs
- generated PNG/SVG no longer referenced
- old smoke outputs
- temporary scripts
- abandoned dashboard artifacts
- docs that contradict current behavior
- loose files in the repo root

**Never delete blindly.** Before removing or moving any file:

1. Search for references in: `README.md`, `CLAUDE.md`, `docs/`,
   `tests/`, `scripts/`, `tools/`, CI workflows, dashboard, Python
   imports, Ruby scripts, smoke commands.
2. Classify each suspect as one of:
   - `active`
   - `historical baseline`
   - `diagnostic artifact`
   - `generated output`
   - `duplicate`
   - `obsolete`
   - `unknown / preserve`
3. **Preserve by default**: ground truth, baselines, regression
   snapshots, reports used by tests, files referenced by docs,
   artifacts needed to reproduce bugs, anything inside protected
   paths (`runs/`, `patches/`, `docs/`, `vendor/` per §1).
4. When in doubt → archive / quarantine instead of delete.
5. Cleanup ships in its **own commit**, separate from any
   algorithmic change.
6. Never mix repo cleanup with risky algorithmic changes in the
   same PR.

**Suggested commit messages:**
- `chore: clean obsolete generated artifacts`
- `docs: archive stale operational notes`
- `chore: remove unreferenced markdown files`

**Every cleanup must report:**
- files removed
- files archived
- files preserved + why
- reference searches performed
- validations executed (pytest / smoke / dashboard build)

**Cheap automated checks before every commit:**
```bash
python scripts/project_state_check.py       # G-PROJECT-STATE
python tools/repo_health_gate.py --mode audit  # G-REPO-HEALTH (read-only)
```

CI runs the strict equivalents on every PR
(`.github/workflows/repo_health.yml`); the local commands above are
the same gates in audit form, so any local clean run reproduces CI.

---

## 16. Review Frequency

CLAUDE.md is the operational source of truth and is read **every
session**. Update cadence:

- **Read** at the start of every session.
- **Verify** before any risky edit (Ruby/SU/schema/threshold).
- **Verify conformance** before every commit.
- **Update `docs/ops/`** at the end of long sessions.
- **Update `docs/learning/`** when there is a new bug, failure
  pattern, validation rule, or agent improvement.
- **Promote repeated failures to CLAUDE.md** immediately.
- **Compact CLAUDE.md** every 3-5 PRs OR once per week, whichever
  comes first. Strip duplication; refresh §10 known-issue list.

**Add to CLAUDE.md only when the information will change future
agent behavior.** Do not add:

- execution logs
- one-off command outputs
- temporary metrics
- single-execution observations
- PR summaries

These belong in:

- `docs/ops/`
- `docs/learning/`
- `docs/adr/`
- `runs/`
- `artifacts/`

---

## 17. Non-Stop Autonomy Rule

Completing the requested scope is **not** a stopping condition.

When a task, queue, validation, PR review, bugfix, or stage finishes,
Claude must:

1. Record the result in `.ai_bridge/HANDOFF.md` and `CURRENT_STATE.md`.
2. Update `.ai_bridge/TODO_NEXT.md` with real pendencies.
3. Pick the next highest-ROI safe item.
4. Start the next cycle without asking the human.
5. Continue while there is a safe technical step to take.

> **DONE IS NOT STOP. DONE MEANS PICK NEXT HIGHEST-ROI TASK.**

The mandatory loop is `READ → DIAGNOSE → PLAN → EXECUTE → VALIDATE →
RECORD → COMMIT → CONTINUE` (see §14 for the cycle's per-step gates).

Before stopping, Claude internally checks all twelve:

1. Open PR?
2. Local branch without PR?
3. Failing test?
4. `TODO_NEXT.md` item?
5. `HANDOFF.md` pending?
6. Documented known failure?
7. Safe cleanup pending?
8. Stale doc?
9. Broken dashboard/report?
10. Validation improvement available?
11. Next-highest-ROI gate?
12. Anything safe to measure / validate / clean / document / prep?

**Any** answer of "yes" → keep going.

Stop only on a real blocker:

- missing credential
- missing required file/artifact
- nonexistent branch with no safe alternative
- destructive conflict
- data-loss risk
- §1 / §2 / §3 hard rule blocks the action
- human approval required and not on record
- forbidden operation on `main` / `develop`
- tool / context / environment limit
- operational failure with no workaround
- environment unavailable

When stopped by a real blocker, leave: current state, evidence, what
was attempted, why blocked, exact next commands, and the next-best
item if the blocker is resolved.

### End-of-cycle reporting format

Each cycle ends with:

```
## Cycle Completed
What finished.

## Evidence
Tests, reports, PRs, files, metrics.

## Recorded State
Files in .ai_bridge / docs that were updated.

## Next Highest-ROI Task
Which next item was picked and why.

## Continuing
First action of the next cycle.
```

**Important:** "do not stop" never authorizes risky actions. This rule
operates *inside* the safety boundary set by §1, §2, §3, §9, the git
flow rules, and the validation gates.

---

## 18. SU runner mode protocol (LL-015, FP-023)

Every Python/Ruby tool that calls `Popen` on `SketchUp.exe` MUST
declare a runtime mode and behave accordingly:

| Mode | Termination |
|---|---|
| `headless` / `ci` | MAY terminate ONLY `proc.pid` (own child). NEVER `taskkill /IM SketchUp.exe`. |
| `interactive` / `debug` | MUST NOT terminate. Done marker = artifact ready, not "kill SU". |
| `attach` / `manual` | NEVER touch any SU process. Read files only. |

**Safe default is `interactive`** — a runner without a declared
mode behaves as if `interactive` (no termination). This protects
any concurrent human SU session.

Implementation contract:
- Accept mode via `RUN_MODE` env, `--mode {headless,interactive,attach}` CLI, or `--no-terminate` shorthand.
- Print at launch: `[su-runner] mode=<X>; terminate_on_done=<bool>`.
- Document destructiveness in docstring + `--help`.
- In `headless` mode, terminate only own `proc.pid` (never broader kill).

Reference helper: `tools/su_runner_safety.py` exports `parse_mode`,
`should_terminate`, `is_attach`, `log_mode`. Covered by 35 unit
tests in `tests/test_su_runner_safety.py`.

See LL-015 (positive rule) and FP-023 (anti-pattern).

---

## 19. Window vs door opening semantics (LL-016, FP-024, ADR-007)

> **Window openings must be wall-hosted partial-height openings.
> They must preserve wall mass below and above the opening and must
> never be represented as door-like full-height voids unless
> explicitly classified as doors.**

This is the architectural contract of a window. The exporter encodes
it structurally — in the topology of the produced SKP — not
cosmetically (via material colours).

**Routing table** (`tools/build_plan_shell_skp.py` + `.rb`):

| Normalised `kind_v5` | 2D pre-extrude carve | 3D post-extrude aperture | Wall mass below sill | Wall mass above head |
|---|---|---|---|---|
| `interior_door` | full-height | — | no | no |
| `interior_passage` | full-height | — | no | no |
| `glazed_balcony` (porta-vidro) | full-height | — | no | no |
| `window` | **NEVER** | **`build_window_aperture_3d`** | **yes (peitoril)** | **yes (verga)** |

Window apertures are carved by `build_window_aperture_3d` in
`tools/build_plan_shell_skp.rb`:
1. Find host wall lateral face spanning [0, WALL_HEIGHT_IN].
2. Read its fixed coord from `face.bounds` (LL-014).
3. Add coplanar rect at z ∈ [WINDOW_SILL_IN, WINDOW_HEAD_IN] — SU
   splits the host face; perimeter remainder preserves wall mass.
4. `pushpull(-real_thickness_in)` → real through-hole.
5. Emit `WindowGlass_Group_<id>` at mid-thickness (separate
   top-level group). NO sill/lintel sub-groups.

**Detection signature of the bug (FP-024) — must NEVER appear in
a healthy build:**
- `Window_Group_<id>_sill` group at `bbox_m.z = [0, 0.9]` (sill on
  the floor — door-like void with infill).
- `Window_Group_<id>_lintel` group.
- `PlanShell_Group.bbox_m.max.z` < WALL_HEIGHT_M (wall carved short).

**Validation gates:**
- `tests/test_window_aperture_contract.py` (15 tests) — Python
  contract; includes a planta_74 regression that locks 4-window
  routing.
- `tests/test_window_aperture_geometry.py` (9 tests) — SKP /
  geometry-report invariants; skips cleanly when no SKP present.

See ADR-007 (the decision document), LL-016 (positive rule),
FP-024 (anti-pattern), `docs/specs/quadrado_demo_spec.md` §6.4
(in-place edit pattern adopted by the 3D carve).

---

## 20. Wall shell canonicalisation (LL-017, FP-025)

> **Wall footprints must extend by half-thickness at BOTH endpoints
> along the wall's own axis. After `unary_union` and carve, the
> resulting polygon must be canonicalised: drop any vertex
> sandwiched between two same-cardinal-direction edges. Axis-aligned
> wall input must produce axis-aligned output with no stepped
> notches, no slivers, no overhanging segments.**

This is the canonical corner-completion rule. Without it, the union
of two perpendicular wall rectangles (each cut exactly at its
centerline endpoints) leaves a `2*half × 2*half` L-shape notch at
each outer corner — the FP-025 "tecos" signature.

**Implementation contract** (`tools/build_plan_shell_skp.py`):

1. `wall_footprint(wall, extend_endpoints=True)` defaults to
   extension. Opt-out (`extend_endpoints=False`) only for unit
   tests that need the raw box.
2. After `unary_union(wall_footprints)` and `shell.difference(carve_union)`,
   each retained polygon passes through
   `canonicalise_axis_aligned_polygon(poly)` which drops collinear
   redundant vertices on every ring (outer + interiors).
3. Stats carry `redundant_vertices_dropped` so regressions are
   visible in the artifact. Quadrado-healthy = 0 (extension alone
   produces canonical union); non-zero indicates the canonicaliser
   earned its keep on mid-wall carves.

**Detection signature of the bug — must NEVER appear in a healthy
build:**
- Quadrado outer ring with > 4 vertices (notches at corners).
- Outer vertices off `{(97.3, 97.3), (216.384, 97.3),
  (216.384, 216.384), (97.3, 216.384)}` for the canonical fixture.
- Non-axis-aligned edges from axis-aligned input.
- `slivers_removed > 0` on planta_74.

**Validation gates:**
- `tests/test_wall_shell_canonical.py` (15 tests) — wall_footprint
  extension, quadrado canonical 4-vertex outer + inner, edge
  axis-alignment, canonicaliser unit tests, planta_74 regression
  (canonicaliser idempotent + no slivers + all edges axis-aligned).

See ADR-007 (window aperture fix landed first; this corner fix
complements it on the wall side), LL-017 (the positive rule),
FP-025 (anti-pattern), ADR-003 (the broader plan-shell exporter).

---

## 21. Terminal-first GitHub auth & PR workflow (LL-018)

> **Before requesting any manual action for GitHub** (opening /
> merging / commenting on PRs, listing checks, calling the API),
> walk this recovery ladder. If `git push` works on this machine,
> the cached token can create PRs.

**Ladder** (canonical procedure in
[`docs/protocols/terminal_first_github_auth.md`](docs/protocols/terminal_first_github_auth.md)):

1. `gh auth status` — try `gh` directly first.
2. `git ls-remote origin` — confirm Git can reach GitHub.
3. `git credential fill` — pull the cached token (NEVER echo).
4. `GH_TOKEN=… gh pr create …` — temporary env var, unset after.
5. `curl https://api.github.com/…` — REST API fallback.
6. **Only NOW** request manual action, with the diagnostic trail.

**Token-hygiene non-negotiables:**
- NEVER print the token to stdout / stderr / logs.
- NEVER paste it into a PR body, commit, or any tracked file.
- Token only lives in a local shell var or `GH_TOKEN` env.
- Unset/clear the variable at end of cycle.
- Evidence about token use is masked as `ghs_***`, not the value.

See LL-018 (the lesson + context),
`docs/protocols/terminal_first_github_auth.md` (the full procedure
with bash + PowerShell snippets), LL-012 (same operational
philosophy applied to PATH lookups).

---

## 22. Multi-agent coordination (LL-019)

> **Root rule:** multiple autonomous agents MUST NEVER share the
> same physical working directory. `git worktree add` per
> agent / per session is the default isolation mechanism. Lock files
> are advisory only — the worktree is the architectural safety, not
> a courtesy marker.
>
> Canonical protocol: [`docs/AGENT_COORDINATION.md`](docs/AGENT_COORDINATION.md)
> (the long form with copy-paste snippets).
>
> **In multi-agent mode, never assume sole authorship of remote
> state.** Other agents (Claude or human) may push commits, merge
> PRs, delete branches, or even check out a different branch in
> any working tree between any two of your commands.

**Mandatory checklist before any GitHub mutation** (merge, close,
delete branch, push, REST write):

1. `git fetch --all --prune` — surface remote deletes + new commits.
2. `git rev-parse origin/develop` — confirm base HEAD before basing /
   rebasing / merging.
3. `gh pr view <n>` immediately before any per-PR action — never
   reuse a value from an earlier turn.
4. **Diff snapshot vs current state** and report out-of-band changes
   in the same response that performs the mutation.
5. **Operate from your own `git worktree`** — never from the
   canonical clone that peer agents may also be using.
6. **Do not trust snapshots older than 30–60 s** for destructive
   actions.
7. **If state changed mid-operation**, stop, document, re-classify
   before continuing.

**Mandatory checklist before every commit:** confirm current branch,
HEAD SHA, and `git diff --stat HEAD`. No unexpected files. See
[`docs/AGENT_COORDINATION.md`](docs/AGENT_COORDINATION.md)
"before every commit".

**Mandatory checklist after every commit:** verify `git log
--oneline -1`, push ASAP, record SHA in `.ai_bridge/HANDOFF.md`.
See [`docs/AGENT_COORDINATION.md`](docs/AGENT_COORDINATION.md)
"after every commit".

**Concurrency incident** — if branch / HEAD / working tree changes
unexpectedly between tool calls: STOP, capture state, report to
user in the same response, wait for instruction before any new
mutation. Full recovery in
[`docs/AGENT_COORDINATION.md`](docs/AGENT_COORDINATION.md)
"Concurrency incident".

**Coordination surface:**
- `.ai_bridge/HANDOFF.md` is the **tracked, public** coordination
  file — use it for "last known good state" + "what I just did".
- `.ai_triage/` and gitignored scratch dirs are **agent-local
  only** — invisible to peers; do NOT use for coordination.
- Commit messages, PR titles, branch names are **public signals**
  — write them so peer agents can route around your work.

**Forbidden even under multi-agent pressure:**
- `git push --force` to any shared branch.
- Deleting a branch with an open PR.
- Closing a PR without a comment.
- Touching `main` directly.
- Editing files in a peer agent's branch from a shared working
  tree (use your own worktree).

Full procedure with copy-paste snippets:
[`docs/AGENT_COORDINATION.md`](docs/AGENT_COORDINATION.md).

See LL-019 (the lesson + incident timeline),
LL-018 (same operational philosophy applied to credentials),
LL-012 (fix tooling access before falling back to manual).

---

## 23. Artifact policy — `.skp` is the deliverable

> **Root rule:** `.skp` is the primary deliverable of this project.
> Do NOT treat every `.skp` as disposable just because `/runs/` is
> gitignored.
>
> Canonical policy: [`docs/ARTIFACT_POLICY.md`](docs/ARTIFACT_POLICY.md)
> (the long form with promotion procedure + LFS escape hatch).

**Two-folder split** (both tracked, neither gitignored):

```
artifacts/
  human_review/<plant>/       ← Felipe / reviewer-facing
    <plant>_<descriptor>.skp  ← THE DELIVERABLE
    <plant>_<descriptor>.png  ← optional supporting render
    README.md
  agent_inputs/<plant>/       ← agent / test plane (JSON / reports / pointer doc)
    README.md
```

**Promote `runs/<id>/foo.skp` → `artifacts/human_review/<plant>/`
when ANY of these is true:** canonical success / user review /
fidelity comparison / claimed working output / demo proof.

**Inviolable**: **No PR may claim "SKP generated successfully"
unless the reviewable `.skp` is committed in
`artifacts/human_review/<plant>/`.** If you cannot commit the
`.skp` (size > LFS threshold, missing SU, etc.) the task FAILS —
do not silently drop the deliverable.

**Gate enforcement:** `tools/repo_health_gate.py` allows
`artifacts/human_review/` and `artifacts/agent_inputs/` as
valid tracked paths for `.skp` (and other generated suffixes);
tracked `.skp` files outside those paths still fire `E002`
(`generated-in-wrong-path`).

**File size:** for `.skp` > 5 MB, configure Git LFS first
(`git lfs track "artifacts/human_review/**/*.skp"`); do NOT
skip the commit. The gate's `E005 heavy-file-no-allowlist`
fires at 5 MB as the "configure LFS now" signal.

**Migration of existing tracked `.skp` files:** policy is
forward-looking. `fixtures/planta_74/skp_final_model.skp` stays
at its current path until a future PR refreshes that build (per
ARTIFACT_POLICY §6). Do NOT mass-move.

See `docs/ARTIFACT_POLICY.md` for: full promotion procedure,
agent_inputs vs human_review boundary, what does NOT belong in
`artifacts/`, LFS configuration commands.
