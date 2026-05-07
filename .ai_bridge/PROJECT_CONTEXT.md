# Project Context — sketchup-mcp

> **Stable** project-level context. Updated only when mission /
> architecture / canonical paths shift. Last reviewed: 2026-05-07.

## Mission

Build a reliable pipeline:

```
PDF/floorplan → extraction → consensus_model.json → validation → renders → SketchUp .skp
```

Priority: **structural fidelity for furniture/layout planning**, not
perfect CAD precision.

## Pipeline (V7 vector-first)

5 deterministic stages, each with versioned schema:

```
build_vector_consensus → extract_room_labels → rooms_from_seeds
  → extract_openings_vector → classify_openings_by_room_context
```

Each stage emits a JSON; downstream stages read from the previous.
Final consensus feeds into:
- `tools/consume_consensus.rb` (Ruby, runs inside SU 2026) → `.skp`
- `tools/coherence_audit.py` → `coherence_report.json` + `questions.json`
- `tools/micro_truth_gate.py` → `micro_truth_report.json`
- `scripts/smoke/smoke_skp_export.py` → 8-gate validation harness

## Key paths

| Path | Purpose |
|---|---|
| `CLAUDE.md` | Constitution. Read at session start. INVIOLABLE rules in §0-§5. |
| `tools/` | Pipeline executables (Python + Ruby) |
| `tests/baselines/planta_74.json` | Plan Truth Gate baseline (regression lock) |
| `ground_truth/planta_74_micro.json` | First external truth (SALA DE ESTAR) |
| `config/assumptions.yaml` | Project-level decision policy (Stage 1 audit) |
| `docs/SCHEMA-COHERENCE-REPORT.md` | Schema spec for audit JSONs |
| `docs/ops/` | Long-session operational snapshots |
| `docs/learning/` | Bug patterns, lessons, decision logs |
| `runs/` | Local artifacts (gitignored). §1 protected. |
| `reports/` | Audit/perf outputs (gitignored except `.example.json`) |

## Hard rules (CLAUDE.md §1, never override)

1. Never delete history under `runs/`, `patches/`, `docs/`, `vendor/`.
2. Never change `consensus_model.json` schema without approval.
3. Never change geometry thresholds (`WALL_HEIGHT_M`, `PT_TO_M`,
   `snap_tolerance`, etc.) without sweep + approval.
4. Never modify Ruby/SU exporter logic
   (`tools/consume_consensus.rb`, `tools/inspect_walls_report.rb`,
   `tools/autorun_*.rb`, `tools/su_boot.rb`) without approval.
5-10. See CLAUDE.md §1 for the full list.

## Git flow (CLAUDE.md §0, INVIOLABLE)

- Branch from `develop`. PR to `develop`. Never directly to `main`.
- `main` only receives `develop → main` promotion PRs.
- Branch naming: `feature/`, `fix/`, `chore/`, `docs/`, `perf/`,
  `refactor/`, `test/`, `agents/`, `tooling/`, `validate/`, `hotfix/`.
- Delete branches (local + remote) after merge.

## Three trincos

What was loose before, locked now in `develop`:

1. PDF → SKP determinístico (Ruby exporter + smoke gate)
2. Incerteza auditável (`confidence`/`decision`/`hypotheses` per opening
   + `coherence_report.json`)
3. Verdade externa mínima (`ground_truth/planta_74_micro.json` + score)

## Canonical commands

```bash
# In-scope test set (excludes pre-existing raster failures + dashboard)
.venv/Scripts/python.exe -m pytest tests/test_planta_74_truth_gate.py \
    tests/test_micro_truth_gate.py tests/test_coherence_audit.py \
    tests/test_assumptions_loader.py tests/test_classify_openings_by_room_context.py \
    tests/test_consume_consensus_*.py tests/test_classify_opening_kind.py \
    tests/test_detect_wall_gaps.py tests/test_inspect_metrics.py \
    tests/test_skp_inspection_report_v2.py tests/test_smoke_gate_g2_inspector.py -q

# Full pipeline + audits + smoke
PY=.venv/Scripts/python.exe; RUN=runs/<name>; PDF=planta_74.pdf
$PY -m tools.build_vector_consensus $PDF --out $RUN/c0.json --detect-openings
$PY -m tools.extract_room_labels $PDF --out $RUN/labels.json
$PY -m tools.rooms_from_seeds $RUN/c0.json $RUN/labels.json --out $RUN/c1.json --canonicalize-rooms --room-canonicalization-tol 8
$PY -m tools.extract_openings_vector $PDF --consensus $RUN/c1.json --out $RUN/c2.json --mode replace --classify-kind --detect-wall-gaps
$PY -m tools.classify_openings_by_room_context $RUN/c2.json --out $RUN/c3_classified.json
$PY -m tools.coherence_audit $RUN/c3_classified.json --out-dir $RUN
$PY -m tools.micro_truth_gate $RUN/c3_classified.json --ground-truth ground_truth/planta_74_micro.json --out $RUN/micro_truth_report.json
$PY scripts/smoke/smoke_skp_export.py --consensus $RUN/c3_classified.json --out-dir $RUN --force-skp
```

## Known baseline (planta_74)

```
walls=33  rooms=11  openings=11  soft_barriers=8
by_kind = {interior_door: 6, interior_passage: 2, window: 1, glazed_balcony: 2}
by_decision = {clean: 7, debug: 4}
SALA DE ESTAR micro_truth score = 1.0
```

Locked by `tests/baselines/planta_74.json`. Any drift fails the
Plan Truth Gate.
