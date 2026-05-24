# Repo Health Report

> **Status:** Generated (do not edit). Produced by `tools/repo_health_gate.py`.
> **Generated:** 2026-05-24 (post Wave 1 cleanup)
> **Branch:** chore/repo-cleanup-w1-fresh (PR target: develop)
> **Cycle:** Repo Health Gate Wave 1 — root prototypes

## Summary

| Severity | Before Wave 1 | After Wave 1 | Delta |
|---|---|---|---|
| error   |  0 |  0 | ±0 |
| warning | 61 | 56 | **−5** |
| info    |  0 |  0 | ±0 |

W001 specifically (loose script in repo root): **16 → 10** — a
6-warning drop. 3 from deletions of unreferenced orphans + 3 from
moves of test-referenced scripts to `tools/legacy/`.

## What this PR did

### Deleted (3 unreferenced orphans)

| File | Last commit | Live references | Action |
|---|---|---|---|
| `proto_runner.py` | `2135f55` (2026-04-28) | 0 | deleted in `f3882d0` |
| `proto_skel.py`   | `2135f55` (2026-04-28) | 0 | deleted in `f3882d0` |
| `proto_v2.py`     | `2135f55` (2026-04-28) | 0 | deleted in `f3882d0` |

`rg` proof: each file's grep hits resolve only to audit reports and
archived docs (`docs/_archive/2026-04-f1-cycle/ANALYSIS.md`,
`reports/repo_hygiene_report.md`, `docs/ops/repo_hygiene_audit_2026-05-10.md`).
Zero imports, zero CLI invocations, zero CI references, zero test
references.

### Moved (3 test-referenced scripts)

| From | To | Test caller | Migration |
|---|---|---|---|
| `proto_colored.py`     | `tools/legacy/proto_colored.py`     | `tests/test_proto_cli.py::test_proto_colored_help_runs` | atomic with test update in `bd900c4` |
| `proto_red.py`         | `tools/legacy/proto_red.py`         | `tests/test_proto_cli.py::test_proto_red_help_runs` + `test_proto_red_missing_input_exits_nonzero` | atomic with test update in `bd900c4` |
| `render_sidebyside.py` | `tools/legacy/render_sidebyside.py` | `tests/test_proto_cli.py::test_render_sidebyside_help_runs` + `test_render_sidebyside_crop_validator_rejects_bad_spec` | atomic with test update in `bd900c4` |

`tests/test_proto_cli.py` got a new `_script_path()` helper that
points the 5 subprocess invocations at `tools/legacy/<script>`.
`usage: proto_red.py` argparse output is unchanged because Python
uses `sys.argv[0]`'s basename.

### New scaffolding

- `tools/legacy/README.md` — Status: Active. Documents what lives
  here, the live-caller table, and the "when to delete an entry"
  rule that honors `docs/REPO_HYGIENE.md` §3.

## Intentionally deferred (still in the report as W001 warnings)

### 5 deprecation wrappers — kept at repo root by deliberate policy

| File | Reason kept |
|---|---|
| `render_debug.py`          | docstring begins `"""DEPRECATED — moved to renderers.debug."""`. Carries `warnings.warn(DeprecationWarning)` + `from renderers.debug import *` + `runpy.run_module("renderers.debug", ...)` for `python render_debug.py ...` callers. Policy in `docs/architecture/target_repo_architecture.md` step 5. |
| `render_native.py`         | same pattern — wraps `renderers.native`. |
| `render_proto_overlays.py` | same pattern — wraps `renderers.proto_overlays`. |
| `render_semantic.py`       | same pattern — wraps `renderers.semantic`. |
| `render_with_openings.py`  | same pattern — wraps `renderers.with_openings`. |

**Recommended Wave 2 PR:** teach `tools/repo_health_gate.py` W001
to exempt files whose docstring begins with the literal `DEPRECATED`.
That gate-feature change auto-resolves these 5 warnings without
moving the files (which would break `python render_*.py` callers
that have not yet migrated).

### 5 other root scripts — out of scope for Wave 1 (different category)

| File | Notes |
|---|---|
| `analyze_overpoly.py`  | over-polygonisation diagnostic — used during the F1 cycle; reference scan deferred. |
| `crop_legend.py`       | one-shot PDF legend crop helper. |
| `make_test_pdf.py`     | synthetic PDF generator. |
| `peek_pdf.py`          | quick PDF inspection helper. |
| `preprocess_walls.py`  | wall-mask preprocessing one-off. |

These belong to a "diagnostic utilities" category distinct from
`proto_*` / `render_*`. **Wave 3 PR** scope.

## Other warnings (unchanged by this PR)

- 46 W002 — `docs/**/*.md` without `Status:` header. Policy
  (`docs/REPO_HYGIENE.md` §2) is "do not bulk rewrite"; these get
  backfilled when each file is next touched.

## Validation evidence

```
pytest tests/test_proto_cli.py -q
  -> 5 passed in 1.15s

pytest -q
  -> 1248 passed, 17 failed
     (17 failures are the pre-existing CLAUDE.md §10 baseline in
      tests/test_text_filter.py — unrelated to this PR; documented
      as tech debt from the `len(strokes) > 200` gate in
      `classify/service.py:160`)

ruff check tools/repo_health_gate.py scripts/project_state_check.py \
           tests/test_proto_cli.py tests/test_repo_health_gate.py \
           tools/legacy/
  -> All checks passed

python tools/repo_health_gate.py --mode audit
  -> ERROR 0, WARNING 56, INFO 0  (was 0/61/0 pre-cleanup)

python tools/repo_health_gate.py --mode check --base origin/develop
  -> exit 0 once the docs/PROJECT_STATE.md §9 entry was added.
     Without that, the gate's E006 (project-state-stale on structural
     diff) correctly fired — gate working as designed.

python scripts/project_state_check.py
  -> PASS 30, FAIL 0, WARN 9  (unchanged from pre-cleanup; the 9
     soft warnings track feature/window-aperture-semantics)
```

## Per-cycle commits

| SHA | Title | Effect |
|---|---|---|
| `f3882d0` | chore(repo): delete 3 unreferenced root prototype scripts | W001 16 → 13 |
| `bd900c4` | chore(repo): move 3 root prototypes to tools/legacy/ + update tests | W001 13 → 10 |
| _this commit_ | chore(repo): refresh repo-health report + PROJECT_STATE §9 update log | report + state-doc sync |

## How to act next

1. **Wave 2 (separate PR):** add docstring-`DEPRECATED` exemption to
   W001 detector. Eliminates 5 warnings without moves.
2. **Wave 3 (separate PR):** classify the 5 diagnostic-utility root
   scripts (`analyze_overpoly`, `crop_legend`, `make_test_pdf`,
   `peek_pdf`, `preprocess_walls`).
3. **W002 backfill:** opportunistic — every PR that touches a
   `docs/*.md` adds a `Status:` header in the same commit (per
   `docs/REPO_HYGIENE.md` §2 — no bulk rewrite).

## References

- [`../../docs/REPO_HYGIENE.md`](../../docs/REPO_HYGIENE.md) — policy
- [`../../docs/GATES.md`](../../docs/GATES.md) — gate catalogue
- [`../../tools/repo_health_gate.py`](../../tools/repo_health_gate.py) — detector + safe-fix catalogue
- [`../../tools/legacy/README.md`](../../tools/legacy/README.md) — new scaffolding
