# Stage 1.6 — Orphan inspector branch investigation (2026-05-08)

> **Scope:** read-only audit of `feature/smoke-promotes-inspector-v2-gate`
> (last commit `2417a20`, never opened as PR), classification of what
> remains relevant after PR #84 (`gate_f0`) shipped, and a recommended
> re-launch path for the Stage 1.6 SketchUp-side wiring.
>
> **Authority:** Felipe authorized advancing on RED items per
> `.ai_bridge/TODO_NEXT.md` P3 ("Stage 1.6 / orphan inspector branch").
> This doc is the closure record + planning input. **No SU runtime is
> exercised here.** The implementing PR is a separate fresh-session
> task (see `.ai_bridge/pr_bodies/PR_BODY_stage_1_6_followup.md`).

---

## 1. Status quo on `develop` (@`1f200c5`)

### What gates exist today

`scripts/smoke/smoke_skp_export.py` runs the following pipeline (per
the `pipeline = (...)` tuple at line 774):

```
A → B → C → D → E → F0 → F → G → H
```

| Gate | What it does | Cost |
|---|---|---|
| A | Preparation (resolve sketchup.exe, mkdir out_dir) | <1 s |
| B | Acquire consensus (load JSON, hash) | <1 s |
| C | JSON structural sanity (walls/rooms/openings shape) | <1 s |
| D | Preview PNG (`tools.render_axon`) | 2–4 s |
| E | Hash + cache (sha256 of consensus + skp source) | <1 s |
| **F0** | **Pre-SKP review (PR #84, ADR-001 §2.8)** — reads `fidelity_report.json` + optional `review_overrides.json`, emits `pre_skp_review_report.json`, gated by `--review-mode={off,warn,block}` | <1 s |
| F | Export `.skp` via `tools.skp_from_consensus` (skipped on `--skip-skp` or cache hit) | 5–90 s |
| G | Validate `.skp` (file exists, size > 1 KiB) | <1 s |
| H | Reports (`sketchup_smoke_report.{json,md}`, refresh cache) | <1 s |

### What `inspect_walls_report.rb` does (already on `develop`, schema 1.0)

`tools/inspect_walls_report.rb` runs **inside SketchUp** and emits
`inspect_report.json` with schema_version `"1.0"` (Stage 1.6 inspector
v2, shipped via PR #49 / merge `4cb968f`). Fields it produces:

- `meta.skp_sha256` + `meta.skp_size_bytes`
- `meta.consensus_path` + `meta.consensus_sha256` (when env set on launch)
- `structural.{default_faces_count, materials_count, wall_overlaps_count, components_count, groups_by_layer}`
- `bounds_check.{skp_bbox_in, consensus_bbox_pt, scaled_consensus_bbox_in, delta_in, within_tol_in, delta_within_tol}`

`tools/skp_inspection_report.py` (also on `develop`) is the Python
reader. It exposes `InspectionReport.is_clean()` and
`InspectionReport.strict_blockers()` — exactly the verdict primitives
the orphan branch's gate G2 wanted to consume.

### What is **missing** on `develop`

- **No smoke-harness consumer** of `inspect_report.json`. Gate F exports
  the SKP, gate G validates file existence/size, gate H writes reports.
  None of them parse the inspector output.
- **No autorun-into-smoke wiring**. `tools/autorun_inspector_plugin.rb`
  exists and works (45 LOC, fires on SU startup, schedules a 5 s
  timer to run the inspector against an active model), but it is
  driven by an external `autorun_inspector_control.txt` file. The
  smoke harness does **not** stage that control file or invoke the
  plugin during gate F.

### Why Stage 1.6 was held

`.ai_bridge/TODO_NEXT.md` line 167–172 documents the hold:

> **Color:** RED — explicitly on hold per earlier session
> **Branches affected:** `feature/smoke-promotes-inspector-v2-gate` (orphan, never PR'd).
> **To unblock:** Felipe needs to lift Stage 1.6 hold.

Earlier handoff (`.ai_bridge/HANDOFF.md` line 681 onward) reveals
the historical context: PR #49 (inspector v2 schema) and PRs #50/#51
(autonomy rules + hygiene) landed; PR #52 (gate G2) was prepared but
never opened, then the session pivoted to ground-truth + cockpit
work. The branch was left dangling with `2417a20` as its tip.

---

## 2. What's on the orphan branch

### Branch tip

```
2417a20  feat(smoke): gate G2 — inspector v2 structural check (opt-in strict)
fad28d9  Merge pull request #51 from GFCDOTA/chore/repo-hygiene-2026-05-06
```

`2417a20` is a **single commit** on top of `develop @ fad28d9`
(2026-05-06). The branch is roughly 30 merges behind today's
`develop @ 1f200c5` because it predates the entire ground-truth +
cockpit + ADR-001 wave.

### File-by-file diff

`git show 2417a20 --stat` (the only commit on the branch beyond
`fad28d9`):

| File | Lines added | Why |
|---|---|---|
| `scripts/smoke/smoke_skp_export.py` | +88 | Inserts `gate_g2()` between G and G; adds `--inspect-strict` flag; appends `gate_g2` to the pipeline tuple |
| `tests/test_smoke_gate_g2_inspector.py` | +208 (new file) | 8 G2 behaviour cases + 1 unparseable + 2 pipeline-integration tests |

**Net:** 2 files, +295 LOC, **0 changes to Ruby / schema / thresholds /
consensus**. The commit message correctly attests "CLAUDE.md hard
rules: #4 / #2 / #3 UNTOUCHED."

### Behavioural contract of the proposed gate G2

Reading the `2417a20` source verbatim, gate G2 does the following:

1. **SKIP** when `--skip-skp` is passed (no SKP to inspect).
2. **SKIP** when smoke cache hit AND not `--force-skp` (the inspector
   ran on the previous SKP; nothing has changed).
3. **SKIP** when `inspect_report.json` is **not** present in the
   `out_dir`. The reason logged is *"no inspect_report.json in
   out_dir — autorun inspector plugin did not fire for this smoke
   run (deferred)"*. **This is the always-skip path on a clean
   `develop`** because no upstream gate stages a control file for
   the autorun plugin.
4. Otherwise, parse the report via
   `tools.skp_inspection_report.InspectionReport.from_path()`:
   - `not blockers` → **PASS** with summary message.
   - `blockers AND --inspect-strict` → **FAIL** with first 5 blockers.
   - `blockers AND default mode` → **PASS** with `would-block: ...`
     warning (informational, never regresses the smoke verdict).
5. Unparseable JSON → **FAIL** in both modes (always).

The contract is conservative: G2 is a **report-only** gate by
default, opt-in to strict via the new flag.

### Pipeline integration

The orphan changes the pipeline tuple from:

```python
pipeline = (gate_a, gate_b, gate_c, gate_d, gate_e, gate_f, gate_g)
```

to:

```python
pipeline = (gate_a, gate_b, gate_c, gate_d, gate_e, gate_f, gate_g, gate_g2)
```

**This was authored against `develop @ fad28d9` — before PR #84
(`gate_f0`) was merged.** The current pipeline order on `develop` is
`(A, B, C, D, E, F0, F, G)`. A clean re-launch must respect that and
position G2 **after G, before H**, yielding:

```python
pipeline = (gate_a, gate_b, gate_c, gate_d, gate_e,
            gate_f0, gate_f, gate_g, gate_g2)
```

### Test plan on the orphan

`tests/test_smoke_gate_g2_inspector.py` covers:

1. `test_g2_skip_when_skip_skp_flag_set` — SKIP on `--skip-skp`
2. `test_g2_skip_when_cache_hit_and_not_forced` — SKIP on cache hit
3. `test_g2_skip_when_no_inspect_report_present` — SKIP, "deferred"
4. `test_g2_pass_on_clean_v2_report_default_mode` — PASS w/ summary
5. `test_g2_pass_with_blockers_in_default_mode` — PASS w/ would-block
6. `test_g2_fail_with_blockers_in_strict_mode` — FAIL on strict
7. `test_g2_fail_on_unparseable_report` — FAIL always
8. `test_g2_fail_strict_on_v0_report_due_to_schema` — schema_version blocker
9. `test_g2_pass_on_v0_report_default_mode` — back-compat
10. `test_pipeline_includes_gate_g2` — sanity on tuple wiring
11. `test_inspect_strict_arg_in_parser` — flag registered

The 11 tests are well-scoped: they fixture-build the JSON (no SU,
no live SKP), and the pipeline-integration assertion just greps the
module source. **All 11 are salvageable as-is** with two trivial
adjustments:

- `test_pipeline_includes_gate_g2` asserts `"gate_g, gate_g2)" in src`.
  After re-launch on top of `develop`, the line breaks differently
  due to F0 being added; the assertion needs to become substring-only
  (e.g., `"gate_g2" in src and "pipeline = (" in src`).
- The `_make_args` helper builds an `argparse.Namespace` with only
  3 fields. Today's `gate_g2` would still only read those three; no
  new fields need to be added to the helper.

---

## 3. What changed on `develop` since the branch was created

Between `fad28d9` (orphan base) and `1f200c5` (today's develop tip):

- **Cycle 7** — Ground truth v1 schema + Fidelity Engine v1 (advisory)
  → promoted to **HARD merge gate** in Cycle 8b.
- **Cycle 8b** — Concave-hull room clip (FP-012 fix); SUITE 01 went
  from 69.91 m² to 26.75 m².
- **Cycle 11–12e** — Validation Cockpit (read-only Streamlit slice).
- **Cycle 12g** — Thumbnail on-demand (PR #82).
- **ADR-001 / Slices 1–3** — `cockpit/overrides.py` (Slice 2),
  `tools/apply_overrides.py` (Slice 3), and `gate_f0` in the smoke
  harness (Slice 3, PR #84).
- **Operational** — `.ai_bridge/` scaffolding, autonomy rules
  (CLAUDE.md §14–17), repo hygiene cycles, RuboCop CI.

### Effect of `gate_f0` (PR #84) on Stage 1.6's scope

`gate_f0` is a **pre-SKP review**: it reads `fidelity_report.json`
(extraction-side metric) plus optional `review_overrides.json` (human
gate), and writes `pre_skp_review_report.json` with a verdict. It
runs **before** F (the export). It blocks the SKP from being created
when fidelity is below threshold or a human flagged a block override.

**Gate G2 is a post-SKP structural check**: after F has produced
the `.skp` and G has confirmed the file exists, G2 reads the
**inspector's** report (a different artifact, produced by Ruby
running inside SU) and verifies the structural shape of the SKP
(no default-material faces, no overlapping walls, no rogue
components, bounding box matches consensus).

**They are complementary, not redundant.** F0 catches "the
extraction looks bad, don't bother exporting"; G2 catches "the
exporter ran but produced a malformed SKP". Both can fire on the
same run; they exercise different artifacts and different
failure modes. **`gate_f0` does not obsolete the orphan branch.**

---

## 4. Original Stage 1.6 goal (articulated)

From the orphan commit message + handoff entries:

> **Stage 1.6 = "the SKP is structurally sound, not just present
> as a file"**. Schema 1.0 of the inspector report (PR #49) +
> Python parser (PR #49) + smoke-harness consumer (this orphan,
> Cycle 5) + autorun-into-smoke wiring (Cycle 6, never started).
>
> Goal: every smoke run that produces a `.skp` must also produce
> an `inspect_report.json` next to it; the harness reads that
> report, surfaces any structural blocker, and (with
> `--inspect-strict`) fails the run when the SKP would be
> unsuitable for downstream consumption.

The orphan branch implements **Cycle 5 only** (the consumer). It
**does not** wire the autorun plugin into gate F; it explicitly
defers that to a "future PR (Stage 1.6 Cycle 6)" per the commit
body. On a clean `develop`, the gate would always SKIP with
`"no inspect_report.json in out_dir ... (deferred)"`.

---

## 5. Recommended re-launch approach

### Decision: **Cherry-pick the orphan's intent, fresh-author the code on top of today's `develop`**.

**Why not merge the orphan branch as-is:**
- 30+ merges of drift; rebase would have many no-op conflicts on
  the unrelated cockpit / ADR-001 work.
- The pipeline tuple position needs adjustment for `gate_f0`.
- The substring assertion in `test_pipeline_includes_gate_g2`
  needs updating.
- It's cleaner to open one focused PR than to drag a stale branch.

**Why not "supersede with `gate_f0`":**
- F0 is extraction-side; G2 is SKP-side. They cover disjoint
  failure surfaces (see §3 above).

**Why not "do Cycle 5 + Cycle 6 in one PR":**
- Cycle 5 (the consumer) is pure-Python, fixture-tested, no SU
  spawn — small, safe, mergeable in isolation.
- Cycle 6 (the autorun-into-smoke wiring) requires modifying
  `tools/autorun_inspector_plugin.rb` (CLAUDE.md §1.4 — Ruby
  exporter) and changing `gate_f` to stage a control file. It
  involves SU runtime, env var plumbing (`INSPECT_REPORT`,
  `CONSENSUS_JSON_FOR_INSPECTION`, `INSPECT_QUIT`), and a real
  smoke E2E run. **That belongs in its own PR with a dedicated
  validation pass.**

**Recommended sequence:**

1. **PR A — Cycle 5 (this is the follow-up brief)**: salvage the
   `gate_g2` code + `test_smoke_gate_g2_inspector.py` from
   `2417a20`, port to today's `develop`, wire after G in the
   pipeline tuple, ship as a docs+test+harness PR. **No SU
   runtime exercised**; gate always SKIPs in the wild today.

2. **PR B — Cycle 6 (separate, future)**: wire the autorun
   inspector plugin into gate F so that every successful F leaves
   an `inspect_report.json` next to the `.skp`. Then gate G2
   stops always-skipping and starts giving real verdicts.

3. **PR C — promote `--inspect-strict` to default in CI** (only
   after PR B has run green for several days on the canonical
   consensus).

---

## 6. Risks

### SU runtime risk

PR A (Cycle 5) **does not touch the SU runtime** — gate G2 only
reads a JSON file. **PR B (Cycle 6) does**; it wires
`autorun_inspector_plugin.rb` into the same SU session as `gate_f`.
That involves:

- Writing `autorun_inspector_control.txt` next to the plugin
  (with `INSPECT_SKP`, `INSPECT_REPORT`, and the script path).
- Setting `ENV['INSPECT_QUIT'] = '1'` so SU exits cleanly after
  the inspector runs.
- Risk of timing collisions: the autorun plugin uses
  `UI.start_timer(5.0, false)` to defer until the model is ready.
  The export script also uses a timer; both must complete before
  SU is told to quit.
- Risk of double-running: if the user re-runs gate F on a cache
  hit, the control file still exists; the plugin would fire on
  the **previous** SKP. Solution: stamp the control file with
  the run UTC timestamp; the plugin verifies before reading.

### `schema_version` coupling

Gate G2 hardcodes `"1.0"` as the expected schema (via
`InspectionReport.is_v2()`). Any future inspector schema bump
must:

- Either preserve back-compat (extend the parser to accept new
  versions while still passing v0/v1 through the legacy path).
- Or coordinate the bump with a smoke harness change in the
  same PR.

`tools/skp_inspection_report.py` already absorbs this via
`schema_version` field on the dataclass; the contract is
documented at line 47 of that file. No additional risk over what
`develop` already carries.

### Gate ordering interaction with `gate_f0`

F0 may FAIL in `block` mode. When that happens, the existing
short-circuit in `main()` jumps straight to gate H (no F, no G,
no G2). Gate G2 already SKIPs cleanly in that scenario because
`--skip-skp` is not set but no `inspect_report.json` was produced
(the F gate never ran). **No special handling needed**; G2's
"deferred" SKIP path covers it.

---

## 7. Acceptance criteria for the implementing PR (PR A)

- [ ] `scripts/smoke/smoke_skp_export.py`: new `gate_g2()` function
      ported from `2417a20` (88 lines); pipeline tuple updated to
      `(gate_a, gate_b, gate_c, gate_d, gate_e, gate_f0, gate_f, gate_g, gate_g2)`;
      new `--inspect-strict` flag in `_build_parser()`.
- [ ] `tests/test_smoke_gate_g2_inspector.py`: ported from `2417a20`
      with the substring assertion in `test_pipeline_includes_gate_g2`
      relaxed to handle the multi-line tuple. Other 10 tests
      should pass byte-equivalent.
- [ ] `docs/validation/sketchup_smoke_workflow.md`: gate table
      extended with G2 row; `--inspect-strict` documented.
- [ ] `pytest -q` passes the full sweep (current baseline 769
      collected; +11 = 780 collected after PR; pre-existing 17
      raster failures from CLAUDE.md §10 remain unchanged).
- [ ] `ruff check scripts/ tests/test_smoke_gate_g2_inspector.py`
      clean.
- [ ] **No** modifications to `tools/inspect_walls_report.rb`,
      `tools/autorun_inspector_plugin.rb`, `tools/consume_consensus.rb`,
      `tools/su_boot.rb`, `consensus_model.json` schema, geometry
      thresholds, or any baseline.
- [ ] Smoke verdict on the canonical consensus
      (`runs/vector/consensus_model.json`) **stays PASS**, with G2
      reporting SKIP `"deferred"` until Cycle 6 lands.

---

## 8. Status of the orphan branch

**Recommendation: KEEP until PR A merges, then DELETE.**

- **Now:** the branch is the only place `2417a20` lives outside the
  reflog. Reading it requires `git fetch` then `git show`. Keeping
  it costs nothing.
- **After PR A merges:** the salvaged code + tests will live on
  `develop` (with adjustments). The orphan adds zero unique value
  beyond historical attribution. Per CLAUDE.md §0 ("Delete a
  feature branch after its PR is merged"), it should be deleted
  from origin.
- **Attribution:** the commit message of PR A's port should reference
  `2417a20` so the original authorship is traceable in the git log.
  Recommended commit subject: `feat(smoke): gate G2 — port inspector
  consumer from orphan branch (Stage 1.6 Cycle 5)`.

---

## 9. References

- Orphan branch tip: `2417a20` on `feature/smoke-promotes-inspector-v2-gate`
- Inspector v2 schema PR (already merged): #49, merge `4cb968f`
- Pre-SKP review gate F0 (PR that may have changed scope): #84,
  merge `76739b3`
- Stage 1.6 hold record: `.ai_bridge/TODO_NEXT.md` lines 167–172
- Earlier handoff with Cycle 5/6 plan:
  `.ai_bridge/HANDOFF.md` lines 681–760
- Inspector parser (already on develop): `tools/skp_inspection_report.py`
- Autorun plugin (already on develop, not yet wired into smoke):
  `tools/autorun_inspector_plugin.rb`
- Smoke harness (current state): `scripts/smoke/smoke_skp_export.py`
- Smoke workflow doc: `docs/validation/sketchup_smoke_workflow.md`
- Follow-up PR brief:
  `.ai_bridge/pr_bodies/PR_BODY_stage_1_6_followup.md`

---

*This audit is read-only. No code, no Ruby, no schema, no thresholds
were touched. SketchUp was not exercised. The implementation belongs
in the follow-up PR per §5.*
