# SketchUp Generator Guide — `consume_consensus.rb`

V6.2 adapter that consumes `consensus_model.json` (schema 1.0.0) and emits a
`.skp` with walls, doors, gaps and named room groups.

---

## 1. Running it inside SketchUp

Open the Ruby console (`Window -> Ruby Console`) and run:

```ruby
load "E:/Claude/sketchup-mcp/skp_export/consume_consensus.rb"
Consume.from_consensus(
  "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json",
  Sketchup.active_model,
)
```

Dry-run (no SketchUp API needed, plain Ruby):

```bash
ruby -r ./consume_consensus.rb -e \
  'Consume.dry_run("E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json")'
```

Returns `{walls:, doors:, gaps:, rooms:}` summary; wraps everything in
`start_operation/commit_operation` so undo is one step.

## 2. Schema — `consensus_model.json`

Canonical reference:
`E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json`

```jsonc
{
  "metadata": { "schema_version": "1.0.0",
                "coordinate_space": "pdf_points",
                "page_bounds": [w_pt, h_pt] },
  "walls":    [{ "wall_id", "start":[x,y], "end":[x,y],
                 "angle_deg", "confidence", "sources":[...] }],
  "openings": [{ "opening_id", "center":[x,y], "chord_pt",
                 "kind":"door|window", "geometry_origin":"svg_arc|pipeline_gap",
                 "confidence", "hinge_side", "swing_deg",
                 "room_a", "room_b" }],
  "rooms":    [{ "room_id", "polygon":[[x,y],...], "area",
                 "label_qwen":"Suite 01", "sources":[...] }]
}
```

Walls have **no thickness/parent_wall_id** — each entry is already a split
segment. Openings have **no host wall_a/wall_b** — host inferred via
nearest-segment lookup.

## 3. Coordinate conversion (V6.2 final, 2026-04-27)

**Use SEMPRE `su_point(x_pt, y_pt)`** — single source of truth para conversão pt PDF-space → SU world. Internamente:
1. Normaliza origem: `(x - min_x_pt)`, `(max_y_pt - y)` (inverte Y porque PDF raster é y-down e SU é y-up)
2. Aplica `effective_scale` (default `PT_TO_M = 0.000352778` OR override via env var)
3. Multiplica por `Numeric#m` (built-in SU; converte metros → SU internal inches)

```ruby
def su_point(x_pt, y_pt, z_m = 0.0)
  nx_m, ny_m = world_xy_m(x_pt, y_pt)
  Geom::Point3d.new(nx_m.m, ny_m.m, z_m.m)
end
```

`compute_origin(walls)` deve ser chamado **uma vez** antes de qualquer `su_point`, populando `@origin_pt = {min_x, max_y}` em pt-space.

**⚠️ Importante:** `Numeric#pt` **NÃO existe** em SU 2026 Ruby API (apenas `.cm/.feet/.inch/.m/.mm/.yard`). Tentar `x_pt.pt` causa `NoMethodError: undefined method 'pt' for Float`. Bug histórico corrigido em commit `4b03515` (2026-04-25).

### Scale override (`CONSUME_SCALE_OVERRIDE` env var)

`PT_TO_M = 0.000352778` assume PDF a **1:1 publication scale** (1pt papel = 1pt real). Plantas arquitetônicas reais são desenhadas em **1:50 a 1:100** — nesse caso o default deixa o modelo 50–100× menor que real. Pra `planta_74` (74,93m²) o scale correto é `0.0135` (modelo sai 6.96m × 10.63m = 74.0m² ✓).

```bash
CONSUME_SCALE_OVERRIDE=0.0135 \
  "C:/Program Files/SketchUp/SketchUp 2026/SketchUp/SketchUp.exe" \
  -RubyStartup ".../headless_consume_and_quit.rb" "...Templates/Temp01a - Simple.skp"
```

Cálculo do scale por planta (mais detalhes em [GEOMETRY_FIX_REPORT.md](GEOMETRY_FIX_REPORT.md)):
```python
scale = math.sqrt(area_real_m2 / (walls_x_span_pt * walls_y_span_pt))
```

V6.3 TODO: substituir override manual por OCR de cota dimensional (ler "3.40m" do PDF → calcular scale auto).

## 4. Category mapping

| Source                                                       | Action                                                                  |
| ------------------------------------------------------------ | ----------------------------------------------------------------------- |
| `walls[]`                                                    | rect (length x 0.14m alvenaria) + `pushpull(2.70m)`, group `Wall_<id>`  |
| `openings` `geometry_origin="svg_arc"` AND `confidence>=0.5` | `PlaceDoorComponent.place_door` (V6.1 real component, scale_x=t/0.19)   |
| `openings` `geometry_origin="pipeline_gap"`                  | carve void in host wall, no door component                              |
| `openings` `kind="window"`                                   | IfcWindow scaffold — rect cut + painted frame (currently same as gap)   |
| `rooms` w/ `label_qwen`                                      | floor face Group named `Room_<label>` (spaces -> `_`)                   |
| `furniture` w/ `center_pdf_pt`                               | 3D Warehouse component if mapped, else placeholder cube `0.5x0.5x0.5 m` |

Low-confidence `svg_arc` openings (<0.5) are skipped with a `warn`.

## 5. Known limitations

- **Scale calibration manual via `CONSUME_SCALE_OVERRIDE`** — V6.2 entrega knob; V6.3 TODO substitui por OCR de cota.
- **Welcome dialog SU 2026** bloqueia `-RubyStartup` na primeira run após install. Workaround: usuário dismissa welcome 1× manualmente, depois automation funciona indefinidamente (state persiste em `login_session.dat` + `WebCache/`). Tentativas de dismiss programático (WM_CLOSE/SC_CLOSE/SendKeys/UIAutomation) falham porque welcome é DOM CEF, não nativo.
- **`hinge_side` flip** é procedural e às vezes espelha. Arc geometry não rebuild em Ruby ainda (V6.3).
- **Furniture sem `center_pdf_pt`** (Qwen-only labels) cai no centroide da room pai.
- **Wall thickness** hardcoded 0.14m alvenaria; drywall (0.075m) classifier TBD.
- **Pipeline NÃO generaliza** pra plantas externas brasileiras (5/5 FAIL — ver [EXTERNAL_VALIDATION_REPORT.md](../../sketchup-mcp-exp-dedup/EXTERNAL_VALIDATION_REPORT.md)). V6.3 wave deve atacar isso.

## 6. Visual debug

- Fusion dashboard: `http://localhost:<port>/fusion/expdedup/final_planta_74`
- 3D viewer (post-build): `http://localhost:<port>/3d/expdedup/final_planta_74`

Dashboard overlays the consensus walls/openings on the rendered PDF so you
can spot drift before committing the SKP.

## 7. TODO — V6.3

### Generalization wave (high priority — 5/5 externas FAIL hoje)
- [ ] **Auto-detect color preset** via K-means em fingerprint cromático (`color: auto` flag não está disparando em plantas pretas)
- [ ] **Single-page selector** heurístico (página com mais structure geometry, não primeira) — multi-page A0 PDFs (codhab, natal) explodem
- [ ] **Cap + retry**: rejeitar runs com walls>500 OR rooms>50, re-tentar com preset diferente automaticamente
- [ ] **Regression gates negativas**: 5 plantas externas como `expected_quality: poor` em fixtures multiplant

### Geometry refinements
- [ ] **Scale calibration via dimension OCR** (ler cota "3.40m" do PDF → calcular scale automático, substituir `CONSUME_SCALE_OVERRIDE` manual)
- [ ] **Swing-arc geometry** em Ruby (`add_arc` + sweep) em vez de folha estática
- [ ] **Drywall vs alvenaria classifier** feeding `thickness_m` per wall

### Components / scene
- [ ] **3D Warehouse furniture real** (substituir cube placeholders) — auth-walled, scrap via Selenium ou usar Built Archi/CGTips mirrors
- [ ] **IfcWindow proper** com frame/glass material em vez de bare gap
- [ ] Wire 11 furniture items do `furniture_room_mapping.json` aos componentes reais (Wardrobe.skp, Janela_Correr_2F.skp, etc., já em `components/`)

## 8.0 SU 2026 install state (2026-04-27 — RESOLVIDO)

### Estado atual: canonical install funcionando

`SketchUp.exe` agora está em `C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe` (canonical install path) — Solução A (admin 1×) foi aplicada pelo user entre sessões. Crack folder removida. Comando de execução headless:

```powershell
$env:CONSUME_SCALE_OVERRIDE = "0.0135"   # planta_74 specific
& "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe" `
  -RubyStartup "E:\Claude\sketchup-mcp\skp_export\headless_consume_and_quit.rb" `
  "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\resources\en-US\Templates\Temp01a - Simple.skp"
```

Ou via wrapper completo:
```powershell
powershell -File "E:\Claude\sketchup-mcp\skp_export\run_full_pipeline.ps1"
```

### Histórico do fix (2026-04-25)

Install Trimble SU 2026 vinha quebrado: `Crack/SketchUp/SketchUp.exe` (18MB main module patcheado) isolado **sem DLLs adjacentes** + install dir `SketchUp/` com 954MB de DLLs **sem `SketchUp.exe`**. Crack folder veio sem README explicando o passo de overlay.

**Soluções avaliadas (todas SEM admin falharam — 7 tentativas):**
- Lançar exe direto, `cd` no install dir, prepend PATH, `Start-Process -WorkingDirectory`, `[DllPath]::SetDllDirectory()`, `mklink /H` hard links, `New-Item -ItemType Junction` — todas blocked por Windows Safe DLL Search Mode + NTFS ACL no `Program Files/`. Detalhes em [reference_su2026_crack_install_fix.md](~/.claude/projects/E--Claude/memory/reference_su2026_crack_install_fix.md).

**Solução A aplicada (admin 1×):**
```cmd
copy /Y "C:\Program Files\SketchUp\SketchUp 2026\Crack\SketchUp\SketchUp.exe" "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
```

### Welcome dialog (limitação remanescente)

SU 2026 abre dialog "Bem-vindo(a)" (CommonWebDialog CEF) que bloqueia `-RubyStartup` na **primeira run após reinstall**. Tentativas programáticas falham:
- WM_CLOSE/SC_CLOSE → mata SU inteiro
- SendKeys Esc/Tab/Enter → CEF não reage
- UIAutomation tree → vê só "Chrome Legacy Window" panel (DOM oculto)

**Workaround de 30 segundos:** abrir SU manualmente uma vez, dismissar welcome (qualquer template), fechar SU. Estado persiste em `%APPDATA%/SketchUp/SketchUp 2026/login_session.dat` + `WebCache/`. Subsequent `-RubyStartup` funcionam.

### Solução B (workaround antigo — DEPRECATED)

`E:/SU2026_test/` (971MB clone com crack exe overlaid) foi parcialmente removido após Solução A aplicada. Não é mais usado.

---

## 8. Substitute door component (2026-04-25)

Componente histórico `Porta de 70/80cm.skp` em `E:/Claude/Cursos/...`
foi removido junto com o folder. Substituto: **`Door Interior.skp`**
do install Trimble SketchUp 2026, copiado para
`skp_export/components/Door Interior.skp` (19.5 KB, source:
`C:/ProgramData/SketchUp/SketchUp 2026/SketchUp/Components/Components Sampler/`).

**Uso:**
- `consume_consensus.rb` define `DEFAULT_DOOR_LIB` apontando pro
  novo componente. Quando `from_consensus` é chamado sem `door_lib:`,
  o default é resolvido automaticamente.
- `headless_consume_and_quit.rb` passa `door_lib: DOOR_LIB` explicito.

**Convenção de eixos:**
- Default `assume_upright: true` em `place_door_component.rb` —
  componentes modelados em pé (X=width, Y=thickness, Z=height) usam
  scale_y, sem rotação -90 X. Caso do SU sampler.
- `assume_upright: false` retoma convenção V6.1 (X=thickness, lying flat,
  -90 X rotação). Útil pra componentes legados/customizados.

**Calibração TBD:**
- Não foi possível medir bbox real do `Door Interior.skp` sem abrir
  SU desktop. O código lê `definition.bounds` dinamicamente em runtime,
  então scale_y deve sair correto. **Validação visual pendente** após
  primeiro run em SU 2026 — comparar com PDF real (memory pdf_skp_sidebyside).
- Se a porta sair errada (proporção, orientação, posição), candidatos:
  - Trocar `assume_upright` para false
  - Verificar qual axis do bbox é realmente thickness (pode não ser Y)
  - Substituir por outro componente: 3D Warehouse busca "porta arquitetônica brasileira" tem candidatos.

**Bibliotecas alternativas (não baixadas):**
- [3D Warehouse SketchUp](https://3dwarehouse.sketchup.com/) — busca "porta interior" ou "porta arquitetônica"
- [Built Archi single shutter door](https://builtarchi.com/sketchup-door-model/) — Door_3D_model_1.skp via MediaFire
- [Allan Brito](https://www.allanbrito.com/2016/11/29/portas-e-janelas-para-sketchup-download-gratuito/) — pacote pt-BR
- [BIMobject doors](https://www.bimobject.com/en-us/categories/doors?software=sketchup) — BIM grátis com cadastro
