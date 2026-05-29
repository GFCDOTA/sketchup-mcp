# Visual Oracle — negative fixtures

Synthetic `geometry_report.json` + `consensus.json` pairs that are
**deliberately broken** in one specific way, so the deterministic
heuristics in `tools/run_skp_visual_review.py` can be asserted to
produce a `FAIL` verdict.

These are NOT full SKP builds — they're minimum-shape reports that
test the `inspect_report()` function. Honest scope: they prove the
**oracle reproves bad input**; they do NOT validate the builder.

## Fixtures

| Folder | Broken in | Expected finding(s) |
|---|---|---|
| `floating_door/` | `DoorLeaf_Group.bbox_m.min[2]` > 0.5m | `floating_door` |
| `orphan_glass/` | `WindowGlass_Group_<id>` with id not in consensus.openings | `orphan_glass_panel` |
| `full_height_window/` | `WindowGlass_Group.height_m` ≈ 2.7m + `bbox_m.min[2]` ≈ 0 | `bad_window_aperture` + `full_height_window_void` |

## How they are tested

See `tests/test_visual_oracle_negative_fixtures.py`:

```python
def test_floating_door_fixture_produces_fail():
    rep = load(neg / "floating_door/geometry_report.json")
    con = load(neg / "floating_door/consensus.json")
    findings = inspect_report(rep, con)
    assert any(f["type"] == "floating_door" for f in findings)
```

## Discipline

- These fixtures MUST stay synthetic (no full SKP build expected).
- Do NOT use them as training data for the visual oracle bridge —
  they exist for deterministic check assertions.
- If you add a new heuristic, add a corresponding negative fixture
  here that exercises it.
