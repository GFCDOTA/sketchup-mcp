# Contributing to sketchup-mcp

> **Status:** Canonical (2026-05-24).

This file is the short version for humans + agents who want to ship a
change without re-reading the entire `CLAUDE.md` constitution every
time. **`CLAUDE.md` is the authoritative source for the rules.** When
the two disagree, `CLAUDE.md` wins. This doc is a navigator, not a
constitution.

## TL;DR

```
1. branch off `develop` (never `main`)
2. small, focused change (one idea per PR)
3. pytest + ruff + smoke gates clean
4. PR against `develop` using the standard PR body template
5. wait for review — CI + spec_harness comment must be green/observational
```

## Branch flow

- `main` — production. Only receives PRs from `develop`.
- `develop` — integration. All feature branches target here.
- Feature branches: `feature/`, `fix/`, `chore/`, `docs/`, `perf/`,
  `refactor/`, `test/`, `agents/`, `tooling/`, `validate/`, `hotfix/`.
- One branch = one PR = one idea. Diff > 500 lines that isn't pure
  docs needs to be split.

Forbidden by `.claude/hooks/pre_bash_guard.py` (these will be
rejected automatically — you don't need to remember them, the hook
does):

- `git push origin main`
- `git commit` while on `main` or `develop`
- `git push --force` against `main` or `develop`
- `rm -rf` against `runs/`, `patches/`, `docs/`
- `ruff --fix .` or `ruff format .` over the whole repo

## Before the first commit

- Read `CLAUDE.md` once. **Especially §0 (git flow), §1 (hard safety
  rules), §2 (pipeline invariants), §3 (SketchUp rule), and §4 (PR
  standard).**
- Skim the relevant ADR (`docs/adr/`) for the area you're touching.
- Check `docs/learning/failure_patterns.md` for FP-NNN entries
  related to your area.

## Required toolchain

| Tool | Version | Used for |
|---|---|---|
| Python | 3.12 | All Python code |
| `uv` | latest | Install: `uv pip install -e ".[dev]"` |
| Ruby | 3.2+ | Only the syntax check in CI; you don't need it locally unless touching `tools/*.rb` |
| SketchUp 2026 | exact | Final gate; smoke runs without it via `--skip-skp` |
| `gh` CLI | optional | PR creation; manual via web UI is the documented alt |

Quickstart:

```bash
git clone <repo>
cd sketchup-mcp
uv pip install -e ".[dev]"
pytest -q
ruff check .
```

## Local validation before pushing

The CI workflow runs:

```bash
pytest -q --tb=short \
  --deselect tests/test_planta_74_regression.py \
  --deselect tests/test_cubicasa_oracle.py \
  --deselect tests/test_oracle.py \
  --deselect tests/test_f1_regression.py::test_raster_byte_identical_on_planta_74 \
  --deselect tests/test_f1_dashboard.py::test_dashboard_runs \
  --deselect tests/test_text_filter.py \
  --deselect tests/test_orientation_balance.py \
  --deselect tests/test_pair_merge.py
```

The deselects are documented dívida (see
`docs/learning/baseline_known_failures_audit.md`). Locally without
the deselects you'll see 11 pre-existing failures — none are your
fault unless you just landed a real regression in those areas.

Lint:

```bash
ruff check <files-you-changed>     # cirurgical — don't run on the repo
```

Smoke harness (no SketchUp):

```bash
python scripts/smoke/smoke_skp_export.py \
  --consensus tests/fixtures/smoke_consensus.json \
  --out-dir runs/smoke/local \
  --skip-skp
```

## PR body template

Every PR body should include all of these sections. The PR description
is the artefact reviewers read; if it's incomplete the review is
incomplete.

```markdown
## Summary
1–3 bullets, what this PR does.

## What changed
List of files + brief reason.

## What did NOT change
Confirm scope: no algorithm, no schema, no thresholds, no Ruby/SU, …

## Validation
Commands run + expected output (pytest, ruff, smoke, bench).

## Risks
What could go wrong.

## Rollback
Exact `git revert` / `git push --delete` commands.

## Next steps (optional)
What should follow this PR.
```

A passing CI is necessary but not sufficient — the spec_harness
comment (Phase 2, non-blocking) is also part of the signal.

## Spec-driven changes

If your change touches anything in the architectural-fidelity surface
(rooms, openings, soft_barriers, fidelity scores), follow the
**SDD workflow**:

```
SPEC → HARNESS FAILING → FIX → BEFORE/AFTER EVIDENCE → REGRESSION LOCK
```

1. Write the spec contract first (`specs/<planta>/<aspect>.spec.yaml`)
2. Confirm `tools/spec_harness.py` FAILS the new contract on the
   pre-fix consensus
3. Implement the fix on a separate commit / PR
4. Capture before/after `spec_harness_report.json` next to overlay
   PNGs in `runs/.../evidence/`
5. Add a pytest test that pins the post-fix behaviour

See `docs/engineering/spec_driven_development.md` for the full
framework.

## Specialist agents

`.claude/agents/*.md` defines narrow-mission agents with explicit
allow/deny lists:

- `repo-auditor` — read-only repo health
- `geometry-specialist` — extraction / topology / model changes
- `openings-specialist` — door / window detection
- `sketchup-specialist` — Ruby / SU exporter
- `performance-specialist` — perf + benchmark
- `validator-specialist` — validator / scoring
- `ci-guardian` — CI workflow health
- `docs-maintainer` — keep docs in sync
- `agent-coordinator` — which specialist for what

Use them for review parallelism. Each agent reads its own file plus
`CLAUDE.md`.

## What NOT to do without explicit authorisation

`CLAUDE.md` §1 has the full list. The most-violated ones:

- Don't change `consensus_model.json` schema (§1.3)
- Don't modify `tools/consume_consensus.rb` (§1.4)
- Don't change geometry thresholds (§1.3)
- Don't run `ruff --fix .` over the whole repo (§1.7)
- Don't mix refactor + functional fix + perf in one PR (§1.9)
- Don't skip pytest / ruff / smoke gates on a Python-touching PR (§1.10)

When in doubt, ask before, not after.

## Decision-making escalation

`CLAUDE.md` §5: "When in doubt, choose the conservative path."

- Prefer **documenting** over changing code.
- Prefer **benchmarking** over optimising blindly.
- Prefer **adding a guardrail** over trusting future authors.
- Prefer **opening a draft PR** over silent merge.

If you're an autonomous agent and you're blocked by something that
needs a human, list the EXACT next commands needed to resume (see
`CLAUDE.md` §17 "End-of-cycle reporting format").

## Where to ask for help

- **Failure patterns** — `docs/learning/failure_patterns.md`. If
  your bug matches an existing FP-NNN, the repair is documented.
- **Specialist docs** — `docs/engineering/`, `docs/protocols/`,
  `docs/adr/`.
- **Live debugging** — `tools/inspect_walls_report.rb` via the SU
  autorun plugin; `tools/dump_skp_groups.{py,rb}` for non-disruptive
  geometry dumps.

## See also

- [`CLAUDE.md`](CLAUDE.md) — the constitution
- [`OVERVIEW.md`](OVERVIEW.md) — full architecture + cross-machine setup
- [`AGENTS.md`](AGENTS.md) — agent contract surface
- [`docs/pipeline_overview.md`](docs/pipeline_overview.md) — visual pipeline diagram
- [`docs/engineering/spec_driven_development.md`](docs/engineering/spec_driven_development.md) — SDD framework
- [`docs/engineering/harness_engineering.md`](docs/engineering/harness_engineering.md) — harness internals
