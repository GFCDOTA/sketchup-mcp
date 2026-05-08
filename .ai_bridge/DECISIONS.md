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

## 2026-05-08 — Mutation Surface contract → promoted to ADR-001

### Context

The cockpit's read-only slice is feature-complete (Cycles 12 / 12b /
12c / 12d / 12e / 12f). The next phase has a different nature: it
must accept human decisions (approve / reject / re-classify / block
SKP). That contract touches ground truth, fidelity scoring, SKP
export, and audit trail simultaneously — too cross-cutting for an
ADR-lite entry.

### Options considered

1. **Inline ADR-lite here** — fast, but the contract is too detailed
   (7 override types, 6 proposed-action types, 8 safety rules,
   F0 gate semantics) to fit the lightweight format.
2. **Promote to a full ADR under `docs/adr/`** — heavier process but
   the right home for a multi-PR contract that future readers will
   reference.

### Decision

**Promote.** Created `docs/adr/` (first ADR in the repo) and shipped
**ADR-001 — Validation Cockpit Mutation Surface** as the canonical
contract for review_overrides_v1 + proposed_actions_v1 + the F0
pre-SKP gate.

### Reason

The contract spans:
- 4 new schemas (review_overrides_v1, proposed_actions_v1,
  pre_skp_review_v1, amended_observed_v1)
- ≥3 new files / modules across Slices 2 and 3
  (`cockpit/overrides.py`, `tools/apply_overrides.py`,
  smoke `gate_f0`)
- 8 invariants ("override never deletes original",
  "audit trail is append-only", etc.) that must survive future PRs

A future agent reading just `.ai_bridge/DECISIONS.md` couldn't
derive that. ADR-001 gives them a single document to land on.

### Consequences

- Future cockpit-mutation work derives from ADR-001 without
  re-litigating the contract.
- `.ai_bridge/DECISIONS.md` keeps its tactical role; `docs/adr/`
  takes the architectural one.
- ADRs are append-only and numbered; supersession is explicit.

### Rollback

`git revert <merge-sha>` removes the ADR + this entry. Since no code
references the ADR yet (Slices 2/3 are unbuilt), rollback is purely
docs-level.

---

## 2026-05-08 — Validation Cockpit MVP: Streamlit, not vanilla JS+FastAPI

### Context

Two parallel design paths surfaced for the pre-SKP visual-validation UI:

- A previous session had already begun and committed (`30246d6`) a
  Streamlit MVP — `cockpit/app.py` + `cockpit/render_overlay.py`
  (308 LOC pure Python SVG renderer) + 10 unit tests + docs +
  `[cockpit]` extra in `pyproject.toml`.
- A fresh planning session (in plan mode, before discovering the
  pushed work) recommended vanilla JS + FastAPI router under
  `tools/dashboard/cockpit/` to avoid forking the dashboard stack.

### Options considered

1. **Honor fresh plan, discard Streamlit work** — clean stack
   alignment with the existing FastAPI dashboard, but discards
   ~600 LOC of working, tested, reasonable code.
2. **Honor pushed work, abandon fresh plan** — preserves invested
   effort; Streamlit is what GPT recommended in the original
   exploration; ships Slice 1 fastest.
3. **Hybrid** — Slice 1 stays Streamlit (this PR); Slice 2/3 add
   FastAPI when state mutation (review_overrides / proposed_actions
   / pre-SKP gate) makes a Python-only UI insufficient.

### Decision

Option 3 (Hybrid). This PR is the Slice 1 Streamlit MVP. FastAPI
remains reserved for Slice 2/3 when POST endpoints are needed.

### Reason

Streamlit gets us a working visual gate fastest, reuses 100% of
the already-pushed renderer, and respects the rule "preserve
existing work of good quality, prefer the least destructive
path." The renderer itself is dependency-free, so Slice 2/3 can
keep importing it from a future FastAPI surface unchanged.

### Consequences

- Forward: Slice 2 will introduce FastAPI alongside (not replacing)
  the Streamlit shell, since approve/reject persistence + diff +
  pre-SKP gate are inherently mutation-flavoured.
- Forward: `[cockpit]` extra is a permanent install path — must
  stay opt-in so core pipeline + CI never pull in Streamlit.
- Backward: the `tools/dashboard/cockpit/` subdirectory the fresh
  plan assumed is NOT created in Slice 1; it stays as a Slice 2/3
  candidate.

### Rollback

If Streamlit becomes unviable, revert commits `30246d6` + `f11e13c`
on this branch (or after merge, on develop). Renderer code is
self-contained and could be re-mounted under a different UI shell
(plain HTML, FastAPI/Jinja, etc.) without rewriting.

### See also

- `docs/validation_cockpit.md` — UI map + boundary
- `feedback_pre_existing_work_pivot.md` (cross-project memory) —
  the rule that guided this decision

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
