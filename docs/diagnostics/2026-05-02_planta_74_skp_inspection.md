# Inspect report — `runs/vector/planta_74.skp`

**Inspected:** 2026-05-02 00:52, SketchUp 2026 (build 26.0.490 series)
**Source script:** `tools/inspect_walls_report.rb`
**Raw data:** `runs/vector/inspect_report.json` (~100 KB)

---

## Diagnóstico — o que produz o branco visível na planta

### 1. TRIPLICAÇÃO DE GEOMETRIA (causa primária dos "rastros brancos seguindo as paredes")

O `.skp` foi gerado executando `consume_consensus.rb` **3× no mesmo modelo sem `model.entities.clear!`** entre runs.

Evidências:

| Material | Cor | Faces | Origem |
|---|---|---|---|
| `wall_dark`  | [78,78,78] | 198 | run 1 |
| `wall_dark1` | [78,78,78] | 198 | run 2 (auto-renamed) |
| `wall_dark2` | [78,78,78] | 198 | run 3 (auto-renamed) |
| `room_r000..r010` | palette | 11 | run 1 |
| `room_r1..r11`    | palette | 11 | run 2 |
| `room_r12..r22`   | palette | 11 | run 3 |

`Sketchup::Model#materials.add(name)` retorna existente se nome bate; o consume usa nomes fixos e o método **renomeia silenciosamente para `<name>1`, `<name>2`** quando colidem — sintoma clássico de re-execução sem limpar.

**Wall groups:** 99 = 33 walls do consensus × 3 builds. Cada `w000` aparece **3×** no mesmo bbox.

**Wall overlaps detectados (top 5, todos auto-overlap por triplicação):**
```
w002 vs w002  vol=425025 in³  bbox=534×7.5×106
w002 vs w002  vol=425025 in³  (mesmo par, outras combinações da tripleta)
w002 vs w002  vol=425025 in³
w031 vs w031  vol=316920 in³  bbox=7.5×398×106
w031 vs w031  vol=316920 in³
```
425025 in³ ≈ 6.96 m³. Walls coincidentes mas com offsets sub-pixel (pdf_pt_to_su_pt arredondamentos diferentes em cada run) → **z-fighting / faixas brancas finas seguindo cada parede**. É exatamente o que você circulou em vermelho.

### 2. PARAPETS SEM MATERIAL (994 faces brancas)

`add_parapet()` em `consume_consensus.rb:97-119` extruda mas **não pinta**:
```ruby
face.pushpull(PARAPET_HEIGHT_IN)   # ← sem face.material = nada
```

Resultado: cada parapet vira um pequeno prisma com 5 faces visíveis default-white.

| Classificação | Count | Where |
|---|---|---|
| `parapet_side_default` | **583** | laterais verticais (4 por parapet) |
| `parapet_top_default`  | **411** | tampa horizontal |

Multiplicado por 3 builds. Parapets aparecem no terraço (peitoril 1.10m).

### 3. FLOOR WHITESPACE (146 faces)

`floor_face_no_material` — z=0, normal=(0,0,-1), parent_chain=[]. Áreas onde nenhum room polygon foi gerado pelo polygonize, ficam só com a edge-induced face do SU sem material.

### 4. RESÍDUO DE TEMPLATE — figura humana "Sree"

| Tipo | Detalhe |
|---|---|
| ComponentInstance | name="" def="Sree" bbox=[-39.9, -49.9, -0.05, 9.9, -0.1, 62.68] (em inches) |
| 17 materials `Sree_*` | Hair, Watch_1..3, Dress_1..4, Shoes_1..4, Pearls_1..2, Laptop_1..3, Complexion_1..3, Nails_4 |
| 87 faces totais com materials Sree_* | usadas pela figura |

A figura `Sree` é a personagem padrão do **template "Architectural"** do SU2026 (o mesmo template detectado pelo `sketchup_metadata_extractor`). O `consume_consensus.rb` **não limpa o template default antes de construir**, então a figura fica solta na origem (-40,-50,0) — invisível na vista iso porque está fora do bbox da planta, mas pesa no modelo.

---

## Inventário

| | Valor |
|---|---|
| `groups` (root) | 100 (99 wall_volume + 1 unnamed) |
| `components` | 1 (Sree) |
| `faces` (todas) | 1855 |
| `materials` | 57 |
| `layers` | 1 (`Layer0`) |
| `default_faces_count` | 1140 (61% do total) |

**Layers:** apenas `Layer0`. Nenhum tag/layer customizado pelo consume — toda geometria fica no layer default. Isso impede usar tag visibility pra esconder triplicatas.

---

## Recomendações

**Fix imediato no `tools/consume_consensus.rb`:**

1. **Limpar modelo no início do `main`** (mata triplicação E figura Sree):
   ```ruby
   model.entities.clear!
   model.definitions.purge_unused
   model.materials.purge_unused
   ```
   Coloca antes do `model.start_operation` ou logo depois.

2. **Pintar parapets** em `add_parapet`:
   ```ruby
   face.pushpull(PARAPET_HEIGHT_IN)
   parapet_group = ...   # envolver num grupo nomeado também
   parapet_group.entities.grep(Sketchup::Face).each do |fc|
     fc.material = parapet_mat   # criar mat com PARAPET_RGB que já existe na constante
     fc.back_material = parapet_mat
   end
   ```

3. **Tag/layer** por categoria — facilita debug e isola triplicatas se acontecerem de novo:
   ```ruby
   walls_layer = model.layers.add('walls')
   wall_group.layer = walls_layer
   ```

4. **Floor whitespace**: gerar uma "background floor face" cobrindo o `planta_region` do consensus com material neutro, pra eliminar as áreas brancas onde rooms não chegam. Ou — melhor — investigar por que o polygonize tá deixando zonas sem room.

**Validação pós-fix:** rodar `tools/inspect_walls_report.rb` de novo, confirmar:
- `materials` count em torno de 12 (1 wall_dark + 1 parapet + 11 rooms, sem `wall_dark1/2`)
- `wall_face_default(in_wall_group)` = 0
- `parapet_*_default` = 0
- `wall_overlaps_top20` = []
- ComponentInstances = 0

---

## Como reproduzir a inspeção

Plugin `~/AppData/Roaming/SketchUp/SketchUp 2026/SketchUp/Plugins/autorun_inspector.rb` lê `autorun_inspector_control.txt` (3 linhas: skp, report.json, script.rb), roda `inspect_walls_report.rb` 5s após boot via `UI.start_timer`. Sem matar SU. JSON em `INSPECT_REPORT`.

```bash
# trocar alvo
echo "PATH/to/other.skp
PATH/to/other_report.json
E:/Claude/sketchup-mcp/tools/inspect_walls_report.rb" > ~/AppData/Roaming/SketchUp/SketchUp\ 2026/SketchUp/Plugins/autorun_inspector_control.txt

# lançar SU com o skp positional
"C:/Program Files/SketchUp/SketchUp 2026/SketchUp/SketchUp.exe" PATH/to/other.skp
# JSON aparece em ~6s
```
