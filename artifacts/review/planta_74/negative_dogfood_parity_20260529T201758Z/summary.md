# Negative dogfood — `planta_74` (production-parity)

## Generated: 2026-05-29T20:18:19Z

**Defect injected:** `erase_top_exterior_wall_segment` (missing_wall_continuation) on `planta_74_top.png`, rect=(400, 92, 740, 122) filled with rgb=[191, 191, 198]. Only the top render (and the side-by-side built from it) is corrupted; iso + PDF + geometry context are identical between runs.

## Oracle verdicts (ollama_vision, full input set)

| Render set | status | top_level | localized gap findings |
|---|---|---|---|
| clean | `ok` | `PASS` | 0 |
| corrupted | `ok` | `PASS` | 0 |

## Result: **NOT_DISCRIMINATED**

- primary (top-level worse, clean not already FAIL): **False**
- secondary (new localized gap finding): **False**

> Clean was acceptable but the oracle did NOT register the corrupted render as worse. Honest finding: on this defect the oracle is not discriminative. No verdict fabricated.

## Evidence

- `clean_top.png`, `corrupted_top.png`, `*_side_by_side.png`
- `clean/`, `corrupted/` (oracle raw/normalized or request package)
- `discrimination_report.json`
