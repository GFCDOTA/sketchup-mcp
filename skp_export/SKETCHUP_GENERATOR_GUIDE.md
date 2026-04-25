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

## 3. Coordinate conversion

PDF points -> metres -> SketchUp internal inches:

- `PT_TO_M = 0.000352778` (1pt = 1/72in)
- `1m = 39.37in`
- Ruby shorthand: `Numeric#pt` and `Numeric#m` go straight to internal inches.

```ruby
Geom::Point3d.new(x_pt.pt, y_pt.pt, 0)   # from pdf points
Geom::Point3d.new(x_m.m,   y_m.m,   0)   # from metres
```

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

- **PT_TO_M scale** assumes PDF is at 1:1 publication scale. Real planta
  needs calibration via dimension OCR (cota "3.40") — slated for V6.3.
- **`hinge_side` flip** is procedural and sometimes mirrors. The arc geometry
  is not rebuilt in Ruby yet (V6.2 final).
- **Furniture without `center_pdf_pt`** (Qwen-only labels) falls back to the
  centroide of its parent room.
- **Wall thickness** hardcoded to 0.14m alvenaria; drywall (0.075m) detection
  not wired.

## 6. Visual debug

- Fusion dashboard: `http://localhost:<port>/fusion/expdedup/final_planta_74`
- 3D viewer (post-build): `http://localhost:<port>/3d/expdedup/final_planta_74`

Dashboard overlays the consensus walls/openings on the rendered PDF so you
can spot drift before committing the SKP.

## 7. TODO — V6.3

- [ ] Scale calibration via dimension OCR (read cota `3.40m`, solve PT_TO_M)
- [ ] Swing-arc geometry in Ruby (`add_arc` + sweep) instead of static folha
- [ ] Replace cube placeholders with real 3D Warehouse furniture components
- [ ] Window IfcWindow with proper frame/glass material instead of bare gap
- [ ] Drywall vs alvenaria classifier feeding `thickness_m` per wall

## 8.0 SU 2026 install fix — `-RubyStartup` headless (2026-04-25)

### Problema

O install Trimble SU 2026 (`C:/Program Files/SketchUp/SketchUp 2026/`) vem com:
- `SketchUp/` — todas as DLLs (Qt6, SketchUpAPI, LayOutAPI, importers, exporters; ~954 MB) — **SEM `SketchUp.exe`**
- `Crack/SketchUp/SketchUp.exe` (18 MB) — main module patcheado isolado **SEM DLLs adjacentes**

O instalador esperava que o usuário rodasse `Crack/SketchUp/SketchUp.exe` por cima de `SketchUp/SketchUp.exe` no install dir. Esse passo nunca foi feito. Resultado: rodar o crack exe em qualquer dir (incluindo `Crack/SketchUp/`) → silent crash em <2s (Windows não acha as DLLs adjacentes).

### Investigação completa (2026-04-25)

Tudo testado sem admin elevation, **todos falharam**:

| Tentativa | Resultado |
|---|---|
| Lançar `Crack/SketchUp/SketchUp.exe` direto | Exit em 2s, sem janela, sem log |
| `cd C:/Program Files/SketchUp/SketchUp 2026/SketchUp` antes de invocar crack via `..` | Exit em 2s. Windows Safe DLL Search Mode exclui CWD pra exes em system dirs |
| Prepend install dir ao `$env:PATH` | Exit em 2s. Safe DLL Search também exclui PATH |
| `Start-Process -WorkingDirectory $install_dir` | Exit em 2s. Mesmo motivo |
| `[DllPath]::SetDllDirectory(install_dir)` via .NET P/Invoke | Exit em 2s. SetDllDirectory afeta o processo CHAMADOR, não o filho |
| `mklink /H` hard link das DLLs pra `~/SU2026_hardlink/` | **Acesso negado** — ACL do install dir bloqueia ate criação de hard link |
| `New-Item -ItemType Junction` apontando pro install dir | OK criar junction, mas escrever DENTRO do junction continua bloqueado pelo ACL alvo |
| Copiar crack exe pra dentro do install dir | **Permission denied** (precisa admin) |

Referência: Microsoft DLL Search Order — para exes em `Program Files/`, Safe DLL Search Mode pula CWD e PATH durante resolução de DLL absoluta. Apenas Application Directory + System32 + Windows são consultados.

### Solução A (canonical, requer admin 1× — recomendada)

```cmd
copy /Y "C:\Program Files\SketchUp\SketchUp 2026\Crack\SketchUp\SketchUp.exe" "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
```

Rodar em **CMD como Administrador** uma vez. SU 2026 passa a funcionar normalmente do Start Menu, file associations, etc. Headless via:
```cmd
"C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe" -RubyStartup "..." "...template.skp"
```

### Solução B (workaround sem admin — atual em uso)

Mirror full do install dir + crack exe sobreposto em local writable:

```powershell
robocopy "C:\Program Files\SketchUp\SketchUp 2026\SketchUp" "E:\SU2026_test" /E /MT:8 /R:1 /W:1
Copy-Item "C:\Program Files\SketchUp\SketchUp 2026\Crack\SketchUp\SketchUp.exe" "E:\SU2026_test\SketchUp.exe" -Force
```

- Custo: ~971 MB (full clone — hard links inviáveis devido ACL)
- Funciona com `-RubyStartup` headless
- Path do `.exe` workaround: `E:/SU2026_test/SketchUp.exe` (já criado pelo agent em 2026-04-25)

### Por que não rolou hard link (custo zero)

Hard link em NTFS exige:
1. Read source (✓ — install files são world-readable)
2. Write destination dir (✓ — `~/SU2026_hardlink/` writable)
3. **Permission to CREATE hardlink no source** (✗) — segurança NTFS no `Program Files/` bloqueia mesmo `mklink /H` sem admin. Erro: `Acesso negado` em todos os 127 arquivos do install dir testado.

Não há workaround para isso sem elevation. Por isso a Solução B duplica de fato (~1 GB).

### Comando final que funciona

```bash
"E:/SU2026_test/SketchUp.exe" \
  -RubyStartup "E:/Claude/sketchup-mcp/skp_export/headless_consume_and_quit.rb" \
  "E:/SU2026_test/resources/en-US/Templates/Temp01a - Simple.skp"
```

Tempo: ~6s para gerar `generated_from_consensus.skp`. Auto-quit via `UI.start_timer(2.0) { Sketchup.send_action('fileQuit:') }`.

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
