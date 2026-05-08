# Stage 1.6 Cycle 5 — Port `gate_g2` (inspector v2 consumer) from orphan branch

> **Self-contained prompt for the implementing session.** Read this end-to-end
> before doing anything. The investigation is in
> `docs/diagnostics/2026-05-08_stage_1_6_investigation.md`; this file is the
> action plan.

## Branch name

`feature/smoke-gate-g2-inspector-v2`

(Off `develop`. **Do NOT use** the orphan name
`feature/smoke-promotes-inspector-v2-gate`; that name still belongs to the
orphan and you'll delete it after merge.)

## Source of the code

`git show origin/feature/smoke-promotes-inspector-v2-gate:scripts/smoke/smoke_skp_export.py`
and
`git show origin/feature/smoke-promotes-inspector-v2-gate:tests/test_smoke_gate_g2_inspector.py`

The orphan tip is `2417a20`. **You are NOT merging the orphan**; you are
copying the relevant code into a fresh branch on top of today's `develop`
and adapting it to the post-`gate_f0` pipeline shape.

## File scope

**Modify (3 files):**

1. `scripts/smoke/smoke_skp_export.py` — add `gate_g2()` function (+88 LOC),
   add `--inspect-strict` flag in `_build_parser()`, append `gate_g2` to
   the pipeline tuple after `gate_g`.
2. `docs/validation/sketchup_smoke_workflow.md` — extend gate table with
   row G2; document `--inspect-strict`.

**Create (1 file):**

3. `tests/test_smoke_gate_g2_inspector.py` — port from `2417a20` with one
   trivial relaxation (see step 4).

**Do NOT touch:**

- `tools/inspect_walls_report.rb` (CLAUDE.md §1.4 — Ruby exporter)
- `tools/autorun_inspector_plugin.rb` (CLAUDE.md §1.4)
- `tools/consume_consensus.rb` (CLAUDE.md §1.4)
- `tools/su_boot.rb` (CLAUDE.md §1.4)
- `tools/skp_from_consensus.py`
- `tools/skp_inspection_report.py` (already perfect on `develop`)
- Any consensus / schema / threshold / baseline file
- The orphan branch itself (read-only via `git show`)

## Step-by-step plan

### 1. Branch + read

```bash
cd /e/Claude/sketchup-mcp
git fetch origin
git switch develop
git pull --ff-only
git switch -c feature/smoke-gate-g2-inspector-v2

# Read the orphan source for reference
git show origin/feature/smoke-promotes-inspector-v2-gate:scripts/smoke/smoke_skp_export.py > /tmp/orphan_smoke.py
git show origin/feature/smoke-promotes-inspector-v2-gate:tests/test_smoke_gate_g2_inspector.py > /tmp/orphan_tests.py
```

Open `/tmp/orphan_smoke.py` and locate the `gate_g2()` block (added at
line ~409 in the orphan, between gate_g and gate_h).

### 2. Add `gate_g2()` to `scripts/smoke/smoke_skp_export.py`

Insert the function **after `gate_g()`, before `gate_h()`** in today's
`develop` version. The function body is **byte-identical** to the orphan's
copy; no adaptation needed. It depends only on:

- `tools.skp_inspection_report.InspectionReport` (already on `develop`)
- `report.cache_hit`, `report.out_dir` (existing `SmokeReport` fields)
- `args.skip_skp`, `args.force_skp`, `args.inspect_strict` (the third is new)

### 3. Add the flag and update the pipeline tuple

In `_build_parser()`, add:

```python
ap.add_argument("--inspect-strict", action="store_true",
                help="gate G2 fails the smoke run when "
                     "inspect_report.json has structural blockers "
                     "(default: non-blocking; report-only)")
```

In `main()`, change the pipeline tuple from:

```python
pipeline = (gate_a, gate_b, gate_c, gate_d, gate_e,
            gate_f0, gate_f, gate_g)
```

to:

```python
pipeline = (gate_a, gate_b, gate_c, gate_d, gate_e,
            gate_f0, gate_f, gate_g, gate_g2)
```

Update the module docstring (top of file) `Gate sequence` block to include
G2 between G and H.

### 4. Port the tests with one relaxation

Copy `tests/test_smoke_gate_g2_inspector.py` from the orphan verbatim,
**except** for `test_pipeline_includes_gate_g2`. The orphan asserts:

```python
assert "gate_g, gate_g2)" in src or "gate_g2," in src
```

The new pipeline tuple breaks across lines and ends with `gate_g2)` on its
own visual line. Change the assertion to:

```python
assert "gate_g2" in src
assert "pipeline = (" in src
# Sanity: gate_g2 appears in the pipeline definition, not just imports
import re
m = re.search(r"pipeline\s*=\s*\((.*?)\)", src, re.DOTALL)
assert m is not None and "gate_g2" in m.group(1)
```

The other 10 tests should pass byte-equivalent.

### 5. Update `docs/validation/sketchup_smoke_workflow.md`

In the gate table (around line 22), add a row for G2 between G and H:

```markdown
| G2 | Inspector v2 (opt-in strict) | <1 s | Reads `inspect_report.json` from out_dir, parses via `tools.skp_inspection_report`. SKIP if report missing (until Cycle 6 wires the autorun plugin into gate F). PASS with `would-block` warning when blockers present in default mode. FAIL on blockers when `--inspect-strict` is passed. |
```

In the CLI flag table (around line 50), add:

```markdown
| `--inspect-strict` | off | Promote gate G2 from report-only to fail-on-blocker. |
```

Update the ASCII pipeline diagram if it lists gates explicitly.

### 6. Validate

```bash
# From repo root, with .venv activated
python -m pytest tests/test_smoke_gate_g2_inspector.py -v
# Expect: 11 PASS

python -m pytest -q
# Expect: 780 collected (769 + 11), pre-existing 17 raster failures
# unchanged from CLAUDE.md §10. NO new failures.

ruff check scripts/smoke/smoke_skp_export.py tests/test_smoke_gate_g2_inspector.py
# Expect: clean

# E2E sanity (cheap gates only, no SU spawn)
python scripts/smoke/smoke_skp_export.py \
    --consensus runs/vector/consensus_model.json \
    --skip-skp
# Expect: smoke verdict PASS, G2 reports SKIP "--skip-skp"

# E2E with a stub inspect_report.json to exercise the parse path
mkdir -p /tmp/g2_test
cat > /tmp/g2_test/inspect_report.json <<'EOF'
{"schema_version":"1.0","meta":{"skp_sha256":"a","skp_size_bytes":1,
"sketchup_version":"26.0"},"structural":{"default_faces_count":0,
"materials_count":1,"wall_overlaps_count":0,"components_count":0,
"groups_by_layer":{}},"bounds_check":null,"materials":[],"layers":[],
"wall_overlaps_top20":[],"default_faces_count":0,"groups":[]}
EOF
# (G2 only fires when cache_hit is False or --force-skp; --skip-skp
# alone makes it SKIP. To smoke-test the PASS path, set up a fixture
# unit test rather than wrestle the harness E2E here.)
```

### 7. Commit + PR

Single commit, message format:

```
feat(smoke): gate G2 — port inspector v2 consumer from orphan branch (Stage 1.6 Cycle 5)

Salvages 2417a20 from the orphan branch
feature/smoke-promotes-inspector-v2-gate (which was authored before
gate_f0 / Slice 3 / cockpit / ground-truth waves landed). Wires the
inspector v2 reader (tools.skp_inspection_report, already on develop
since PR #49) into the smoke harness as gate G2, sitting after the
.skp file-existence check (G) and before the reports gate (H).

Behaviour contract (unchanged from 2417a20):
  - SKIP on --skip-skp
  - SKIP on cache hit unless --force-skp
  - SKIP when no inspect_report.json next to the SKP
    (Cycle 6 will wire the autorun plugin into gate F so this
    SKIP path becomes the exception rather than the rule)
  - PASS in default mode even with structural blockers (logs
    "would-block: ..." for visibility, never regresses smoke)
  - PASS in default mode on legacy v0 reports (back-compat)
  - FAIL in --inspect-strict mode on any structural blocker
  - FAIL on unparseable JSON (always, both modes)

Pipeline tuple is now:
  (gate_a, gate_b, gate_c, gate_d, gate_e,
   gate_f0, gate_f, gate_g, gate_g2)

Investigation + rationale:
  docs/diagnostics/2026-05-08_stage_1_6_investigation.md

CLAUDE.md hard rules:
  - #1.4 (Ruby exporter): UNTOUCHED
  - #2 (consensus_model.json schema): UNTOUCHED
  - #3 (geometry thresholds): UNTOUCHED
  - #1.10 (validation): pytest + ruff run, see body

Co-Authored-By: Claude <noreply@anthropic.com>
```

PR command (use the absolute `gh.exe` path per LL-012):

```powershell
& "C:\Program Files\GitHub CLI\gh.exe" pr create `
    --repo GFCDOTA/sketchup-mcp `
    --base develop `
    --title "feat(smoke): gate G2 — port inspector v2 consumer (Stage 1.6 Cycle 5)" `
    --body-file - <<'EOF'

## Summary

- Ports `gate_g2()` (inspector v2 structural check) from the orphan
  branch `feature/smoke-promotes-inspector-v2-gate` (`2417a20`) into
  today's smoke harness, on top of the post-`gate_f0` pipeline.
- Default mode is **report-only** (PASS with would-block warning);
  opt-in `--inspect-strict` flag promotes blockers to FAIL.
- Always SKIPs on a clean `develop` until **Stage 1.6 Cycle 6** wires
  the autorun inspector plugin into gate F. This PR is the consumer
  half only; producer half is a separate PR.

## What changed

| Path | Why |
|---|---|
| `scripts/smoke/smoke_skp_export.py` | New `gate_g2()` (+88 LOC); `--inspect-strict` flag; pipeline tuple appends `gate_g2`; module docstring updated |
| `tests/test_smoke_gate_g2_inspector.py` | NEW (+208 LOC). 11 tests: 3 SKIP paths, 4 default-mode PASS variants, 2 FAIL paths, 2 sanity (pipeline + parser) |
| `docs/validation/sketchup_smoke_workflow.md` | Gate table extended with G2 row; `--inspect-strict` documented |

## What did NOT change

- **Schema** — `consensus_model.json` / `inspect_report.json` (schema 1.0)
  / `pre_skp_review_report.json` (schema `pre_skp_review_v1`) all untouched.
- **Geometry thresholds** — none touched.
- **Ruby/SketchUp exporter** — `tools/consume_consensus.rb`,
  `tools/inspect_walls_report.rb`, autorun plugins, `tools/su_boot.rb`
  all UNTOUCHED.
- **Pipeline invariants** (CLAUDE.md §2): no inference, no fallback,
  no GT leakage; gate G2 is purely observational.
- **`gate_f0`** (Slice 3) — left alone; G2 sits after G, well downstream.
- **No baseline / no fidelity / no schema gate** changes.

## Validation

- `python -m pytest tests/test_smoke_gate_g2_inspector.py -v` → 11/11 PASS
- `python -m pytest -q` → 780 collected (769 + 11), pre-existing 17
  raster failures from CLAUDE.md §10 unchanged, **0 new failures**
- `ruff check scripts/smoke/smoke_skp_export.py tests/test_smoke_gate_g2_inspector.py` clean
- E2E smoke `--skip-skp` on canonical consensus → verdict PASS, G2 SKIP `"--skip-skp"`
- E2E smoke without `--skip-skp` (cache hit on default consensus) →
  verdict PASS, G2 SKIP "deferred — no inspect_report.json"

## Risks

| Risk | Mitigation |
|---|---|
| Gate always SKIPs until Cycle 6 wires the producer | Documented in commit msg + investigation doc; G2 is opt-in to strictness via `--inspect-strict`, never breaks existing flows |
| `schema_version` hardcoded to `"1.0"` | Acceptable: the parser already enforces this; future schema bumps must coordinate via the parser, not the harness |
| Pipeline ordering with `gate_f0` | `gate_f0` short-circuits to `gate_h` on its own FAIL (in `block` mode); G2 then SKIPs cleanly because no SKP was produced |

## Rollback

```bash
git revert <merge-sha>
git push origin develop
```

The revert removes the new file and reverts `smoke_skp_export.py` /
`sketchup_smoke_workflow.md`. No data, no schema, no Ruby is touched
so nothing else needs to be undone.

## Next steps

- **Stage 1.6 Cycle 6 (separate PR)** — wire
  `tools/autorun_inspector_plugin.rb` into `gate_f` so that every
  successful F leaves an `inspect_report.json` next to the `.skp`.
  After that, gate G2 stops always-skipping and starts giving real
  verdicts on every smoke run.
- **Stage 1.6 Cycle 7 (later)** — promote `--inspect-strict` to
  default in CI after Cycle 6 has been green for several days on
  the canonical consensus.
- **Delete the orphan branch** (`feature/smoke-promotes-inspector-v2-gate`)
  after this PR merges. Per CLAUDE.md §0, feature branches are deleted
  after their PR lands; this PR is the de-facto closure for the orphan.

## Origin

- Orphan branch: `feature/smoke-promotes-inspector-v2-gate` (tip `2417a20`,
  authored 2026-05-07, never opened as PR)
- Investigation: `docs/diagnostics/2026-05-08_stage_1_6_investigation.md`
- Inspector v2 schema PR (predecessor): #49 (merged `4cb968f`)

EOF
```

## Stop conditions

Halt and report **without** opening the PR if:

- Tests fail and the failure is not the trivial `test_pipeline_includes_gate_g2`
  substring relaxation. Read the failure, diagnose, and only proceed when 11/11
  pass and the full sweep is at parity with `develop`'s baseline.
- `tools/skp_inspection_report.py` has changed in a way that breaks
  the orphan's test fixtures. Read the parser's `from_dict()` and adjust
  the fixtures to today's contract.
- The orphan branch has been silently merged or deleted on origin
  in the meantime → consult `git log origin/develop --oneline | grep -i
  inspector` to find the actual landing commit, and switch to a docs-only
  follow-up that documents the closure.

Halt and ask **only** if:

- A real CLAUDE.md §1 hard-rule conflict surfaces that the investigation
  did not anticipate. Document it in `.ai_bridge/QUESTIONS_FOR_NEXT_AGENT.md`
  and stop.

For everything else — read the code, run the tool, write the test, ship the PR.
