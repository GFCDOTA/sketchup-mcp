# ADR-001 — Validation Cockpit Mutation Surface

> **Status:** Proposed (2026-05-08)
> **Supersedes:** none (first ADR in `docs/adr/`)
> **Author:** Claude session, authorized by Felipe (YELLOW autonomous)
> **Related:** `docs/validation_cockpit.md`, `.ai_bridge/DECISIONS.md`, `tools/fidelity/compare_generated_to_expected.py`, `scripts/smoke/smoke_skp_export.py`

---

## 1. Context

The Validation Cockpit shipped as a feature-complete **read-only**
slice across Cycles 12 / 12b / 12c / 12d / 12e / 12f. It now lets a
human visually validate what the pipeline understood from a PDF
**before** paying the 60–90 s SketchUp export cost — overlay,
expected_model match, history, Pre-SKP Review status, all
read-only.

The next phase is a different *kind* of feature: the cockpit must
start **accepting human decisions** that change how the pipeline
treats a run. Specifically:

- accept / reject individual elements (openings, rooms),
- correct an opening's `kind_v5` or `room_left/right` connect,
- correct a room label,
- mark a room or opening as suspect (don't fail, just flag),
- block SKP export when the human says the run isn't safe.

A naive implementation ("just add an Approve button") would
implicitly invent a contract for how the pipeline accepts human
truth. That contract touches **ground truth**, **fidelity scoring**,
**SKP export**, and **audit trail** simultaneously. Getting it wrong
once means rebuilding when the first real review case breaks the
assumptions.

This ADR defines the contract **before any UI button is shipped.**

## 2. Decisions (the contract)

### 2.1. Two artefact types, one mutation surface

The cockpit's mutation surface produces **two** new artefacts. They
live side-by-side in the run dir, are versioned by consensus
SHA-256, and never modify the source `consensus_*.json`.

| File | Schema | Purpose | Author |
|---|---|---|---|
| `runs/<run_id>/review_overrides.json` | `review_overrides_v1` | Human decisions: approve / reject / re-classify / block. **Authoritative human voice.** | Human via cockpit (Slice 2) |
| `runs/<run_id>/proposed_actions.json` | `proposed_actions_v1` | Pipeline / agent suggestions: "this opening kind looks wrong, suggest re-classify". Advisory only. | Pipeline / agents (Slice 3) |

The cockpit's job is to **show both** and let the human resolve.
The pipeline's job is to **emit proposed_actions** and **honour
review_overrides** when it next runs.

### 2.2. File location

Both files live under the run directory:

```
runs/<run_id>/
├── consensus_*.json            (existing, unchanged, unmutated)
├── fidelity_report.json        (existing)
├── review_overrides.json       (NEW — human decisions, authoritative)
├── proposed_actions.json       (NEW — agent suggestions, advisory)
└── pre_skp_review_report.json  (NEW — F0 gate output, computed)
```

**Why per-run, not per-plant:** override files reference run-specific
element IDs (`r000`, `o3`, etc.) which are unstable across runs. A
review of run A shouldn't bleed into run B even if both are of
`planta_74` — re-running the pipeline produces fresh IDs.

**Future-graduation path (out of scope this ADR):** when an override
proves stable across multiple runs of the same plant, it can be
graduated into `ground_truth/<plan_id>/expected_model.json` as a
`manual_correction` entry. That graduation is a separate, deliberate
human action — never automatic.

### 2.3. Schema v1 — `review_overrides.json`

```json
{
  "schema_version": "review_overrides_v1",
  "run_id": "feature_room_context_2026_05_06",
  "consensus_sha256": "<sha256 of consensus_with_room_context.json at the moment overrides were written>",
  "consensus_path": "runs/feature_room_context_2026_05_06/consensus_with_room_context.json",
  "created_at": "2026-05-09T14:23:00Z",
  "last_updated_at": "2026-05-09T14:35:12Z",
  "overrides": [ /* see §2.5 */ ],
  "global": {
    "block_skp_export": false,
    "block_reason": null
  },
  "audit_trail": [ /* see §2.7 */ ]
}
```

**Required at top level:** `schema_version`, `run_id`,
`consensus_sha256`, `created_at`, `overrides`, `audit_trail`.

### 2.4. Schema v1 — `proposed_actions.json`

```json
{
  "schema_version": "proposed_actions_v1",
  "run_id": "feature_room_context_2026_05_06",
  "consensus_sha256": "<sha256 of source consensus>",
  "generated_at": "2026-05-09T14:00:00Z",
  "generator": "tools/propose_skp_actions.py@v0.1",
  "actions": [ /* see §2.6 */ ]
}
```

**Required at top level:** `schema_version`, `run_id`,
`consensus_sha256`, `generated_at`, `generator`, `actions`.

### 2.5. Override types (7 in v1)

Every entry in `overrides[]` carries a stable shape:

```json
{
  "id": "<uuid4>",
  "type": "<one of the 7 below>",
  "target": { "kind": "opening" | "room", "id": "o3" },
  "payload": { /* type-specific */ },
  "author": "human" | "agent:<name>",
  "created_at": "2026-05-09T14:23:00Z",
  "reason": "free text, why this override exists",
  "signature": "<sha256 of {target,payload,author,created_at}>"
}
```

The 7 v1 types:

| Type | `target.kind` | Payload | Effect |
|---|---|---|---|
| `opening_kind_override` | `opening` | `{ "new_kind_v5": "<one of: interior_door, interior_passage, window, glazed_balcony, exterior_door, unknown>" }` | When pipeline applies, the opening's `kind_v5` is replaced. Original is preserved at `_kind_v5_original`. |
| `opening_connects_override` | `opening` | `{ "room_left_id": "r1", "room_right_id": "r2" }` | Replaces `room_left_id`/`room_right_id` on the opening. Originals preserved with `_*_original` suffix. |
| `room_label_override` | `room` | `{ "new_name": "SUITE 01" }` | Replaces room `name`. Original preserved. |
| `mark_suspect` | either | `{ "severity": "low" \| "medium" \| "high", "tag": "<short tag>" }` | Element keeps its values but gets `_suspect: { severity, tag }`. Cockpit shows orange outline. |
| `reject_element` | either | `{}` | Element is **dropped** from amended_observed. Original preserved at run-level for audit. Counts deltas in fidelity will move. |
| `approve_element` | either | `{}` | Element is **whitelisted**. Pipeline cannot drop or amend it. `_approved: true` set. |
| `block_skp_export` | n/a (top-level under `global`) | `{ "reason": "<text>" }` | Sets `global.block_skp_export=true`. F0 gate FAILS. |

**Precedence when multiple overrides target the same element:**
`reject_element` > `mark_suspect` > explicit kind/connect/label
overrides > `approve_element` > nothing. Within the same precedence
level, last `created_at` wins.

**Validation rules (enforced when reading):**
- `target.id` must exist in the source consensus (validated against
  `consensus_sha256`).
- `opening_kind_override.payload.new_kind_v5` must be in the
  enumerated set (mirrors `tools/classify_openings_by_room_context.py`).
- `opening_connects_override.payload.room_*_id` must exist in the
  consensus's `rooms[]`.
- `mark_suspect.payload.severity` ∈ `{low, medium, high}`.
- A consensus_sha256 mismatch invalidates ALL overrides — they
  remain on disk for human re-confirmation but are NOT applied.

### 2.6. Proposed action types (6 in v1)

```json
{
  "id": "<uuid4>",
  "type": "<one of the 6 below>",
  "target": { "kind": "opening" | "room", "id": "o3" },
  "payload": { /* type-specific */ },
  "confidence": 0.0,                  /* 0.0–1.0 */
  "rationale": "free text, why agent suggests this",
  "generator": "tools/propose_skp_actions.py@v0.1",
  "created_at": "2026-05-09T14:00:00Z"
}
```

The 6 v1 types:

| Type | Payload | Suggested human action |
|---|---|---|
| `classify_opening` | `{ "suggested_kind": "<kind_v5>", "evidence": [...] }` | Apply `opening_kind_override` |
| `expand_room_polygon` | `{ "delta_pts": [[x,y]...], "delta_area_pts2": <float> }` | Apply manual polygon edit (deferred to future) OR `room_label_override` if name was wrong |
| `shrink_room_polygon` | same shape | Same; suggests scope reduction |
| `relink_opening_rooms` | `{ "new_room_left_id": "r1", "new_room_right_id": "r2" }` | Apply `opening_connects_override` |
| `mark_low_confidence` | `{ "current_confidence": <float> }` | Apply `mark_suspect` with severity=low |
| `request_human_review` | `{ "reason_codes": ["...", ...] }` | Force the run into the WARN band — reviewer must explicitly approve before SKP |

Proposed actions are advisory. They're **never** automatically
applied. They feed cockpit UX (suggestion chips next to each
element) but the human always clicks the override.

### 2.7. Audit trail

`review_overrides.json` carries an `audit_trail[]` listing every
mutation event to the file:

```json
{
  "id": "<uuid4>",
  "event": "create" | "update" | "delete",
  "override_id": "<uuid4 from overrides[]>",
  "actor": "human:fmodesto30" | "agent:<name>",
  "timestamp": "2026-05-09T14:23:00Z",
  "before": { /* previous override state, null on create */ },
  "after":  { /* new override state, null on delete */ },
  "diff_signature": "<sha256 of {before,after}>"
}
```

**Append-only.** The cockpit / API never deletes audit entries.
A "remove an override" action is recorded as `event: delete` with
`after: null`. The override is then filtered out at apply time, but
the trail remains.

### 2.8. F0 gate behavior — Pre-SKP Review

Lives in the smoke harness as a new gate **before** `gate_f`. The
existing `cockpit.history_view.pre_skp_review` (Cycle 12f) already
implements the *advisory* logic; F0 is the *enforced* version.

Inputs:
- `runs/<run_id>/fidelity_report.json` (must exist; FAIL if missing)
- `runs/<run_id>/review_overrides.json` (optional)
- `runs/<run_id>/proposed_actions.json` (optional, ignored at this gate)

Output: `runs/<run_id>/pre_skp_review_report.json`

```json
{
  "schema_version": "pre_skp_review_v1",
  "verdict": "PASS" | "WARN" | "FAIL",
  "reasons": ["..."],
  "fidelity_score": 0.917,
  "hard_fails_count": 0,
  "warnings_count": 2,
  "active_overrides_count": 0,
  "block_skp_export": false,
  "recommendation": "safe to export SKP" | "review before SKP" | "do not export SKP"
}
```

**Verdict logic (v1):**
- `FAIL` ← `block_skp_export=true` OR fidelity < 0.69 OR
  `hard_fails_count > 0` OR `consensus_sha256` mismatch on overrides
- `WARN` ← fidelity ∈ [0.69, 0.85) OR `warnings_count > 3` OR any
  `mark_suspect` with severity=high OR any `request_human_review`
- `PASS` ← otherwise

**CLI flag on the smoke harness:** `--review-mode={off,warn,block}`,
default `off` so existing smoke runs don't change behaviour.

| `--review-mode` | F0 verdict `PASS` | F0 verdict `WARN` | F0 verdict `FAIL` |
|---|---|---|---|
| `off` (default) | continue | continue | continue (warns to stderr) |
| `warn` | continue | continue (warns) | continue (warns LOUDLY) |
| `block` | continue | continue (warns) | **abort smoke**, exit non-zero |

The default `off` means **shipping the F0 gate does NOT change CI
green-ness on day one.** Adoption of `block` is a deliberate flip
in a follow-up PR after Slice 3 lands and is exercised on a real
review case.

### 2.9. Pipeline consumption — phased

The pipeline reads overrides through a thin layer, never directly:

```
consensus_*.json + review_overrides.json
        ↓
tools/apply_overrides.py
        ↓
amended_observed.json   (NEW, schema = consensus + override metadata)
        ↓
fidelity engine compares amended_observed to expected_model
```

**Phase 0 (current — already shipped):** nothing reads overrides.
The cockpit's Cycle 12f Pre-SKP Review already exists as advisory.

**Phase 1 (Slice 2):** cockpit reads `review_overrides.json` for
display. If present, the Expected / History tabs show "with
overrides applied" stats alongside raw stats. **The pipeline still
ignores overrides entirely.**

**Phase 2 (Slice 3):** `tools/apply_overrides.py` is introduced.
Smoke harness gains gate_f0 with `--review-mode`. Fidelity engine
gets a new param `apply_overrides: bool = False` that, when true,
reads `review_overrides.json` and computes against the amended
observation.

**Phase 3 (future, NOT in this ADR):** cockpit POSTs overrides via
FastAPI; mutation UI lands. Until Phase 3, `review_overrides.json`
is hand-edited (or written by a CLI helper).

The detector itself (`tools/build_vector_consensus.py`,
`tools/extract_openings_vector.py`, etc.) is **never** modified to
read overrides. Overrides live as a layer above the detector.

### 2.10. Safety rules (invariants)

These are non-negotiable for the lifetime of the mutation surface:

1. **Originals are immutable.** `consensus_*.json` is never edited
   in place. Apply layer produces `amended_observed.json` as a NEW
   file.
2. **Overrides are a layer, not a replacement.** Apply layer always
   keeps `_<field>_original` for any field it changes, so the raw
   detector output is recoverable from any amended view.
3. **Audit trail is append-only.** No event is ever deleted from
   `audit_trail[]`. A "rollback" is a new override entry that
   reverses a previous one.
4. **Source attribution is mandatory.** Every element in the
   amended observed carries a `source` field with one of:
   - `detected` — straight from the detector, no override touched it
   - `manual` — overridden by a human via cockpit
   - `proposed` — would have been proposed but no override applied
   - `override_rejected` — element exists in detector but
     `reject_element` override drops it
5. **Fidelity is never silently masked.** When fidelity is computed
   on amended observed, the report carries:
   - `global_fidelity` (post-override)
   - `global_fidelity_pre_override` (the pre-override score)
   - `overrides_applied_count`
   so a review can never make the score look better without leaving
   evidence.
6. **Consensus SHA-256 binds overrides.** Any override file whose
   `consensus_sha256` doesn't match the live consensus is
   invalidated until the human re-confirms. Stale overrides never
   silently apply.
7. **`block_skp_export` is sticky.** Once set, it remains until
   explicitly cleared via a new audit-trailed event. The cockpit
   shows a banner. The smoke harness, in `--review-mode=block`,
   refuses to export.
8. **The detector pipeline never reads overrides.** Overrides live
   strictly between fidelity scoring and SKP export. Detector
   output is reproducible from PDF alone, override-free, forever.

## 3. Slice 2 plan (read/write minimal cockpit)

Derived directly from this ADR. Out of scope for this PR; landed in
a follow-up.

**Goal:** the cockpit reads + writes `review_overrides.json` for
the active run. No FastAPI yet — Streamlit's session-state +
filesystem write is enough for a single-user local tool.

**Touchpoints:**
- `cockpit/overrides.py` (NEW) — pure helper:
  `load_overrides(run_dir, expected_consensus_sha) -> dict` and
  `save_override(run_dir, override_payload, audit_actor) -> dict`.
  Hash-validates and updates the audit trail. No streamlit imports.
- `cockpit/app.py` — new "Review" tab: dropdown per opening to
  re-classify, dropdown per room to re-label, "mark suspect"
  toggle, "reject" button, "block SKP export" master toggle.
- `tests/test_cockpit_overrides.py` — round-trip tests (write →
  read → assert), audit-trail append-only, sha256 invalidation
  behaviour, payload schema validation.
- `docs/validation_cockpit.md` — Slice 2 section.

**What Slice 2 does NOT do:**
- Does NOT modify the consensus.
- Does NOT compute amended fidelity.
- Does NOT run the smoke harness.
- Does NOT block anything — pipeline still ignores the file.

**Acceptance:** I can open the cockpit, override an opening's kind,
close the cockpit, re-open it, see the override persisted, see the
audit trail, and see the kind reflected on the SVG with `source:
manual` annotation.

## 4. Slice 3 plan (apply layer + F0 gate)

**Goal:** the pipeline starts honouring overrides; smoke harness
gains the F0 gate; cockpit's Pre-SKP Review reads the F0 verdict
instead of computing locally.

**Touchpoints:**
- `tools/apply_overrides.py` (NEW) — CLI: reads consensus +
  overrides, writes `amended_observed.json`. Pure function plus a
  thin CLI shell.
- `tools/fidelity/compare_generated_to_expected.py` — new optional
  param `apply_overrides: bool = False`. When True, reads overrides
  via `apply_overrides.py` first.
- `scripts/smoke/smoke_skp_export.py` — new `gate_f0` inserted
  before `gate_f`. Reads fidelity_report + overrides, emits
  `pre_skp_review_report.json`. Honours `--review-mode={off,warn,block}`.
- `cockpit/history_view.py` — `pre_skp_review()` switches to read
  `pre_skp_review_report.json` if present, falls back to the
  in-memory computation otherwise (12f behaviour preserved for
  runs without F0 reports).
- Tests for: amended-observed schema, fidelity engine in
  apply-overrides mode, gate_f0 verdict logic, --review-mode CLI
  matrix.
- Docs: `docs/validation/sketchup_smoke_workflow.md` updated for
  gate_f0; `docs/validation_cockpit.md` Slice 3 section.

**What Slice 3 does NOT do:**
- Does NOT default `--review-mode` to `block` — that's a separate
  follow-up after one real review case.
- Does NOT change any existing fidelity threshold.
- Does NOT add UI — just consumes what Slice 2 wrote.

## 5. Alternatives considered (and rejected)

### A. "Edit the consensus directly via cockpit"
**Why rejected:** Violates safety rule §2.10.1. Loses the audit
trail. Makes detector regressions invisible — if the detector
silently degrades, an old human edit might mask it forever.

### B. "Store overrides under `ground_truth/<plan_id>/`"
**Why rejected:** Override entries reference run-specific element
IDs which are unstable across runs. Per-plant graduation is a
*future* deliberate human action, not the default storage. Mixing
per-run override audit history into per-plant ground truth pollutes
the GT corpus.

### C. "FastAPI POST + sqlite database for overrides"
**Why rejected:** Premature complexity for a single-user local tool.
Streamlit + filesystem JSON is enough through Slice 2. FastAPI lands
in Phase 3 only when multi-user / remote needs surface.

### D. "Make overrides a CLI-only feature, no cockpit UI"
**Why rejected:** Defeats the cockpit's purpose. The whole point of
the cockpit is that the human looks visually + decides. CLI
overrides would force back to grep-and-edit JSON — exactly what
Cycle 12 was supposed to eliminate.

### E. "Gate F0 defaults to `block` from day one"
**Why rejected:** would break green CI immediately on any run with
fidelity < 0.85, which is most current runs. Default-off keeps the
gate ship-able as additive infrastructure; flipping to default-on
is a deliberate later decision after evidence on a real review case.

### F. "Skip proposed_actions.json — humans should drive the review"
**Why rejected:** the pipeline already knows things the human will
discover later (low-confidence kind classifications, ambiguous
adjacencies). Surfacing those as `proposed_actions` reduces the
human's visual scanning load. They remain advisory; the human still
clicks.

## 6. Consequences

### Positive
- Cockpit becomes a control surface, not just a viewer.
- SKP export gains a hard human gate when needed (`block_skp_export`).
- Fidelity reporting becomes honest about override-induced score
  changes (`global_fidelity_pre_override`).
- Detector path stays purely reproducible from PDF — no human
  feedback contamination.
- Per-run audit trail makes "who said what when" answerable.

### Negative / costs
- New schemas to maintain (`review_overrides_v1`,
  `proposed_actions_v1`, `pre_skp_review_v1`,
  `amended_observed_v1`).
- New module: `cockpit/overrides.py`.
- New module: `tools/apply_overrides.py`.
- New smoke gate: `gate_f0`.
- Cockpit complexity grows (Review tab + override status surfaces
  in Expected / History / Diff tabs).
- Test surface expands ~30 unit tests across Slices 2 + 3.

### Reversibility
- Slice 2 alone can be reverted by deleting `cockpit/overrides.py`
  + the Review tab from `cockpit/app.py`. No persistent damage —
  written `review_overrides.json` files remain on disk and can be
  read by future versions.
- Slice 3 alone can be reverted by removing `gate_f0` from the
  smoke pipeline (default `--review-mode=off` means no behaviour
  change anyway) and reverting the fidelity engine's
  `apply_overrides` param. Existing fidelity reports unchanged.
- The schemas, once shipped, are versioned (`_v1`) so v2 can land
  without breaking v1 readers.

## 7. Rollback procedure

If this contract proves wrong after Slice 2 ships:

1. Stop writing new overrides via cockpit.
2. Add a deprecation banner in the cockpit's Review tab pointing at
   ADR-002 (the corrected contract).
3. Slice 3's `apply_overrides.py` learns to read both `_v1` and
   the new schema; at apply time, v1 entries either migrate or are
   surfaced for re-confirmation.
4. ADR-001 status updates to "Superseded by ADR-002" with the
   migration plan.

The contract is reversible because:
- No detector code reads overrides.
- No existing artefact format is changed (consensus, fidelity report
  remain backward-compatible).
- All new schemas carry `_v1` versioning.

## 8. Open questions (resolved before merging this ADR)

1. **Should `reject_element` cascade?** If a room is rejected, do
   its openings auto-reject?
   **Resolution:** No. Cascade in v1 is too magic. The reviewer
   rejects each element explicitly. Cockpit can offer a "reject all
   children" convenience button but each click writes its own
   audit-trailed override.

2. **Where does `block_skp_export` live in the JSON?**
   **Resolution:** Top-level `global.block_skp_export` (boolean) +
   `global.block_reason` (string). Not under `overrides[]` because
   it's not per-element. Audit-trailed like any other change.

3. **Can two overrides target the same element?**
   **Resolution:** Yes, but precedence rules apply (§2.5). Cockpit
   shows ALL overrides on an element, indicating which is active.

4. **Is the consensus_sha256 the source consensus or the post-room-context?**
   **Resolution:** Whatever consensus the cockpit was looking at
   when the human made the decision. Recorded in
   `consensus_path` for clarity. If the run produces multiple
   consensus files (raw → with_room_context → with_openings), the
   override file binds to ONE specific path + sha. A re-run with
   a new pipeline pass invalidates the override binding.

## 9. Acceptance for this ADR

This ADR is mergeable when:

- [x] All 10 Felipe-listed deliverables are addressed (ADR doc,
  `review_overrides_v1` schema, `proposed_actions_v1` schema, file
  location, 7 override types, 6 proposed_action types, F0 gate
  behaviour, pipeline consumption phasing, safety rules, Slice 2
  plan, Slice 3 plan).
- [x] Risks documented (§5 alternatives, §6 consequences).
- [x] Next PR (Slice 2) is clearly derivable from this ADR without
  needing further architectural decisions — only implementation
  decisions.
- [ ] CI green on the docs PR.

## 10. References

- `docs/validation_cockpit.md` — current cockpit doc (read-only
  slice as of `a87185c`)
- `tools/fidelity/compare_generated_to_expected.py` — fidelity
  engine that the F0 gate consumes
- `scripts/smoke/smoke_skp_export.py` — smoke harness gate_f
  (existing) is what gate_f0 will run before
- `cockpit/history_view.py` — Cycle 12f's existing `pre_skp_review`
  function (advisory) becomes the seed for the F0 gate logic
- `.ai_bridge/DECISIONS.md` — ADR-lite log (this ADR is referenced
  there with a one-line pointer)
- `CLAUDE.md` §1 (safety rules), §2 (pipeline invariants), §3 (the
  SketchUp Rule), §17 (DONE-IS-NOT-STOP)
