# apê planta_74 furnished @0.0259 — furniture-canonical

## O que é
Apartamento INTEIRO mobiliado num único `.skp`, na escala correta do PDF
(`PT_TO_M=0.0259`), **com as separações dos ambientes (paredes do shell) + 78 móveis planejados**.

## Build
- Branch: `feat/furniture-canonical` (suite01-scale-gate integrada + sofá refinado enxertado).
- Escala: `PT_TO_M=0.0259` via `core/scale.py` (fonte única; `pt_to_in=1.0197`). Sem hardcoded.
- Shell: `scale_rebuild_0259_20260608/model.skp` (shell @0.0259 validado).
- Furnish: `tools/furnish_apartment.py` — **78/78** placeholders colocados.
- Sofá: refinado (encosto inclinado + bevel almofadas, commits `a7e75a1`+`a0f00d3`).

## Cômodos mobiliados (7)
| room | ambiente | móveis |
|---|---|---|
| r000 | SUITE 01 | 32 (cama, guarda-roupa, criados, tapete…) |
| r002 | SALA | 4 (sofá refinado + rack) |
| r003 | SUITE 02 | 30 |
| r004 | COZINHA | 6 (geladeira/pia/cooktop/bancada/torre/aéreo) |
| r005/r006/r007 | BANHO 01/02/LAVABO | 2 cada (bancada+vaso) |
| r001 | TERRAÇO | sem móvel planejado (skip) |

## Gates (determinístico)
- `repo_health_gate` PASS (0 scale-literal no código)
- `geometry_sanity` PASS @0.0259 (`test_suite01_scale_gate`: 4 passed)

## Repro
```
PT_TO_M=0.0259 FURNISH_BASE_SKP=<shell_0259>/model.skp \
  .venv/Scripts/python.exe tools/furnish_apartment.py
```

## Status
Determinístico VERDE. **PENDENTE: GPT VISUAL_REVIEW** (Suíte 01 / sala sofá / apê inteiro).
