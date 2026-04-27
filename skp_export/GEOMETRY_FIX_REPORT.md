# Geometry Fix Report — V6.2 Coord Transform Centralization (2026-04-27)

## Diagnóstico final

`.skp` gerado vinha **deformado** (modelo de 5cm² pra planta de 74m²) por **3 bugs distintos**:

### Bug 1 — Origem não normalizada
Pontos pt do PDF (range x[121..1105] y[288..885]) iam direto pro SU world sem subtrair min_x/min_y. Modelo ficava off-origin no SU, e quando renderizado de top-view aparecia minúsculo no canto.

### Bug 2 — Y não invertido
PDF raster tem origem **top-left (Y cresce pra baixo)**. SU world tem origem **bottom (Y cresce pra cima)**. Sem inversão, planta saía espelhada verticalmente.

### Bug 3 — Mistura de unidades + escala 250× errada
Default `PT_TO_M = 0.000352778` (1pt = 1/72 inch ≈ 0.353mm) assume PDF a **1:1 publication scale** (papel = real). Plantas arquitetônicas reais são desenhadas em 1:50 a 1:100 (cada pt do papel representa 50× a 100× sua dimensão real).

**Evidência empírica** (planta_74.pdf, área real 74,93m²):
- Walls span pt: x[42..558] y[29..817] = 516 × 788 pt
- Com PT_TO_M default: bbox SU = **0.18m × 0.28m** (modelo de 5cm² — claramente errado)
- Com SCALE_OVERRIDE=0.0135 (calculado: `sqrt(74 / (516 × 788))`): bbox SU = **6.96m × 10.63m = 74.0 m²** ✓
- Door chord_m em SCALE=0.0135: **0.46m, 0.53m, 0.61m** — coerente com portas brasileiras 60-90cm

## Patch aplicado

### 1. Função única `su_point` (Single Source of Truth)
Toda conversão pt → SU world passa por uma única função:

```ruby
def su_point(x_pt, y_pt, z_m = 0.0)
  nx_m, ny_m = world_xy_m(x_pt, y_pt)
  Geom::Point3d.new(nx_m.m, ny_m.m, z_m.m)
end

def world_xy_m(x_pt, y_pt)
  s = effective_scale
  nx_m = (x_pt - @origin_pt[:min_x]) * s
  ny_m = (@origin_pt[:max_y] - y_pt) * s   # INVERT Y
  [nx_m, ny_m]
end
```

Aplicada em: `build_wall_su` (faces de wall), `build_room_su` (polygon de room), `placement_record` (center_m de door), `dry_run` (logs).

### 2. SCALE_OVERRIDE consistency
Todos os campos delta (não-coordenada) agora usam `effective_scale` em vez de `PT_TO_M` hardcoded:

| Campo | Antes | Depois |
|---|---|---|
| `length_m` (normalise_wall) | `length_pt * PT_TO_M` | `length_pt * effective_scale` |
| `chord_m` (normalise_opening) | `chord_pt * PT_TO_M` | `chord_pt * effective_scale` |
| `area_m2` (normalise_room) | `area_pt2 * PT_TO_M²` | `area_pt2 * effective_scale²` |
| `half_thick_pt` (build_wall_su) | `thickness / PT_TO_M` | `thickness / effective_scale` |

### 3. SCALE_OVERRIDE env var
```bash
CONSUME_SCALE_OVERRIDE=0.0135 ruby ... # ou setado externo via os.environ
```
Aplicado tanto em Ruby (`SCALE_OVERRIDE` constante na top do module) quanto em Python mirror.

### 4. Logs determinísticos pré-build
`compute_origin` agora loga:
```
walls_pt_range:    x[42..558] y[29..817]
origin_pt:         {min_x: 42.48, max_y: 817.32}
effective_scale:   0.0135  (CONSUME_SCALE_OVERRIDE active)
walls_world_range: x[0..6.96m] y[0..10.63m] (pos Y-invert)
```

E `headless_consume_and_quit.rb` loga `model.bounds` real após save — sanity check end-to-end.

## Como usar (pra planta_74)

```powershell
$env:CONSUME_SCALE_OVERRIDE = "0.0135"
"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe" `
  -RubyStartup "E:\Claude\sketchup-mcp\skp_export\headless_consume_and_quit.rb" `
  "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\resources\en-US\Templates\Temp01a - Simple.skp"
```

Ou via Python dry-run (não requer SU):
```bash
CONSUME_SCALE_OVERRIDE=0.0135 \
  "E:/Python312/python.exe" \
  "E:/Claude/sketchup-mcp/skp_export/consume_consensus_dryrun.py" \
  "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json"
```

## Calibração de scale por planta

Como cada planta tem escala arquitetônica diferente (1:50, 1:75, 1:100, etc.), o `SCALE_OVERRIDE` precisa ser calibrado por planta. Fórmula:

```python
import math
# pre-condições: rodar dry-run pra obter walls_pt_range
# pre-condições: saber área real da planta (do título do PDF, ou da planta de vendas)

walls_x_span_pt = max_x - min_x   # de walls_pt_range
walls_y_span_pt = max_y - min_y   # de walls_pt_range
area_real_m2 = 74.93               # da metadata do PDF

# Scale que mantém aspect ratio E entrega area aproximadamente correta:
scale = math.sqrt(area_real_m2 / (walls_x_span_pt * walls_y_span_pt))
print(f"CONSUME_SCALE_OVERRIDE={scale:.4f}")
```

V6.3 TODO: scale calibration via dimension OCR (`scripts/calibrate_scale.py` lendo cota "3.40m" do PDF).

## Arquivos modificados

- `skp_export/consume_consensus.rb` — `su_point` + `world_xy_m` + 4 fixes consistency + range logs
- `skp_export/consume_consensus_dryrun.py` — Python mirror em paridade total
- `skp_export/headless_consume_and_quit.rb` — log de `model.bounds` final

## NÃO modificado (out-of-scope)

- `skp_export/place_door_component.rb` — recebe `placement[:center_m]` já normalizado, funciona inalterado
- Extractor / topology / openings / classify — bug NÃO estava aqui
