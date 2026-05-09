# ADR-002 — `room_polygon_override` (geometric room overrides)

> **Status:** Proposed (2026-05-09)
> **Supersedes:** none. **Extends:** ADR-001 (additive — no schema-version bump).
> **Author:** Claude session, authorized by Felipe (YELLOW autonomous)
> **Related:** `docs/adr/ADR-001-validation-cockpit-mutation-surface.md`,
> `docs/diagnostics/2026-05-09_dogfood_override_aware_flow.md`,
> `cockpit/overrides.py`, `tools/apply_overrides.py`,
> `tools/propose_skp_actions.py`,
> `tools/fidelity/compare_generated_to_expected.py`,
> `scripts/smoke/smoke_skp_export.py`

---

## 1. Context

The first end-to-end dogfood of the override-aware flow (PR #98,
`docs/diagnostics/2026-05-09_dogfood_override_aware_flow.md`)
exercised the contract on the canonical `planta_74` baseline with
3 real overrides. The contract held: consensus sha256 byte-identical
before/after, detector path provably overrides-blind, fidelity
deltas honestly surfaced.

The dogfood also surfaced **UX gap #2**:

> The most common real failure mode on `planta_74` is "room polygon
> area out of expected range" (FP-012 SUITE 01 = 69.91 m² vs
> expected `[10, 28]`). The 7 v1 override types have no way to
> **adjust a room polygon**. The reviewer's only option is
> `reject_element` on the entire room — which drops it from
> amended_observed entirely and probably HURTS fidelity more than
> it helps (`count_score` then drops).

ADR-001 §2.6 already specifies two **producer-side** advisory action
types — `expand_room_polygon` and `shrink_room_polygon` — with a
`delta_pts` payload. The "Suggested human action" column says:

> Apply manual polygon edit (deferred to future) OR
> `room_label_override` if name was wrong

This ADR closes that deferral by specifying the **consumer-side**
override type that the human applies, and how it interacts with
the producer-side advisory chips that already exist on the
suggestion surface.

It also intentionally **does not** add a graphical polygon-edit
UX in v1. UI work happens after the schema + apply layer + F0
surface land and pass dogfood. Slice 6d (graphical drag-edit)
is deliberately deferred per §4 below.

## 2. Decisions (the contract)

### 2.1. ONE override type, three edit methods

The cockpit gains **one** new override type: `room_polygon_override`.
A discriminator field `payload.edit_method` records HOW the human
arrived at the new polygon — for audit, not for runtime branching.
Permitted methods in v1:

| `edit_method` | Source | Notes |
|---|---|---|
| `manual_draw` | Human typed/pasted vertex list into a text-area control | The fallback; always available |
| `snap_to_walls` | Human picked a polygon by clicking adjacent walls; cockpit derived vertices from wall endpoints | Requires the wall graph to be loaded (Slice 6b) |
| `trace_pdf` | Human drew on the PDF underlay; cockpit captured the SVG path | Requires the PDF underlay (Slice 12b) — deferred to Slice 6d |
| `from_proposed_action` | Human promoted an `expand_room_polygon` / `shrink_room_polygon` proposed action chip | Producer's `delta_pts` is applied to the original polygon to derive the absolute polygon stored in the override |

**Why one type, not three (`expand_room_polygon_override`,
`shrink_room_polygon_override`, `redraw_room_polygon_override`):**
the apply semantics are identical — replace the room's polygon
with the new vertex list. The producer's expand/shrink distinction
is a *suggestion* to the human, not a runtime difference.
Collapsing into one type keeps `cockpit/overrides.py` enum at
8 entries (was 7) and `tools/apply_overrides.py` at one new
branch, not three. Audit trail still captures the method via
`payload.edit_method`.

**Relationship to producer-side proposed_actions:**

```
tools/propose_skp_actions.py emits expand_room_polygon /
                              shrink_room_polygon
        ↓
cockpit Review tab shows chip with computed delta_area
        ↓
human clicks "Apply"
        ↓
cockpit composes the new absolute polygon
(original polygon + producer delta_pts) and writes ONE
review_overrides.json entry of type room_polygon_override
with edit_method="from_proposed_action" and
from_proposed_action_id="<uuid of the chip>"
```

The producer's chip is the ergonomic entry point; the override
is the only authoritative artifact.

### 2.2. Schema additions to `review_overrides_v1` (additive)

This is an **additive** change. `review_overrides_v1` keeps its
schema_version. Existing files written without `room_polygon_override`
remain valid. Readers older than this ADR will simply ignore the
new override type (the existing precedence walk falls through to
`approve_element`'s no-op behaviour for unknown types — verified
in `cockpit/overrides.py` `_PRECEDENCE_ORDER` walk).

**OVERRIDE_TYPES enum update** (`cockpit/overrides.py:38`):

```python
OVERRIDE_TYPES: tuple[str, ...] = (
    "opening_kind_override",
    "opening_connects_override",
    "room_label_override",
    "mark_suspect",
    "reject_element",
    "approve_element",
    "room_polygon_override",          # NEW (ADR-002)
)
```

**Precedence rule update** (`cockpit/overrides.py:_PRECEDENCE_ORDER`):
`room_polygon_override` slots between `opening_connects_override`
and `room_label_override`. Per-element resolution: `reject` >
`mark_suspect` > `room_polygon_override` > `room_label_override` >
explicit kind/connect > `approve` > nothing. Rationale: a polygon
edit is a stronger statement than a label edit (it changes geometry,
not just naming) but weaker than `mark_suspect` (which says "I'm not
sure about this room AT ALL — flag it") or `reject_element` (which
removes the room outright).

### 2.3. Payload shape

```json
{
  "id": "<uuid4>",
  "type": "room_polygon_override",
  "target": { "kind": "room", "id": "r004" },
  "payload": {
    "new_polygon_pts": [[x0, y0], [x1, y1], [x2, y2], ...],
    "edit_method": "manual_draw" | "snap_to_walls" | "trace_pdf" | "from_proposed_action",
    "estimated_area_pts2": 12345.6,
    "estimated_area_m2": 15.27,
    "from_proposed_action_id": "<uuid4 or null>"
  },
  "author": "human:fmodesto30" | "agent:<name>",
  "created_at": "2026-05-09T15:00:00Z",
  "reason": "FP-012 leakage — polygon traced through external windows",
  "signature": "<sha256 of {target,payload,author,created_at}>"
}
```

**Required payload fields:** `new_polygon_pts`, `edit_method`,
`estimated_area_pts2`, `estimated_area_m2`. The `_pts2` and `_m2`
values are written by the cockpit **at save time**, so the F0 gate
and history view never need to recompute geometry just to display
"new area". They are advisory display fields — the apply layer
recomputes from `new_polygon_pts` for fidelity.

**Optional payload fields:** `from_proposed_action_id` (uuid4 of
the producer chip the human promoted). When omitted, the override
came from a fresh manual edit. This mirrors the
`source_proposed_action_id` audit-link Slice 4 already implements
on `audit_trail[]` entries — but on the override record itself,
because polygons are voluminous and the link should be on the
authoritative voice, not just the trail.

**Coordinate system:** PDF points (`pdf_points`), same as the
consensus and ADR-001 §2.6 producer payloads. Conversion to metres
uses the existing `PT_TO_M = 0.19 / 5.4 ≈ 0.0352` per
`feedback_pdf_scale_anchor.md`.

**Polygon orientation:** must be **counter-clockwise** (CCW) per
shapely convention. The validator (§2.4) enforces this and the
cockpit auto-fixes by reversing on save when needed.

### 2.4. Validation rules

Enforced in `cockpit/overrides.py:validate_override_payload` at
write time and again at apply time. A consensus-sha256 mismatch
already invalidates the entire override file per ADR-001 §2.10.6;
these are the per-payload checks on top of that.

| Rule | Failure → |
|---|---|
| `target.kind == "room"` | `errors += "room_polygon_override target.kind must be 'room'"` |
| `new_polygon_pts` is a list of ≥ 3 [x,y] pairs of finite floats | `errors += "new_polygon_pts must be ≥3 finite [x,y] pairs"` |
| `edit_method` ∈ {`manual_draw`, `snap_to_walls`, `trace_pdf`, `from_proposed_action`} | `errors += "edit_method <v> not in <set>"` |
| Polygon is **simple** (no self-intersection) — checked via `shapely.geometry.Polygon(pts).is_valid` | `errors += "new_polygon_pts is not a simple polygon (self-intersecting)"` |
| Polygon area > 0 | `errors += "new_polygon_pts has zero area"` |
| `estimated_area_pts2 > 0` and within 1% of `shapely.geometry.Polygon(pts).area` | `errors += "estimated_area_pts2 disagrees with computed area"` |
| `estimated_area_m2 == estimated_area_pts2 * PT_TO_M ** 2` (within 1%) | `errors += "estimated_area_m2 not consistent with estimated_area_pts2"` |
| `from_proposed_action_id` is `null` or a valid uuid4 string | `errors += "from_proposed_action_id must be uuid4 or null"` |
| **Soft check — wall intersection.** If `consensus["walls"]` is provided, log a warning when the polygon's exterior edges cross more than 2 walls. Does NOT fail validation. | `warnings += "polygon exterior crosses N walls (≥3 is unusual)"` |
| **Soft check — bounding box plausibility.** If the polygon's area in m² is outside `[1.0, 200.0]` (covers smallest plausible bath ≈ 1 m² up to a 200 m² loft), log a warning. Does NOT fail validation. | `warnings += "estimated area <N> m² is outside [1, 200] sanity range"` |

Soft checks ship as **warnings**, not errors, because:
- A reviewer correcting an FP may legitimately produce a polygon
  the detector wouldn't have drawn.
- Hard rejecting on a wall-crossing test would block the very
  case ADR-002 exists to fix (FP-012 SUITE 01 has the polygon
  bleeding through external windows — fixing it requires the
  reviewer to draw a polygon that intersects walls the detector
  treated as exterior).

The cockpit surfaces warnings as a yellow callout next to the
"Save" button. The save proceeds.

### 2.5. Apply semantics

`tools/apply_overrides.py` gains a new branch (mirrors the existing
`opening_kind_override` branch at `cockpit/overrides.py:648`):

```python
elif typ == "room_polygon_override":
    # target.id resolves to a room
    room = _room_by_id(amended, target_id)
    if room is None:
        # consensus_sha256 invalidates the override file already;
        # this should be unreachable. Defensive log + skip.
        continue
    # Preserve originals (ADR-001 §2.10.2 — overrides are a layer)
    room.setdefault("_polygon_pts_original", room.get("polygon_pts"))
    room.setdefault("_area_pts2_original", room.get("area_pts2"))
    room.setdefault("_area_m2_original", room.get("area_m2"))
    # Apply the override
    room["polygon_pts"] = list(payload["new_polygon_pts"])
    room["area_pts2"] = float(payload["estimated_area_pts2"])
    room["area_m2"] = float(payload["estimated_area_m2"])
    # Source attribution (ADR-001 §2.10.4)
    room["source"] = "manual"
    room["_edit_method"] = payload["edit_method"]
    if payload.get("from_proposed_action_id"):
        room["_source_proposed_action_id"] = payload["from_proposed_action_id"]
    # Tally for the metadata block
    overrides_applied_count += 1
    polygon_overrides_applied_count += 1
```

**New per-room fields in `amended_observed.json`:**
- `_polygon_pts_original` — the detector's original polygon
- `_area_pts2_original` / `_area_m2_original` — the detector's
  original areas
- `source: "manual"` — already standard from ADR-001 §2.10.4
- `_edit_method` — copied from the override payload
- `_source_proposed_action_id` — link back to the producer chip
  when applicable

**New per-file metadata in `amended_observed.json._overrides_metadata`:**
- `polygon_overrides_applied_count` — `int`, additive to the
  existing `overrides_applied_count` total

Apply order is governed by `_PRECEDENCE_ORDER`. A room may receive
both `room_polygon_override` (geometry) and `room_label_override`
(name) — both apply, in precedence order. `mark_suspect` on the
same room ALSO applies (it is a flag, not a mutually-exclusive
mutation). `reject_element` on the same room overrides everything
and the polygon override is a no-op (the room is dropped from
amended_observed entirely).

### 2.6. Fidelity engine interaction

`tools/fidelity/compare_generated_to_expected.py` already runs in
two modes (raw and `apply_overrides=True`, per ADR-001 §2.9 Phase 2).
ADR-002 adds **no new mode**. The amended_observed produced in §2.5
is the input to the existing apply-overrides path; `room_score`,
`bbox_score`, and `count_score` all naturally pick up the new
polygon because they read `polygon_pts` and `area_m2` directly.

**Honest reporting** (ADR-001 §2.10.5) is preserved:
- `global_fidelity` (post-override) — uses amended polygons
- `global_fidelity_pre_override` — uses original polygons
- `sub_scores` and `sub_scores_pre_override` — both emitted
  per Slice 5b

**New fidelity-report metadata field** (additive, NOT a schema
version bump):

```json
"_overrides_metadata": {
  ...existing fields...,
  "polygon_overrides_applied_count": 1
}
```

Older readers that don't know about polygon overrides will see
a regular fidelity number that may have moved by a non-trivial
delta (a polygon edit can swing `room_score` by 0.1+). The
existing `overrides_applied_count` already signals "non-zero
overrides applied"; the new `polygon_overrides_applied_count` is
a finer-grained breakdown for the cockpit + F0 surface.

### 2.7. F0 gate (`pre_skp_review_v1`) interaction

`pre_skp_review_v1` gains **one** new additive field:

```json
{
  ...existing fields per Slice 5c/5d...,
  "manual_polygon_room_count": 1
}
```

When non-zero, the F0 verdict logic adds:
- WARN if `manual_polygon_room_count > 0` AND
  `fidelity_score >= fidelity_score_pre_override + 0.05`
  (i.e. polygon overrides moved the score up by 5+ points — a
  human "fixing" a room is suspicious if the score jumps
  dramatically; reviewer should re-confirm).

The existing PASS / WARN / FAIL thresholds (ADR-001 §2.8) are
otherwise unchanged. The new field is purely informational by
default; the new WARN trigger is gated on a measurable score
swing, not on "polygon overrides exist".

The cockpit's Pre-SKP Review pane (Slice 4-extra + 5d) gets a
new line under the existing Δ caption when
`manual_polygon_room_count > 0`:

> ✏️ N room(s) with manual polygon edit — see Review tab for
> details

Clicking the line jumps to the Review tab filtered to
`type=room_polygon_override`.

### 2.8. SKP exporter stays overrides-blind in v1

This is the most dangerous interaction and the one most explicitly
constrained.

**The SKP exporter (`tools/consume_consensus.rb`,
`tools/skp_from_consensus.py`) does NOT read review_overrides.json
in v1.** It only ever sees the original consensus.

Rationale:
- ADR-001 §2.10.8 already invariant: detector path never reads
  overrides. By extension, the SKP exporter (which downstream
  reads consensus directly) inherits the same property.
- A polygon override sufficient to fix `room_score` is NOT
  necessarily a polygon SU can extrude into a valid solid.
  Validating polygon → SU geometry is a separate problem.
- F0 is the gate that decides whether SKP runs at all. If
  `block_skp_export` is set (ADR-001 §2.5 / §2.10.7), SU is
  skipped. If F0 is PASS/WARN, the exporter runs on the **raw
  consensus** as before — not on the amended observation.

**What this means in practice:** a `room_polygon_override` improves
the **fidelity report** and the **cockpit review surface**. It
does NOT change the SKP file the exporter produces. The exporter
draws the detector's original polygon. If the human wants the
SKP to reflect a corrected polygon, they have two paths:
1. Fix the detector (preferred — Cycle 8b's concave-hull default
   was exactly this)
2. Re-run the exporter manually with a different consensus file
   (out of scope for v1)

**Future work (Slice 6e+, NOT in this ADR):** introduce an
`amended_consensus.json` artifact that the exporter optionally
reads. That requires extensive validation (every override-introduced
polygon must round-trip through `tools/skp_from_consensus.py`
without degenerate geometry) and is deliberately deferred until the
fidelity-side surface ships and gets dogfooded.

### 2.9. expected_model interaction

`ground_truth/<plan_id>/expected_model.json` is **never**
auto-derived from `room_polygon_override` entries. The graduation
path described in ADR-001 §2.2 ("when an override proves stable
across multiple runs of the same plant, it can be graduated into
expected_model.json") applies, but graduation is a **deliberate
human action**, never automatic.

When such a graduation does happen (manually, in a future cycle),
the expected_model entry carries the source override's
`edit_method` for audit:

```json
{
  "rooms": [{
    "name": "SUITE 01",
    "polygon_m": [...],
    "_source": "manual_correction",
    "_edit_method": "manual_draw",
    "_promoted_from_override_signature": "<sha256>"
  }]
}
```

This intentionally forbids the most dangerous autoplay path:
"the cockpit notices the human always draws SUITE 01 the same way
and silently writes it into ground truth". That would
permanently corrupt the GT corpus the moment the override is wrong.

## 3. Risks + mitigations

### Risk A — overrides hide a real detector bug

**Scenario:** Detector ships a regression that mis-shapes SUITE 01
polygons. Reviewer applies `room_polygon_override` consistently
across multiple runs. Detector's bug never surfaces because the
fidelity score on amended_observed always looks fine.

**Mitigation:**
1. `global_fidelity_pre_override` always emitted (ADR-001 §2.10.5)
   — the unmodified score is one field away in every fidelity
   report.
2. `_polygon_pts_original` always preserved (§2.5) — the detector
   output is recoverable element-by-element.
3. New `polygon_overrides_applied_count` field on fidelity report
   metadata (§2.6) and `manual_polygon_room_count` on F0 verdict
   (§2.7) make "how many polygons were manually edited" trivially
   queryable in cockpit history view + CI.
4. The detector path stays overrides-blind (§2.8). A regression
   surfaces in raw fidelity scores immediately on any run that
   doesn't carry overrides.
5. Cockpit history view (Cycle 12f) already shows raw vs amended
   side-by-side per Slice 5d. Reviewer scanning history sees the
   delta column and is prompted to ask "why is the raw score
   degrading over time?" before the bug calcifies.

### Risk B — overrides inflate fidelity score artificially

**Scenario:** Reviewer deliberately or accidentally draws polygons
that match `expected_model.json` exactly, gaming the fidelity
score upward. The score looks good; the underlying detector hasn't
improved.

**Mitigation:**
1. F0 gate gains a WARN trigger when
   `manual_polygon_room_count > 0` AND `fidelity_score >=
   fidelity_score_pre_override + 0.05` (§2.7). Big upward jumps
   force re-confirmation.
2. `audit_trail` records every override creation (ADR-001 §2.7) —
   reviewer's pattern is auditable post-hoc.
3. SKP exporter ignores overrides (§2.8) — gaming the fidelity
   score does not produce a "better" SKP. The score gaming has no
   downstream artifact reward, removing the incentive.
4. `global_fidelity_pre_override` is the field CI / regression
   gates should track for "did the detector improve?". Documented
   in `quality_gates.yml` (Slice 6 follow-up doc update).

### Risk C — invalid SKP geometry from overridden polygon

**Scenario:** Reviewer draws a polygon that fixes fidelity but
produces invalid geometry when extruded by SU (self-intersecting
when offset by wall thickness, degenerate triangle, etc.).

**Mitigation:**
1. SKP exporter ignores overrides in v1 (§2.8). The exporter only
   sees the detector's original polygon. Override-induced
   geometry never reaches SU.
2. Validation rule (§2.4) enforces simple (non-self-intersecting)
   polygon at write time — even though SU never sees it, the
   review artifact is still a valid polygon for the fidelity engine.
3. Future Slice 6e (amended_consensus.json) explicitly defers this
   problem — and its acceptance criterion is "every overridden
   polygon round-trips through skp_from_consensus without
   degenerate geometry, validated by the smoke harness".

### Risk D — conflict between expected_model and manual override

**Scenario:** `expected_model.json` says SUITE 01 area ∈ [10, 28].
Reviewer applies `room_polygon_override` producing area = 35. The
fidelity engine reports the room as out-of-range; the reviewer
applies more overrides; runaway loop.

**Mitigation:**
1. The override is the human's authoritative voice (ADR-001 §2.1).
   If the human's polygon is genuinely correct and the
   expected_model is wrong, the FIX is to update expected_model
   (a separate deliberate action, §2.9), not to chase the
   fidelity score.
2. ADR-002 explicitly forbids auto-deriving overrides from
   expected_model values (§2.9). The cockpit never offers "snap
   polygon to expected_model bounds" as an action.
3. Cockpit chip from `expand_room_polygon` /
   `shrink_room_polygon` proposed_actions surfaces the producer's
   computed delta to the expected polygon — but as a hint, not a
   forced value. Human always confirms.
4. F0 gate's WARN trigger (§2.7) catches the runaway-loop case:
   if 5+ rooms have polygon overrides on a single run, the
   reviewer sees a WARN regardless of the score.

## 4. Slice 6 plan (derived from this ADR)

Out of scope for this ADR PR. Each slice ships as its own PR.

### Slice 6a — schema + apply layer (foundation)

**Goal:** the data plane works end-to-end. No UI surface yet.

**Touchpoints:**
- `cockpit/overrides.py`: extend `OVERRIDE_TYPES` (§2.2), add
  validation branch (§2.4), update `_PRECEDENCE_ORDER`
- `tools/apply_overrides.py`: new apply branch (§2.5), update
  `_overrides_metadata` to include `polygon_overrides_applied_count`
- `tools/fidelity/compare_generated_to_expected.py`: pass
  `polygon_overrides_applied_count` through to fidelity report
  metadata (one-line additive change)
- `tests/test_cockpit_overrides_polygon.py` (NEW): validation
  matrix (≥3 pts, simple polygon, area > 0, area-consistency,
  edit_method enum, soft warnings)
- `tests/test_apply_overrides_polygon.py` (NEW): round-trip
  apply tests + precedence with mark_suspect / reject /
  room_label
- `tests/test_fidelity_engine_polygon_override.py` (NEW): apply
  override → recompute → assert sub-scores move

**Acceptance:** I can hand-write a `review_overrides.json` with
a `room_polygon_override`, run `tools/apply_overrides.py`, and
see `polygon_pts`, `area_m2`, `_polygon_pts_original`,
`_area_m2_original`, `source: manual`, `_edit_method` all set
correctly on the room in `amended_observed.json`. Fidelity
engine in `apply_overrides=True` mode reports both pre/post
sub-scores + the new `polygon_overrides_applied_count` metadata.

**~25 new tests. ~120 LOC across 3 source files + 3 test files.**

### Slice 6b — chip promotion + text-area polygon entry UX

**Goal:** the cockpit Review tab can produce a
`room_polygon_override` two ways: from a producer chip
(`expand_room_polygon` / `shrink_room_polygon`) or from a manual
text-area edit (paste vertex list).

**Touchpoints:**
- `cockpit/proposed_actions.py`: chip handler for the two new
  expand/shrink action types — composes `original_polygon +
  delta_pts` into the new absolute polygon, computes
  `estimated_area_pts2` + `estimated_area_m2`, calls
  `save_override` with `edit_method="from_proposed_action"`
  and `from_proposed_action_id=<chip uuid>`
- `cockpit/app.py` Review tab: per-room "✏️ Edit polygon" button
  opens a Streamlit text-area where the human pastes a JSON
  vertex list; cockpit validates via §2.4 and shows soft
  warnings before save (`edit_method="manual_draw"`)
- `tools/propose_skp_actions.py`: implement the
  `expand_room_polygon` / `shrink_room_polygon` detection rules
  (currently the producer enumerates the types but emits zero
  of them — ADR-001 §2.6 is satisfied by enum, the detection
  logic was deferred). Detection rule: when fidelity report
  flags a room area-out-of-range warning, emit a chip with
  `delta_pts` derived from the difference between the room's
  bbox and the expected polygon's bbox (when expected_model
  is supplied)
- `tests/test_cockpit_proposed_actions_polygon.py` (NEW):
  chip-to-override round-trip
- `tests/test_propose_skp_actions_polygon.py` (NEW): producer
  emits chips on FP-012-style fidelity warnings

**Acceptance:** I can open the cockpit on `runs/_dogfood_e2e_2026_05_09/`,
see an `expand_room_polygon` chip on SUITE 01, click "Apply",
and have a `room_polygon_override` written with the producer's
delta absorbed.

**~30 new tests. ~250 LOC across cockpit + producer + tests.**

### Slice 6c — F0 surface + cockpit Pre-SKP pane

**Goal:** the F0 verdict and cockpit Pre-SKP pane surface
`manual_polygon_room_count` per §2.7.

**Touchpoints:**
- `scripts/smoke/smoke_skp_export.py` gate F0: count rooms with
  `_edit_method` set in amended_observed; emit
  `manual_polygon_room_count` + the new WARN trigger
- `cockpit/history_view.py`: read `manual_polygon_room_count`
  from `pre_skp_review_report.json`; add the "✏️ N room(s)
  with manual polygon edit" line under the existing Δ caption
- `tests/test_smoke_gate_f0_polygon_count.py` (NEW): F0 emits
  the new field; WARN trigger fires on the 5-point swing test
- `tests/test_history_view_polygon_count.py` (NEW): Pre-SKP
  pane renders the new line when count > 0

**Acceptance:** running the smoke harness on
`runs/_dogfood_e2e_2026_05_09/` after applying a
`room_polygon_override` produces a `pre_skp_review_report.json`
with `manual_polygon_room_count >= 1`; cockpit shows the line.

**~15 new tests. ~80 LOC.**

### Slice 6d — graphical polygon edit UX (deferred)

**Goal:** the human draws on the PDF underlay; cockpit captures
the SVG path; `edit_method="trace_pdf"`.

**Why deferred:** Streamlit's interactive SVG support is limited.
Either we add `streamlit-drawable-canvas` (new dep) or we wait
until Phase 3 (FastAPI + browser SPA — ADR-001 §2.9) where
SVG editing is native. Decision deferred until 6a–6c land and
get exercised on real reviews.

### Slice 6e — amended_consensus.json for SKP (deferred)

**Goal:** SKP exporter optionally reads
`amended_consensus.json` derived from `amended_observed.json`,
producing a `.skp` that reflects the overrides.

**Why deferred:** see §2.8. Requires SU-side geometric validation
on every overridden polygon. Defer until at least one real review
case has produced a `room_polygon_override` and the human asked
for it to flow through to SU.

## 5. Alternatives considered (and rejected)

### A. Three separate override types — `expand_room_polygon_override`, `shrink_room_polygon_override`, `redraw_room_polygon_override`

**Why rejected:** the apply semantics are byte-identical (replace
`polygon_pts`). The distinction is human ergonomics in the
cockpit, not a runtime behaviour. Three types triple the
`OVERRIDE_TYPES` enum surface and the apply-layer branches with
zero behavioural payoff. Captured the distinction via
`payload.edit_method` instead.

### B. Store `delta_pts` (relative) instead of `new_polygon_pts` (absolute)

**Why rejected:** delta-based storage requires the consumer to
re-derive the absolute polygon at apply time, and the result
depends on the original polygon — which means the override
becomes invalid the moment the detector changes how it draws
that room. Absolute polygons are stable across detector
revisions; if the reviewer wants the same polygon on a future
run, the override re-validates as long as the room id resolves
(ADR-001 §2.10.6 sha256 binding handles the binding).

The producer's `delta_pts` is still useful **as a chip
suggestion** (§2.1 from_proposed_action path), but the
authoritative override stores the absolute polygon.

### C. SKP-aware override (validate against SU geometry at write time)

**Why rejected:** would couple the cockpit to SU runtime.
Cockpit currently has zero SU dependencies (Streamlit + PIL +
shapely only). Adding SU validation at override-write time
breaks the "cockpit is offline-capable" property. Deferred to
Slice 6e (amended_consensus.json) and behind an explicit
opt-in CLI flag.

### D. Auto-derive `room_polygon_override` from `expected_model` when fidelity is bad

**Why rejected:** **catastrophic safety violation.** Auto-syncing
the observation to the ground truth permanently breaks fidelity
as a measurement. Hard-forbidden by §2.9 of this ADR and
ADR-001 §2 invariants.

### E. Skip ADR — extend `cockpit/overrides.py` directly with a quick patch

**Why rejected:** `room_polygon_override` touches schema, apply
layer, fidelity report, F0 verdict, cockpit UI, AND has 4
distinct risk vectors. Per `docs/adr/README.md` promotion rule:
"The decision affects >1 file or >1 future PR's semantics ⇒ ADR".
Skipping the ADR would mean re-discovering the constraints in
the apply-layer PR, the F0 PR, and the UI PR independently and
potentially shipping inconsistent contracts.

## 6. Consequences

### Positive

- The most common dogfood failure mode (room polygon area
  out-of-range, FP-012 family) gains a first-class override path.
- Producer-side `expand/shrink_room_polygon` proposed_actions
  (currently spec-only, no producer logic) get a consumer to
  apply them — closing the half-loop ADR-001 §2.6 left open.
- Override-aware fidelity surface (Slices 5a–5d) extends naturally
  to polygon edits without a schema bump.
- Cockpit's review loop becomes complete enough to onboard a
  real reviewer on `planta_74` — the dogfood UX gap that blocked
  "deploy to Felipe" closes.

### Negative / costs

- `OVERRIDE_TYPES` grows from 7 → 8.
- `tools/apply_overrides.py` gains one new branch + 3 new
  per-room fields in amended_observed schema.
- F0 verdict gains one new field + one new WARN trigger.
- Cockpit Review tab gains a polygon-edit text-area + chip
  handler for two new chip types.
- Producer (`tools/propose_skp_actions.py`) gains two new
  detection rules.
- ~70 new tests across Slices 6a–6c.
- Slice 6d (graphical edit) and 6e (SKP exporter consumes
  overrides) explicitly punted.

### Reversibility

- **Slice 6a alone:** revert by deleting the new branch from
  `tools/apply_overrides.py`, removing the entry from
  `OVERRIDE_TYPES`, and reverting validation. Existing
  `review_overrides.json` files with `room_polygon_override`
  entries become "unknown type" and are skipped at apply
  (precedence walk falls through). No data loss.
- **Slice 6b alone:** revert by removing the chip handler +
  text-area UI. Manual hand-editing of JSON still works (Slice
  6a layer remains).
- **Slice 6c alone:** revert by removing the F0 emission + the
  cockpit pane line. The underlying data still exists in
  amended_observed; the surface just goes silent.
- **Schema:** `review_overrides_v1` is unchanged. Forward-
  compatible with older readers (they ignore the new type).
- **Worst-case full revert:** delete the override entries from
  `review_overrides.json`. The audit_trail still records the
  delete events. Originals are immutable, so no consensus
  damage.

## 7. Rollback procedure

If the contract proves wrong after Slice 6a ships:

1. Stop offering the polygon-edit UI in cockpit (Slice 6b
   revert) — `room_polygon_override` becomes hand-only.
2. If the apply-layer behaviour is wrong (e.g., scoring is
   inflating in production), revert Slice 6a:
   - Remove the `room_polygon_override` branch from
     `tools/apply_overrides.py`
   - Remove from `OVERRIDE_TYPES` enum
   - Existing override files become inert (their entries are
     skipped at apply time, but the file remains for audit)
3. If fidelity-side honest reporting is broken (e.g.,
   `polygon_overrides_applied_count` not surfaced), revert
   Slice 5b/5c was the predecessor and that path is well-
   exercised; the new field is purely additive.
4. Update ADR-002 status to "Superseded by ADR-003" with
   migration plan. Existing `review_overrides.json` files with
   v1 polygon overrides remain readable; they may need a
   manual re-confirmation (mirror ADR-001 §6 rollback step 3).

The contract is reversible because:
- No detector code reads polygon overrides (§2.8).
- No SKP exporter code reads polygon overrides (§2.8).
- `_polygon_pts_original` is always preserved (§2.5).
- `review_overrides_v1` schema is additive (§2.2).

## 8. Acceptance for this ADR

This ADR is mergeable when:

- [x] All 9 Felipe-listed deliverables addressed:
  - (1) ADR drafted before implementation
  - (2) No detector mutation
  - (3) No threshold tweaks to mask error
  - (4) No consensus mutation
  - (5) Implementation deferred to Slice 6
  - (6) Representation defined for: override type (§2.1),
    edit method (§2.1), confidence (implied via soft warnings
    §2.4), source (`edit_method` §2.1 + `source: manual` §2.5),
    audit trail (inherits ADR-001 §2.7 — append-only), fidelity
    relationship (§2.6), proposed_actions relationship (§2.1
    `from_proposed_action` + Slice 6b chip handler), F0 pre-SKP
    relationship (§2.7)
  - (7) Risks covered (§3 — 4 risks, 4 mitigations each grounded
    in §2 invariants)
  - (8) Slice 6 plan derived (§4 — 6a/6b/6c shippable, 6d/6e
    deferred with explicit reasons)
  - (9) PR opened via gh, mergeable when CI green
- [x] No surprise interaction with existing ADR-001 contract.
- [x] Future graduation path to expected_model is explicit and
  human-gated (§2.9).
- [ ] CI green on the docs PR.

## 9. References

- `docs/adr/ADR-001-validation-cockpit-mutation-surface.md` —
  parent contract; §2.6 expand/shrink proposed_actions, §2.10
  safety invariants this ADR inherits, §2.9 phased pipeline
  consumption (Slice 6a slots into Phase 2 alongside Slice 3)
- `docs/diagnostics/2026-05-09_dogfood_override_aware_flow.md` —
  source of UX gap #2 that motivates this ADR (§ "Gap #2 — v1
  override types don't address area / polygon issues")
- `cockpit/overrides.py` — `OVERRIDE_TYPES` enum + validation
  pattern this ADR extends additively
- `tools/apply_overrides.py` — apply layer (`opening_kind_override`
  branch is the template the new branch mirrors)
- `tools/propose_skp_actions.py` — producer where the new
  expand/shrink detection rules will live (Slice 6b)
- `tools/fidelity/compare_generated_to_expected.py` — fidelity
  engine; `apply_overrides=True` mode picks up polygon overrides
  for free via `room_score` / `bbox_score`
- `scripts/smoke/smoke_skp_export.py` gate F0 — surfaces
  `manual_polygon_room_count` (§2.7)
- `cockpit/history_view.py` — Pre-SKP Review pane (Slice 4-extra
  + 5d) extended with polygon-count line (§2.7)
- `.ai_bridge/DECISIONS.md` — pointer to this ADR
- `CLAUDE.md` §1 (safety rules), §2 (pipeline invariants), §3
  (the SketchUp Rule, especially "SketchUp is the final gate" —
  §2.8 of this ADR keeps SU exporter override-blind for v1)
