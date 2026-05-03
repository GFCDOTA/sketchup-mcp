# Validation Matrix

> Maps each kind of change to the validation it must pass. Use this
> when writing the "Validation" section of a PR.

## Matrix

| Change kind | Mandatory checks | Specialist agent |
|---|---|---|
| **Pure docs** (`docs/**/*.md`, `OVERVIEW.md`, `README.md`) | `git diff --stat` confirms only docs touched. Skip pytest if cheap. | docs-maintainer |
| **CI/Workflow** (`.github/workflows/*.yml`) | CI runs in PR (PR triggers itself). Watch the run. | ci-guardian |
| **Tooling/Config** (`pyproject.toml`, `requirements.txt`, `.gitignore`) | Fresh-venv install: `python -m venv /tmp/v && /tmp/v/bin/python -m pip install -e ".[dev]"`. Then `pytest -q [+ deselect set]` and `ruff check .`. | repo-auditor |
| **Pipeline geometry** (`extract/`, `classify/`, `topology/`, `model/`, `roi/`, `ingest/`) | pytest of touched modules + metric diff on planta_74 + AGENTS.md §2 invariants + visual inspection of `debug_walls.svg`. | geometry-specialist |
| **Openings detection** (`openings/`, `tools/extract_openings_vector.py`, `tools/render_openings_overlay.py`) | Count + kind + hinge/swing diff on planta_74 + visual overlay inspection. | openings-specialist |
| **Ruby/SU exporter** (`tools/consume_consensus.rb`, `tools/inspect_walls_report.rb`, autorun plugins, `tools/skp_from_consensus.py`, `.mcp.json`) | Run smoke harness; compare `inspect_report.json` before/after; visual inspection of .skp; constants justified. | sketchup-specialist |
| **Validator** (`validator/scorers/`, `validator/vision.py`, `validator/pipeline.py`, `validator/run.py`, `validator/service.py`) | Score diff per kind on the manifest entries. No pass→fail regression. | validator-specialist |
| **Performance / benchmarks** (`scripts/benchmark/*`) | Run benchmark on planta_74 with `--runs 3 --warmup 1`. CV < 10%. No stage > 20% slower vs baseline. | performance-specialist |
| **Hooks/agents/commands** (`.claude/**`) | `python .claude/hooks/pre_bash_guard.py` accepts test inputs. pytest tests for the hook. | repo-auditor + ci-guardian |
| **Pipeline schema** (`docs/SCHEMA-V2.md`, schema files) | All consumers of the schema audited. Backward compat documented. Migration plan for existing artifacts. **REQUIRES HUMAN APPROVAL**. | agent-coordinator (escalates) |
| **Threshold change** (any geometry threshold) | Empirical sweep on planta_74 + p10 + p12. Metric diff on each. Visual inspection of debug_walls.svg. **REQUIRES HUMAN APPROVAL**. | geometry-specialist (escalates) |

## Hard rules (non-negotiable for any PR)

1. **CI must be green** on the PR branch before merge (or the
   failure must be explicitly a baseline-known-failure).
2. **No new pytest failures vs the baseline** documented in
   `docs/repo_hardening_plan.md` (200 passed / 16 failed / 2 skipped
   as of 2026-05-03).
3. **No new ruff violation categories** (additional violations within
   existing categories OK during cleanup phase, but not new categories).
4. **No file outside the allowed scope** of the PR's stated kind.
5. **No commit message touching multiple kinds** ("fix CI + refactor
   tools + add docs" → split).

## How to interpret a verdict

- **APPROVE**: all checks green, ready to merge.
- **DISCUSS**: regression within tolerance, or trade-off worth a
  human eyeball. Open discussion in the PR before merging.
- **BLOCK**: invariant violated, regression beyond tolerance, or
  scope leak. Don't merge until addressed.

## When validation matrix doesn't fit

If a change spans multiple categories (e.g. a refactor that moves
files AND updates docs), invoke the `agent-coordinator` to dispatch
to multiple specialists and aggregate their verdicts.

If a change doesn't fit any row (e.g. adding a new entrypoint type),
update this matrix in the SAME PR that adds the entrypoint. Don't
let the matrix become stale.
