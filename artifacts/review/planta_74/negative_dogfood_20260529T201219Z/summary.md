# Negative dogfood — `planta_74`

## Generated: 2026-05-29T20:12:46Z

**Defect injected:** `erase_top_exterior_wall_segment` (missing_wall_continuation) on `planta_74_top.png`, rect=(400, 92, 740, 122) filled with rgb=[191, 191, 198].

## Oracle verdicts (ollama_vision, top render only)

| Render | status | verdict |
|---|---|---|
| clean | `ok` | `FAIL` |
| corrupted | `ok` | `FAIL` |

## Result: **NOT_DISCRIMINATED**

> The oracle did NOT rate the corrupted render worse. Honest finding: on this defect the oracle is not discriminative. No verdict fabricated.

## Evidence

- `clean_top.png`, `corrupted_top.png`
- `clean/`, `corrupted/` (oracle raw/normalized or request package)
- `discrimination_report.json`
