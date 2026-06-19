# Kitchen Validation Report — r004 (COZINHA, planta_74)

- **Room**: r004 (KITCHEN), parede OESTE, layout LINEAR
- **Scale**: `PT_TO_M=0.0259`
- **Date**: 2026-06-19
- **Role**: VALIDATOR (no code edited)
- **Overall**: ALL 4 GATES PASS

## Commands

```
cd /e/Claude/apps/sketchup-mcp
PT_TO_M=0.0259 .venv/Scripts/python.exe -m tools.kitchen_validation r004
PT_TO_M=0.0259 .venv/Scripts/python.exe -m tools.geometry_sanity r004
PT_TO_M=0.0259 .venv/Scripts/python.exe tools/geometry_sanity.py r004
PT_TO_M=0.0259 .venv/Scripts/python.exe -m tools.furniture_overlap_gate r004
PT_TO_M=0.0259 .venv/Scripts/python.exe -m tools.kitchen_ergonomics r004
```

## Results

### 1. kitchen_validation => PASS
- sink_wall = LEFT
- sink_anchor_source = PDF_WEST_WALL  (pia FIXA na parede OESTE do PDF)
- sink_distance_to_left_wall = 1.2 in (~0 / encostado)
- sink_inside_kitchen = true
- sink_not_inside_AS = true
- fridge_inside_kitchen = true
- cooktop_inside_kitchen = true
- kitchen_door_clearance_ok = true
- modules_grouped_individually = true

### 2. geometry_sanity => PASS
- [PASS] r004 (KITCHEN) 22 tipos
- Confirmed via both `-m tools.geometry_sanity` and `tools/geometry_sanity.py` (exit 0 both)

### 3. furniture_overlap_gate => PASS
- [ok] COZINHA (12 móveis) — sem sobreposição de footprint no mesmo Z

### 4. kitchen_ergonomics => PASS (KITCHEN_DIMENSIONAL_AUDIT)
| Medida | Valor | Faixa | Status |
|---|---|---|---|
| countertop_height | 90.0 cm | 85-92 | PASS |
| toe_kick_height | 12.0 cm | 10-15 | PASS |
| base_depth | 60.0 cm | 55-60 | PASS |
| upper_depth | 33.0 cm | 30-35 | PASS |
| upper_clearance | 60.0 cm | 50-60 | PASS |
| hood_clearance | 55.0 cm | 45-65 | PASS |
| fridge_tower_width | 67.2 cm | 55-75 | PASS |
| fridge_vent_gap | 2.8 cm | 2-6 | PASS |
| base_module_width | 51.2 cm | 35-65 | PASS |
| upper_module_width | 50.4 cm | 35-65 | PASS |
| filler_width | 16.0 cm | 15-18 | PASS |
| sink_rim_height | 90.0 cm | 85-92 | PASS |
| sink_anchor_pdf | — | — | PASS |
| circulation | — | — | PASS |

## Notes
- Pia ancorada na parede OESTE do PDF (FIXA) — regra de posição respeitada.
- 12 móveis na cozinha, agrupados individualmente, sem overlap.
- 14/14 verificações ergonômicas dentro do padrão de planejado.
- Render flat = massa/material básico (sem V-Ray); veios de pedra, reflexo de inox e brilho de LED não aparecem no flat — não é regressão, é limite do render flat.
