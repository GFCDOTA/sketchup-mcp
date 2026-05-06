# SCHEMA-COHERENCE-REPORT.md — uncertainty-aware audit artifacts

> Versioned schemas for `coherence_report.json` and `questions.json`.
> Stage 1 of the audit pipeline (PR `feature/coherence-audit`).
> Both documents start at **schema_version `1.0`**.

## Scope

Stage 1 emits **two read-only artifacts** alongside any
`consensus_with_room_context.json` produced by
`tools.classify_openings_by_room_context`. Geometry is NOT touched;
the SKP exporter is NOT invoked; no LLM is called.

---

## 1. `coherence_report.json` (schema_version: "1.0")

Top-level keys (all required):

| Key | Type | Description |
|---|---|---|
| `schema_version` | string | `"1.0"` |
| `generated_at` | ISO-8601 string | UTC timestamp |
| `consensus_path` | string | Absolute path of the audited consensus |
| `consensus_sha256` | string | SHA-256 of the consensus file bytes |
| `assumptions` | object | Snapshot of the policy applied (see below) |
| `summary` | object | Aggregate counts |
| `facts` | array | One row per atomic observation |
| `hypotheses` | array | Per-opening alternatives + selected kind |
| `ambiguities` | array | Items routed to `decision == "ask"` |
| `drops` | array | Items routed to `decision == "drop"` |
| `issues` | object | Detected coherence problems (see below) |
| `risks` | array of strings | Free-form notes |

### `assumptions` object

```json
{
  "schema_version": "1.0",
  "goal": "furniture_layout",
  "risk_policy": "conservative",
  "ambiguity": {
    "drop_below": 0.20,
    "ask_above": 0.20,
    "debug_above": 0.50,
    "clean_above": 0.75
  },
  "source_path": "<repo>/config/assumptions.yaml"
}
```

### `summary` object

```json
{
  "openings_total": 11,
  "by_decision": {"clean": 7, "debug": 4},
  "by_kind": {
    "interior_door": 6, "interior_passage": 2,
    "window": 1, "glazed_balcony": 2
  }
}
```

### `facts[]`

Each entry is one of:
- `{"category": "wall", "id": "w001"}`
- `{"category": "room", "id": "r000", "name": "SUITE 02"}`
- `{"category": "opening", "id": "o010", "kind": "interior_door", "decision": "clean"}`

### `hypotheses[]`

```json
{
  "opening_id": "o010",
  "selected": "interior_door",
  "decision": "clean",
  "confidence": 0.91,
  "candidates": [
    {"kind": "interior_door", "prob": 0.91,
     "reason": "private pair, fits"},
    {"kind": "interior_passage", "prob": 0.10,
     "reason": "narrow"},
    {"kind": "window", "prob": 0.0, "reason": "no exterior"},
    {"kind": "glazed_balcony", "prob": 0.0, "reason": "no exterior"}
  ]
}
```

`candidates` is sorted by descending `prob`. `prob` is the confidence
that THIS kind is correct, given the same evidence. `selected` is the
kind currently in `consensus.openings[i].kind_v5`.

### `ambiguities[]`

```json
{
  "opening_id": "o007",
  "confidence": 0.45,
  "evidence": {
    "room_left": "SALA DE JANTAR", "room_right": "SUITE 01",
    "width_m": 1.16, "geometry_origin": "svg_arc",
    "wall_id": "w002", "wall_orientation": "h",
    "chord_recovered": false
  },
  "candidates": [...]
}
```

Only openings whose policy decision is `"ask"` appear here.

### `drops[]`

```json
{
  "opening_id": "o000",
  "confidence": 0.18,
  "evidence": {...},
  "reason": "room_context: BANHO 01 <-> SUITE 01"
}
```

Only openings whose policy decision is `"drop"` appear here. The
opening was already excluded from `consensus.openings` by the
classifier — this row preserves the audit trail.

### `issues` object

```json
{
  "floating_doors": [
    {"opening_id": "o099", "wall_id_claimed": "w_missing",
     "kind_v5": "interior_door"}
  ],
  "invalid_rooms": [
    {"room_id": "r050", "name": null,
     "reason": "polygon has 1 pts (<3)"}
  ],
  "duplicate_walls": [
    {"wall_a": "w000", "wall_b": "w000_dup",
     "orientation": "h"}
  ]
}
```

All three lists are detector outputs. They are **observational only**
in Stage 1 — they do NOT mutate consensus and do NOT block by default.

---

## 2. `questions.json` (schema_version: "1.0")

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-05-06T20:30:00Z",
  "consensus_path": "...",
  "consensus_sha256": "...",
  "questions": [
    {
      "id": "q-o007",
      "subject": "opening",
      "subject_id": "o007",
      "evidence": {...},
      "confidence": 0.45,
      "question": "Opening o007 between SALA DE JANTAR and SUITE 01...",
      "options": [
        {"id": "a", "label": "interior_door", "prob": 0.45},
        {"id": "b", "label": "interior_passage", "prob": 0.30},
        {"id": "c", "label": "window", "prob": 0.10},
        {"id": "d", "label": "glazed_balcony", "prob": 0.0},
        {"id": "x", "label": "drop_this_opening", "prob": null}
      ],
      "default_if_unanswered": "debug"
    }
  ]
}
```

`questions` is **non-empty only when** at least one opening had
`decision == "ask"`. Stage 1 does not consume answers; Stage 2 (a
later PR) will add `tools/answers.py` + an interactive resolver.

---

## CLI exit codes

`python -m tools.coherence_audit <consensus.json> [--strict]`

| Mode | Condition | Exit |
|---|---|---|
| default (no flag) | always, if inputs readable | `0` |
| `--strict` | clean (no fired blockers) | `0` |
| `--strict` | any blocker from `assumptions.strict_blockers` is present | `2` |

Default `strict_blockers` (see `config/assumptions.yaml`):

- `opening_decision_ask`
- `opening_decision_drop`
- `floating_door`
- `opening_without_host_wall`
- `invalid_room_polygon`
- `duplicate_or_overlap_walls`

---

## Stage 1 boundary (what this audit does NOT do)

- ❌ Mutate `consensus.walls`, `consensus.rooms`, or
  `consensus.openings` beyond the additive uncertainty contract.
- ❌ Generate or modify `model.skp`.
- ❌ Repair room polygons, merge collinear walls, or place doors.
- ❌ Call any LLM or external service.
- ❌ Write `answers.json` or run an interactive Q&A loop.
- ❌ Read user input from stdin.

These are deliberately deferred. Stage 2+ may build on this contract.

---

## Future versions

The contract above is `1.0`. Backward-compatible additions (new
fields, new candidate kinds) keep the version. Breaking changes
(removed fields, semantic shifts in confidence calculation, decision
routing changes) bump to `2.0` and require a migration path in
`tools.assumptions_loader` + `tools.coherence_audit`.

Last updated: 2026-05-06.
