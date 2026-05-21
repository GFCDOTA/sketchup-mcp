# Harness Engineering — `tools/spec_harness.py`

> Companion to `spec_driven_development.md`. Describes how the
> evaluator works, the supported rule types, and how to extend it
> without breaking existing specs.

## What the harness does

`tools/spec_harness.py` takes a bundle of inputs:

  - one or more spec YAMLs (path or glob);
  - a consensus JSON (optional — only required by rules that read it);
  - a fidelity report JSON (optional — only required by rules that read it);
  - a geometry-invariants report JSON (optional — only required by rules that read it).

For each contract in each spec, it executes the rule, records the
result, and emits a single `spec_harness_report.json`. The exit
code is:

  - `0` if every `critical` contract passes;
  - `1` if any `critical` contract fails;
  - `0` if `warn` contracts fail (they're surfaced but don't break the
    build).

The exit code contract is intentional: the harness can be wired into
a CI job that promotes only when criticals are clean, without
becoming a `warn`-storm gate that fights with operators who are
actively triaging soft-barrier classifications.

## Invocation

```
python -m tools.spec_harness \
  --spec specs/planta_74/rooms.spec.yaml \
  --spec specs/planta_74/openings.spec.yaml \
  --consensus runs/planta_74_plan_shell/consensus_after.json \
  --fidelity-report runs/.../fidelity_report.json \
  --invariants-report runs/.../geometry_invariants_report.json \
  --out runs/.../spec_harness_report.json
```

Multiple `--spec` flags accumulate; the report aggregates contracts
across all loaded specs. Missing input files are tolerated when the
rule under evaluation doesn't need them; rules with missing required
inputs return `skip` and do NOT count toward critical-pass.

## Report schema

```json
{
  "schema_version": "1.0.0",
  "tool": "spec_harness",
  "specs_loaded": ["specs/planta_74/rooms.spec.yaml", ...],
  "inputs": {
    "consensus": "...",
    "fidelity_report": "...",
    "invariants_report": "..."
  },
  "contracts": [
    {
      "spec_path": "specs/planta_74/rooms.spec.yaml",
      "id": "rooms-no-merged-as-tt",
      "severity": "critical",
      "rule_type": "no_merged_room_names",
      "verdict": "fail",
      "evidence": {
        "matched_rooms": ["A.S. | TERRACO SOCIAL | TERRACO TECNICO"],
        "forbidden_substrings_hit": ["A.S. | TERRACO"]
      },
      "message": "1 merged room name(s) violate forbidden_substrings"
    }
  ],
  "summary": {
    "total": 14,
    "pass": 11,
    "warn": 2,
    "fail": 1,
    "skip": 0,
    "critical_fail": 1,
    "verdict": "fail"
  }
}
```

`evidence` is rule-type-specific. The harness writes whatever the
rule's evaluator returns, so an operator reading the report can see
WHY a contract failed without re-running the pipeline.

## Supported rule types

The MVP set covers the four spec files shipped with this PR.
Adding a new type requires (a) a new branch in `_evaluate_rule`, (b)
a unit test, and (c) documentation here.

### `no_merged_room_names`

```yaml
rule:
  type: no_merged_room_names
  forbidden_substrings:
    - "A.S. | TERRACO"
    - "SALA DE JANTAR | SALA DE ESTAR"
```

Reads `consensus.rooms[].name`. Fails if any room name contains any
of the listed substrings. Designed for the planta_74 r001 / r002
merge case: a room name with `" | "` is the harness signal that
polygonize couldn't separate two architectural ambients.

### `expected_room_names`

```yaml
rule:
  type: expected_room_names
  required:
    - A.S.
    - TERRACO SOCIAL
    - TERRACO TECNICO
    - SUITE 01
```

Reads `consensus.rooms[].name`. Fails if any required name is
missing. Use to assert "every named room from the source PDF must
survive to the consensus."

### `room_area_range`

```yaml
rule:
  type: room_area_range
  ranges:
    - { name: "SUITE 01", min_m2: 10.0, max_m2: 28.0 }
    - { name: "A.S.",     min_m2: 2.0,  max_m2: 4.0 }
```

Reads `consensus.rooms[].area_pts2` and converts to m² via the
calibrated `PT_TO_M = 0.19 / 5.4`. Fails if any named room's area
falls outside the documented range. Skips silently when the named
room doesn't exist (use `expected_room_names` to catch absence).

### `soft_barriers_protected_count`

```yaml
rule:
  type: soft_barriers_protected_count
  min: 2
  semantic_keywords: [peitoril, mureta, guarda]
```

Reads `consensus.soft_barriers`. Fails if fewer than `min` barriers
carry a semantic origin (geometry_origin = human_annotation, OR
barrier_type matches one of the keywords, OR the id/name/label
includes one of the keywords). Catches the failure mode "all
semantic peitoris were reclassified or deleted as wall_coincident
noise."

### `door_leaf_proximity`

```yaml
rule:
  type: door_leaf_proximity
  max_distance_m: 1.0
```

Reads `consensus.openings` and the geometry-invariants report's
DoorLeaf group bbox centers. Fails if any DoorLeaf's bbox center
sits more than `max_distance_m` from its host opening's declared
center. Mirrors `test_door_leaf_stays_near_its_opening_center` —
the FP-015 regression test — but extends to any planta with
populated openings + invariants.

### `room_has_door`

```yaml
rule:
  type: room_has_door
  rooms_requiring_door:
    - BANHO 01
    - BANHO 02
    - LAVABO
    - SUITE 01
    - SUITE 02
```

Reads `consensus.rooms[]` and `consensus.openings[]`. For each
listed room, checks whether at least one opening's
`adjacent_rooms` (or fallback heuristic: opening center inside the
room polygon's buffered hull) places it on the room's perimeter.
Fails for any room with zero qualifying openings. The "bathroom
without a door" sanity check.

### `evidence_pack_present`

```yaml
rule:
  type: evidence_pack_present
  required_artifacts:
    - original_floorplan.png
    - skp_render.png
    - overlay_pdf_skp.png
    - diff_walls.png
```

Reads the `--evidence-dir` argument (path on disk). Fails if any
listed artifact is missing or zero-bytes. Mirrors the
visual-fidelity-gate protocol's 7-artifact contract — the spec
can opt into a subset.

### `fidelity_axis_pass`

```yaml
rule:
  type: fidelity_axis_pass
  axes:
    - walls
    - rooms
    - openings
  min_score: 0.85
```

Reads the fidelity report's `per_axis[axis].score` and
`per_axis[axis].verdict`. Fails if any named axis is below
`min_score` or has verdict `FAIL`. Skips silently when the axis
isn't present (so spec stays forward-compatible with future axes).

## Adding a new rule type

1. Append a `_rule_<your_name>` function to `tools/spec_harness.py`.
   Signature: `(rule_body: dict, ctx: HarnessContext) -> RuleResult`.
2. Register it in `_RULE_DISPATCHERS`.
3. Add a unit test in `tests/test_spec_harness.py` covering:
   - rule returns `pass` on a passing input;
   - rule returns `fail` on a failing input;
   - rule returns `skip` when required input is missing;
   - rule's evidence dict captures enough to diagnose.
4. Update this doc — append a sub-section under "Supported rule types".

## Failure modes the harness must NOT hide

- **YAML loading errors**: a malformed spec must FAIL the harness
  with exit 1, not silently skip the spec. The harness reports
  `verdict: error` for the spec_path and exits 1.
- **Unknown rule types**: same — fail loudly. A spec referencing a
  rule type that no evaluator handles is a programming error in the
  spec, not a license to ignore the contract.
- **Required input missing**: the harness reports `verdict: skip`
  for contracts whose required inputs aren't supplied. Skip does NOT
  satisfy a critical contract — `critical+skip` still counts as
  unresolved.

## What the harness intentionally doesn't do

- **It doesn't write to consensus.** Read-only on every input.
- **It doesn't open SketchUp.** Spec evaluation is pure JSON / YAML.
- **It doesn't depend on `runs/`.** Inputs are explicit CLI arguments;
  the harness is fixture-driven and unit-testable.
- **It doesn't have a global config.** Every rule's parameters live
  in the spec YAML itself. The harness has zero per-planta knowledge.
- **It doesn't bypass the visual-fidelity-gate protocol.** When a
  spec uses `evidence_pack_present`, the gate's 7-artifact contract
  is the source of truth. The spec can require a subset; it cannot
  override the gate's policy.

## Where this is going

- **Phase 1 (this PR):** framework + planta_74 specs. The harness
  runs ad-hoc against checked-in fixtures.
- **Phase 2:** integrate into a non-blocking CI job that comments
  the spec_harness_report on PRs touching consensus / exporter.
- **Phase 3:** promote individual contracts to BLOCKING after a
  cooldown period (see Visual Fidelity Gate Protocol §3 — same
  pattern).
- **Phase 4:** extend to multi-planta fixtures + parametrize specs
  by planta. The `specs/_shared/` directory is reserved for
  cross-planta contracts.

This staging keeps the contract layer additive: at each phase the
harness produces more signal, but the existing pipeline keeps
shipping. No "big bang" cutover.
