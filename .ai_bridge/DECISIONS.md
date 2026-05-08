# Decisions — ADR-lite log

> Append-only. Each decision is a small ADR. When a decision graduates
> to architectural status (affects > 1 file or > 1 PR semantics),
> promote to `docs/adr/`.

## Decision template

```
## YYYY-MM-DD — <short title>

### Context
<why this decision was needed>

### Options considered
1. <option A> — <pros/cons>
2. <option B> — <pros/cons>

### Decision
<what was chosen>

### Reason
<one paragraph rationale>

### Consequences
- <forward consequence>
- <backward consequence>

### Rollback
<exact commands or 'not applicable'>
```

---

## 2026-05-07 — Plan Truth Gate stays pytest-only (no JSON report)

### Context

Stage 1.5 had 3 deliverables: `coherence_report.json`,
`plan_truth_report.json`, `micro_truth_report.json`. The Plan Truth
Gate ended up as a pytest assertion (15 tests) without a JSON
artifact. User flagged this as a critério inconsistency.

### Options considered

1. **Add JSON emission** — small PR (~30 min), `plan_truth_report.json`
   becomes a 3rd deliverable file. Pro: symmetric with the other 2.
   Con: vanity artifact (gate is regression-only, file adds nothing).
2. **Accept pytest-only** — Plan Truth Gate's deliverable IS the
   pass/fail exit code. Pro: no extra PR, no vanity. Con: criterion
   list needs adjustment.

### Decision

Option 2. Plan Truth Gate ships as pytest-only.

### Reason

The gate is a regression detector, not an operational report. Pytest
is the right vehicle. `coherence_report.json` and `micro_truth_report.json`
are diagnostics with downstream consumers — different nature.

### Consequences

- Final criterion list: ✓ coherence_report.json + ✓ micro_truth_report.json
  + ✓ Plan Truth Gate pytest verde.
- No 6th PR opened just for this.
- Future: if CI needs an artifact for archival, open a tiny PR then
  (not now).

### Rollback

`docs/adr/2026-05-07-plan-truth-gate-no-json.md` would be the home
if this graduates to ADR. For now, just delete this entry.

---

## 2026-05-07 — Inspector v2 = additive schema, never break v0 readers

### Context

Inspector report needs SHA256 + schema_version + structural section.
Should the new Ruby strip legacy fields or keep both?

### Options considered

1. **Replace** legacy top-level keys with `structural` section.
   Pro: clean schema. Con: breaks `inspect_metrics.py` and any
   downstream that reads `default_faces_count` at top level.
2. **Add** new `structural` section alongside legacy keys.
   Pro: zero downstream breakage. Con: 2x storage of some counters.

### Decision

Option 2. Both v0 and v2 fields coexist; readers prefer
`structural.*` when present, fall back to top-level for v0.

### Reason

Historical reports in `runs/` need to remain parseable. Schema
evolution should be additive until a hard major bump (2.0) with a
documented migration path.

### Consequences

- `tools/inspect_metrics.py.from_dict` now has explicit
  `structural.get(..., legacy_default)` fallbacks.
- New `tools/skp_inspection_report.py` reader handles both formats
  via `is_v2()` helper.
- v2 reports are slightly bigger (~+200 bytes); negligible.

### Rollback

Revert PR #49 (`4cb968f`). Old reports unaffected.

---

<!-- New decisions below this line, newest at top -->
