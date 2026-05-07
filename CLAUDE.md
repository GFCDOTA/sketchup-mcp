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
- `agent_improvements.md` — adjustments to specialist agents

Roadmap of pending work: [`docs/ROADMAP.md`](docs/ROADMAP.md).

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

### Known baseline on `planta_74` (vector pipeline)
- 33 walls, 11 rooms, 12 openings, 8 soft_barriers
- Generated via the documented 4-step flow (see `OVERVIEW.md` §4.4)

### Known baseline on `planta_74` (raster pipeline, OUTDATED)
- 94 walls, 14 rooms, 7 orphan_components, geometry_score 0.156
- 16 tests fail in main due to gate `len(strokes) > 200` in
  `classify/service.py:160`. Documented in
  `docs/repo_hardening_plan.md`. Address only with empirical
  threshold sweep on planta_74 + p10 + p12.

### Known SketchUp issues
- `inspect_walls_report.rb` doesn't embed SHA256 of inspected `.skp`.
- wall_gap openings are rendered as windows by default (caminho A);
  classifier window-vs-passage based on adjacent room context is the
  next step (caminho B). Designer must isolate/delete window groups
  on `windows` layer that should be passages — passage_marker still
  emits to `passages` layer for visibility.

### Recently fixed
- door_arc openings are now CARVED into walls (PR #42, `consume_consensus.rb`)
  and rendered with a visible swing leaf + 30° open
  (`feature/openings-as-components`).
- Window detection runs end-to-end (vector detector + 3-band
  rendering: peitoril 0–0.9 m, glass 0.9–2.1 m, verga 2.1–2.7 m).
  planta_74 specifically yields 0 vector windows (drawn inside wall
  hatch); the 3 wall_gaps detected render as windows.
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
