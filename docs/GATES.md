# GATES — canonical validation gates

> **Status:** Canonical
> **Type:** Catalogue of validation gates with commands and SLAs
> **Updated:** 2026-05-24
> **Companion docs:** [`PROJECT_STATE.md`](PROJECT_STATE.md) §6,
> [`HANDOFF.md`](HANDOFF.md) §2.3,
> [`PR_HYGIENE.md`](PR_HYGIENE.md) §1 + §3 (gate usage in startup/exit
> checklists), [`../CLAUDE.md`](../CLAUDE.md) §3 (SketchUp rule).

This file lists every validation gate that matters. Each gate has:

- a short **name** and a **role** (what it proves),
- a **cost** band (cheap, medium, expensive),
- the exact **command**,
- the expected **outcome**,
- the **artifacts** it consumes / emits,
- the failure **signature** (how you know it failed).

Gates are listed cheapest-first. **Run cheap gates before expensive
ones** ([`../CLAUDE.md`](../CLAUDE.md) §3).

---

## Tier 1 — cheap gates (< 10 s each)

### G-LINT — ruff lint
- **Role:** style + obvious bug detection across the Python surface.
- **Cost:** ~2 s.
- **Command:** `ruff check .`
- **Expected:** zero errors.
- **Failure signature:** `ruff` exits non-zero with a list of files +
  rule IDs.
- **Reset:** the only allowed `--fix` form is `ruff check --fix
  <single-path>`. NEVER `ruff --fix .` — banned by
  [`../CLAUDE.md`](../CLAUDE.md) §1 hard rule.

### G-UNIT — pytest unit suite
- **Role:** every unit test in `tests/`.
- **Cost:** ~25 s on a warm cache.
- **Command:** `pytest -q`
- **Expected:** the baseline pass / known-fail / skip counts documented
  in [`../CLAUDE.md`](../CLAUDE.md) §10 (raster baseline failures are
  pre-existing and known). For the vector pipeline the recent
  baseline is in [`../PROJECT_STATE.md`](PROJECT_STATE.md).
- **Failure signature:** `pytest` exits non-zero with NEW failures
  beyond the documented baseline. Investigate the new failures, never
  the known ones, unless explicitly tasked.

### G-PROJECT-STATE — project state hygiene gate
- **Role:** assert that every canonical doc / fixture / gate listed
  in this file and `PROJECT_STATE.md` still exists and is non-empty.
- **Cost:** < 2 s.
- **Command:** `python scripts/project_state_check.py`
- **Expected:** exit 0, "OK" summary. Missing items list which docs /
  fixtures are gone.
- **Failure signature:** exit 1 + list of missing items.
- **When to run:** at the start and end of every cycle. CI runs it
  on every PR via [`.github/workflows/repo_health.yml`](../.github/workflows/repo_health.yml).
- **Strict mode:** `--strict` promotes soft warnings to hard fails.
- **JSON output:** `--json` for machine consumption.

### G-REPO-HEALTH — repository hygiene gate
- **Role:** enforce [`REPO_HYGIENE.md`](REPO_HYGIENE.md) +
  [`../CLAUDE.md`](../CLAUDE.md) §15 mechanically. Three modes:
  - `audit` — read-only, always exits 0, writes
    `reports/current/repo_health_report.md`.
  - `check` — exits non-zero on ERROR-class findings (or any warning
    under `--strict`). With `--base REF`, only NEW violations vs
    the base count; pre-existing warnings are grandfathered.
  - `fix` — applies the conservative safe-fix list ONLY (move >30d
    reports to archive, append obvious patterns to `.gitignore`,
    delete untracked tmp files in the working tree). Never deletes
    tracked files, never rewrites .md content, never touches `.py` /
    `.rb`.
- **Cost:** < 3 s on the full repo.
- **Command (local audit):** `python tools/repo_health_gate.py --mode audit`
- **Command (PR gate):**
  `python tools/repo_health_gate.py --mode check --base origin/develop`
- **Detector catalogue:** see the script docstring. ERROR codes
  (`E001`–`E006`) gate CI; WARNING codes (`W001`–`W005`) surface as
  technical debt without gating; INFO codes (`I001`–`I002`) are
  observations.
- **Failure signature:** non-zero exit + `reports/current/repo_health_report.md`
  lists the offending paths + the suggested action per finding.
- **JSON output:** `--json` emits the full finding list for
  machine consumption.

### G-QUADRADO — quadrado canonical smoke gate
- **Role:** lock the wall-shell + window aperture canonical contract
  against the versioned fixture.
- **Cost:** < 5 s.
- **Command:** `pytest tests/test_quadrado_canonical_smoke.py -v`
- **Expected:** 14/14 pass.
- **Failure signature:** outer-ring vertex count != 4, missing window
  glass group, sliver / redundant-vertex regression.

### G-WALL-SHELL — wall shell canonicalisation gate
- **Role:** lock the wall footprint extension + canonicaliser
  contract.
- **Cost:** < 5 s.
- **Command:** `pytest tests/test_wall_shell_canonical.py -v`
- **Expected:** 15/15 pass + planta_74 idempotency check.
- **Failure signature:** notches at outer corners (`2*half × 2*half`
  L-shape), non-axis-aligned edges from axis-aligned input,
  `slivers_removed > 0` on planta_74.

### G-WINDOW-CONTRACT — window aperture contract gate
- **Role:** lock the `kind_v5 == "window"` routing to 3D post-extrude
  carve.
- **Cost:** < 5 s.
- **Command:** `pytest tests/test_window_aperture_contract.py -v`
- **Expected:** 15/15 pass.
- **Failure signature:** any window routed to the 2D full-height
  carve path; missing `WindowGlass_Group_*`; sill / lintel sub-groups
  at z = [0, 0.9] (door-like-void signature).

### G-PLAN-TRUTH — planta_74 truth gate
- **Role:** versioned baseline regression test
  (33 walls / 11 rooms / 11 openings / 8 soft_barriers).
- **Cost:** < 3 s.
- **Command:** `pytest tests/test_planta_74_truth_gate.py -v`
- **Expected:** all pass; baseline locked.
- **Failure signature:** numbers shift in the consensus output.

### G-COHERENCE — coherence audit (Stage 1)
- **Role:** Stage 1 uncertainty contract on each opening
  (`confidence` / `decision` / `hypotheses` / `evidence`).
- **Cost:** < 2 s.
- **Command:**
  `python -m tools.coherence_audit runs/vector/consensus_classified.json --out-dir runs/vector`
- **Expected:** emits `coherence_report.json` schema 1.0 + `questions.json`.
- **Strict mode:** `--strict` flips to hard exit-non-zero.
- **Failure signature in strict mode:** unresolved hypotheses for any
  opening.

### G-MICRO — micro truth gate
- **Role:** per-room manual ground truth on the 4 labelled rooms
  (SALA DE ESTAR, SUITE 02, BANHO 02, COZINHA).
- **Cost:** < 2 s.
- **Command:**
  `python -m tools.micro_truth_gate runs/vector/consensus_classified.json --ground-truth ground_truth/planta_74_micro.json --out runs/vector/micro_truth_report.json`
- **Expected:** emits `micro_truth_report.json` schema 1.0;
  4/4 rooms score 1.0.
- **Strict mode:** `--strict` blocks on any score < 1.0.

### G-FIDELITY — Fidelity Engine v1 (Ground Truth v1)
- **Role:** whole-plant golden truth comparison.
- **Cost:** < 2 s.
- **Command:**
  `python -m tools.fidelity.compare_generated_to_expected runs/vector/consensus_classified.json --expected ground_truth/planta_74/expected_model.json --out runs/vector/fidelity_report.json --scorecard runs/vector/fidelity_scorecard.md`
- **Expected:** `global_fidelity = 0.917`, 0 hard_fails, 2 warnings
  (TERRACO TECNICO area marginal, adjacency_f1=0.67 advisory).
- **Strict mode:** `--strict` blocks on any hard_fail.
- **Failure signature:** `global_fidelity < 0.917` or any new
  hard_fail not in the documented baseline.

---

## Tier 2 — medium gates (10 s – 60 s)

### G-COCKPIT-UNIT — cockpit unit + integration tests
- **Role:** validate the Streamlit cockpit + overrides + apply layer.
- **Cost:** ~15 s.
- **Command:**
  `pytest tests/test_cockpit_*.py tests/test_apply_overrides*.py -v`
- **Expected:** all pass.

### G-MUTATION — mutation suite
- **Role:** assert that mutant inputs to the plan-shell exporter
  produce expected detected defects.
- **Cost:** ~30 s.
- **Command:**
  `pytest tests/test_plan_shell_mutant_inputs.py tests/test_plan_shell_mutation_critical_paths.py -v`
- **Expected:** all mutants detected.

### G-CONSUME-CONSENSUS — Ruby exporter contract
- **Role:** lock `tools/consume_consensus.rb` carving + openings +
  passage contracts.
- **Cost:** ~10 s.
- **Command:**
  `pytest tests/test_consume_consensus_*.py -v`
- **Expected:** all pass.

---

## Tier 3 — expensive gates (need SketchUp 2026 or external services)

### G-SMOKE — smoke skp export
- **Role:** the full end-to-end pipeline: consensus → cheap gates →
  SketchUp spawn → `.skp` → inspect → fidelity.
- **Cost:** 60 – 90 s with SU running cold; <30 s if cached on content
  hash.
- **Command (cheap path, no SU):**
  `python -m scripts.smoke.smoke_skp_export <pdf> <out_dir> --skip-skp`
- **Command (full path):**
  `python -m scripts.smoke.smoke_skp_export <pdf> <out_dir>`
- **Expected:** verdict PASS, gates A–G PASS, .skp emitted in band.
- **Failure signature:** any gate FAIL; details in
  `<out_dir>/smoke_report.json`.
- **Bypass content cache:** `--force-skp`.
- **Pre-requisite:** SU 2026 at `C:\Program Files\SketchUp\SketchUp 2026\`.

### G-VISUAL-FIDELITY — visual fidelity gate (2026-05-14 policy)
- **Role:** structural verdict gate cannot promote PASS without the 7
  visual evidence artifacts; see CLAUDE.md §10.
- **Cost:** < 5 s once artifacts exist.
- **Command:**
  `python -m tools.verify_fidelities <consensus> --require-visual-evidence --visual-evidence-dir <dir>`
- **Expected:** top-level verdict respects evidence presence.
- **Protocol:** [`protocols/visual_fidelity_gate_protocol.md`](protocols/visual_fidelity_gate_protocol.md).
- **The 7 required artifacts:** `original_floorplan.png`,
  `skp_render.png`, `overlay_pdf_skp.png`, `diff_walls.png`,
  `diff_doors.png`, `diff_rooms.png`, `mismatches_list.md`.

---

## Tier 4 — CI workflows that bundle multiple gates

| Workflow | Bundles | When it runs |
|---|---|---|
| `.github/workflows/ci.yml` | G-LINT + G-UNIT | every PR + push |
| `.github/workflows/quality_gates.yml` | G-PLAN-TRUTH + G-COHERENCE --strict + G-MICRO --strict + G-FIDELITY | every PR + push |
| `.github/workflows/repo_health.yml` | G-PROJECT-STATE + G-REPO-HEALTH (PR-diff aware) | every PR + push to develop/main |
| `.github/workflows/rubocop.yml` | Ruby lint | PR + push touching Ruby |
| `.github/workflows/skp_fidelity_gate.yml` | G-FIDELITY --strict only | every PR + push |

If a new gate is added, decide which workflow it belongs in (or create
a new one) — and update this file's tier table in the same PR.

---

## Make targets (Unix / WSL / CI)

A canonical [`../Makefile`](../Makefile) wraps the cheap gates:

| Target | Equivalent command |
|---|---|
| `make project-state` | `python scripts/project_state_check.py` |
| `make project-state-json` | `python scripts/project_state_check.py --json` |
| `make repo-health` | `python tools/repo_health_gate.py --mode audit` |
| `make repo-health-check` | `python tools/repo_health_gate.py --mode check --base origin/develop` |
| `make repo-health-fix-dry` | `python tools/repo_health_gate.py --mode fix --dry-run` |
| `make gates` | `make project-state` + `make repo-health-check` |
| `make pytest-gates` | `pytest tests/test_project_state_check.py tests/test_repo_health_gate.py -v` |
| `make ci-local` | mirror of `.github/workflows/repo_health.yml` |

Windows users without `make` should run the right-hand commands
directly — they are the canonical form documented in `PR_HYGIENE.md`
§7 quick-reference card.

---

## How to add a new gate

1. Write the script / test that performs the check.
2. Give it a `G-XXX` short name and pick a tier.
3. Add an entry to this file with: role, cost, command, expected
   output, failure signature.
4. Reference it from [`PROJECT_STATE.md`](PROJECT_STATE.md) §6 if the
   gate is part of the "every change" set.
5. If the gate is a `pytest` file, add it to `tests/`. If it is a CLI,
   add it to `tools/` or `scripts/`.
6. Wire it into the appropriate CI workflow (or `quality_gates.yml`).

---

## Update log

| Date | Commit | What changed |
|---|---|---|
| 2026-05-24 | (this commit) | Initial canonical gate catalogue. All gates currently in `tests/` and CI workflows enumerated with cost + command + failure signature. |
