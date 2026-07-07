# Negative dogfood — `planta_74` (production-parity)

## Generated: 2026-07-01T17:18:55Z

**Defect injected:** `erase_top_exterior_wall_segment` (missing_wall_continuation) on `planta_74_top.png`, rect=(500, 200, 900, 224) filled with rgb=[191, 191, 198]. Only the top render (and the side-by-side built from it) is corrupted; iso + PDF + geometry context are identical between runs.

## Oracle verdicts (`claude_bridge_vision`, full input set)

| Render set | status | top_level | localized gap findings |
|---|---|---|---|
| clean | `ok` | `PASS` | 0 |
| corrupted | `ok` | `WARN` | 1 |

## Result: **DISCRIMINATED**

- primary (top-level worse, clean not already FAIL): **True**
- secondary (new localized gap finding): **True**

> The oracle caught the injected missing-wall defect on the REAL fixture (worse top-level verdict and/or a new localized gap finding the clean run lacked).

## Evidence

- `clean_top.png`, `corrupted_top.png`, `*_side_by_side.png`
- `clean/`, `corrupted/` (oracle raw/normalized or request package)
- `discrimination_report.json`
