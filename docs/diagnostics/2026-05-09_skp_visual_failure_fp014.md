# FP-014 — SKP room polygon leakage / invalid floor surfaces

> **Status:** OPEN — bloqueia entrega de SKP utilizável.
> **Severidade:** Alta — F0 reportou PASS mas o SKP é visualmente
> inutilizável.
> **Aberto em:** 2026-05-09
> **Reportado por:** Felipe ao revisar `model.skp` em SU 2026.
> **Run que evidencia:** `runs/_milestone_skp_planta74_2026_05_09/`
> **commit:** `9df2fee` (develop tip post-PR #101)
> **Validação externa:** GPT-4o (2026-05-09) — confirma diagnóstico,
> rank de prioridade ajustado para A→C→B. Ver
> [`_gpt_validation.md`](2026-05-09_skp_visual_failure_fp014_gpt_validation.md).

## Sintoma

Ao abrir `model.skp` em SU 2026 ou inspecionar a render top
(`preview_top.png`), os pisos/rooms apresentam:

- **SUITE 01** (verde claro) vaza pelo lado direito, formando um
  "triângulo gigante verde" que atravessa atrás de BANHO 02 e por
  baixo de BANHO 01 — o floor passa POR DEBAIXO das walls (Z-overlap)
- **SALA DE ESTAR / SALA DE JANTAR** fundidas por uma diagonal
  (sem wall divisória reconhecida)
- **COZINHA** com corte triangular esquerdo (fold artifact)
- **TERRACO TECNICO** sliver minúsculo (1.59 m² vs ~10 esperado)
- Alguns trechos do envelope (lado esquerdo da torre) ficam SEM
  floor preenchido — só walls + soft_barriers
- **Walls orphans/flutuando** dentro de COZINHA e centro do envelope
  (3-5 wall blocks isolados sem conexão a outros walls)
- **Portas (marrons) flutuando** dentro de gaps das walls como faces
  planas separadas (swing leafs renderizados isolados)

**Resumo (3 famílias de defeitos):**
- **(A) floor polygon vazando** — origem em `rooms_from_seeds` (738 vts em SUITE 01, raster contour trace)
- **(B) wall fragments curtos** — origem em `extract_openings_vector` carving agressivo (14/33 walls < 1m)
- **(C) opening misplacement / width undershoot** — origem em `extract_openings_vector` (10/17 gaps colineares sem opening; janelas/peitoris medidos como fragmento de gap em vez de abertura inteira)

## Artefatos visuais

- `2026-05-09_skp_visual_failure_fp014_top.png` — render top-down
  da consensus (mesma forma que SU mostra como floor surfaces)
- `2026-05-09_skp_visual_failure_fp014_axon.png` — axon 3D
  pré-renderizado da consensus
- `2026-05-09_skp_visual_failure_fp014_sidebyside.png` — PDF | SKP
  top | SKP axon
- **`2026-05-09_skp_visual_failure_fp014_su_screenshot.png`** —
  screenshot real do SU 2026 com o `model.skp` aberto (enviada
  por Felipe em 2026-05-09; salvar via:
  `cp <screenshot.png> docs/diagnostics/2026-05-09_skp_visual_failure_fp014_su_screenshot.png`)

### Sintomas adicionais observados na screenshot 3D real do SU 2026

A screenshot do SU revela 2 sintomas que as previews 2D pré-renderizadas
não mostravam tão claramente:

1. **Walls "orphan" / flutuando dentro do envelope** —
   - 3 wall blocks isolados visíveis dentro de COZINHA (canto
     superior-esquerdo do envelope), sem conexão a outros walls
   - 2 wall blocks no centro entre BANHO 02 e SUITE 01, igualmente
     isolados
   - **Quantificação:** validação topológica revela `0/33 orphans`
     no sentido estrito (toda wall toca a boundary de algum room).
     **MAS** revela **14/33 walls fragmentos curtos (<1m)**, alguns
     com apenas **26 cm** — `w003`, `w007`, `w010`, `w022`. E
     **10 pares de walls colineares com gap pequeno** (5–35 pt =
     0.19–1.25 m), exatamente onde portas foram carved (PR #42)
   - **Mecanismo:** wall original de ~5m → carved em `w002` (1.5m)
     + gap (door, 1m) + `w003` (0.26m) + gap (door, 1.4m) + `w004`
   - **Consequência visual:** o exporter cria cada fragmento como
     bloco SU separado → "barras pretas" isoladas. Não é "wall
     orphan" topológico, é **fragmentação por carving agressivo**

2. **Floor → wall Z-overlap** —
   - SUITE 01 floor (verde) atravessa visualmente POR DEBAIXO
     das walls de BANHO 02 — em axon 3D fica claro que o floor
     está em `z=0` e as walls extrudam por cima dele
   - Isso é o que causa o "vazamento" visual: walls não cortam o
     floor poligonalmente; o floor é uma face única que passa por
     debaixo
   - **Confirma que o exporter é honest passthrough:** ele não
     intersecta floor com walls, só extruda separadamente

3. **Portas (marrons) flutuando** —
   - As 5 portas aparecem como **faces planas marrons** dentro de
     gaps das walls, NÃO ancoradas estruturalmente
   - Parecem "swing leafs" renderizados separadamente, não
     openings na wall propriamente
   - Visualmente parece que as portas estão soltas no espaço
   - **Mecanismo:** `consume_consensus.rb` cria a porta como uma
     `ComponentInstance` posicionada no centro do gap, mas o gap
     é carved da wall em paralelo (PR #42); o swing leaf
     "flutua" porque é um plano separado

4. **Janelas (vidros transparentes azul-claros)** —
   - Visíveis nos walls do TERRACO SOCIAL (parte inferior-esquerda)
     e em pontos centrais
   - Posicionamento correto, mas são planos de vidro extrudados
     em frente do gap da wall, não "openings" propriamente
   - Parece OK visualmente

5. **Topo aberto** — nenhum teto/laje extrudado. Por design (V6.2
   foca walls + floors; teto deferido).

### Sintoma D — opening misclassification, width undershoot, peitoris não detectados

**Detectado em 2026-05-09 quando Felipe revisou as posições/larguras
contra as medidas explícitas do PDF.**

#### D.1 — colinear-gap → opening mapping incompleto

10 de 17 gaps colineares em walls **não têm opening atribuída**:

```
w1   w2    gap_m  orient   opening   distance
-------------------------------------------------
w001 w020  2.46     v      NONE      51.4
w004 w027  5.25     v      NONE      31.4    ← gap MASSIVO sem opening
w006 w007  0.97     h      NONE      59.8
w008 w013  0.19     v      NONE     102.3
w009 w010  0.97     h      NONE     103.5
w015 w023  0.19     v      NONE      38.0
w016 w018  4.32     h      NONE      68.7    ← gap grande sem opening
w017 w018  2.20     h      NONE      73.2
w019 w028  0.19     v      NONE      61.2
w024 w027  0.19     v      NONE      37.5
```

Esses 10 gaps são onde o PDF mostra peitoris (PEITORIL H=1,10M),
janelas, e aberturas amplas (p. ex., porta-vidro de TERRACO SOCIAL
= 3.82m, peitoril = 4.20m). O `extract_openings_vector` falha em:
- detectar peitoris desenhados como wall fino paralelo (não como gap)
- conectar gaps grandes (>2m) a uma opening identificada
- emparelhar gaps pequenos (0.19m) a soft_barriers existentes

Resultado no SKP: vários trechos de wall ficam "sólidos" onde no
PDF tem janela ⇒ aparência visual de "wall sem janela onde deveria".

#### D.2 — opening width vs gap width: inconsistência sistemática

Quando opening foi detectada via **SVG door arc**, `opening_width_pts`
é a **chord** do arco. Quando detectada via **wall_gap**, é o gap
real. Em `consume_consensus.rb`, esse valor é usado literalmente
como largura do void carved.

| Opening | Mecanismo | Width detectada | Medida visível PDF | Δ |
|---|---|---|---|---|
| **o007** (cozinha→sala) | door arc | 1.16 m | porta visível ~0.85 m | +0.31 |
| **o010** (banho02→suite01) | door arc | 1.02 m | "1.20" marcado | -0.18 |
| **o003** (suite01→banho01) | door arc | 1.36 m | porta visível ~0.85 m | +0.51 |
| **o009** (suite01↔sala) | door arc | 0.90 m | "0.90" marcado | ✅ 0 |
| **o005** (suite02 entrance) | door arc | 1.22 m | "1.20" marcado | -0.02 |
| **g001** (terraço social) | wall_gap | 2.88 m | "2.60" + porta | +0.28 |
| **g002** (suite02→terraço) | wall_gap | 1.93 m | "3.20" PDF | -1.27 ← BIG |
| **o008** (window) | wall_gap | 0.87 m | A.S. window 1.77m | -0.90 ← BIG |
| **o012** (window) | wall_gap | 0.91 m | TERRACO peitoril 3.82m | -2.91 ← MASSIVE |
| o006 (passage) | ? | 1.20 m | LAVABO area | ? |
| o004 (passage) | ? | ? m | A.S. side | ? |

**Padrão:** widths de **portas** (door arc) ficam razoavelmente
próximas. Widths de **janelas/peitoris** (wall_gap) podem ficar
massivamente undershot — o algoritmo mede o gap entre 2 walls
fragmentados, mas o PDF tem a abertura inteira (peitoril contínuo
de 3.82m fragmentado em 4 pedaços por marcadores intermediários).

#### D.3 — consequência visual no SKP

- Portas ficam ~OK (largura próxima do real)
- Janelas/peitoris extruídos estreitos demais
- Várias regiões com "wall sólido" onde PDF tem janela
- Combinado com o **Sintoma A** (wall fragments), o exporter desenha:
  - wall_fragment (0.26m) — janela_estreita (0.91m) — wall (1.5m) — peitoril faltando — wall (3m) — etc.
  - Em vez de: wall (1.5m) — peitoril (3.82m) — wall (1.5m)

### Artifacts visuais adicionais (Sintoma D)

- `2026-05-09_skp_visual_failure_fp014_openings_overlay.png` — PDF
  rasterizado com **círculos coloridos** sobre cada opening
  detectada (vermelho=door, laranja=passage, azul=window,
  ciano=glazed_balcony) + label `id` / `→wall_id` / `width_m`
- `2026-05-09_skp_visual_failure_fp014_pdf_zoom_top.png` —
  zoom da região top do PDF (cozinha+lavabo+suite01+banho01) com
  **medidas em metros visíveis** (5.14, 1.20, 0.90, 1.40, 2.40, etc.)
- `2026-05-09_skp_visual_failure_fp014_pdf_zoom_bot.png` —
  zoom da região bottom (suite02+terraços+a.s.) com medidas:
  - **PEITORIL H=1,10M** (largura 3.82m) — não detectado
  - **2.60m** porta SUITE 02→TERRACO TECNICO — undershot pra 1.93m
  - **2.49m**, **3.20m**, **4.00m**, **4.37m** — várias medidas
    de aberturas que o detector ignorou ou mediu errado

## Metadados do SKP (este run)

| Item | Valor |
|---|---|
| `.skp` path | `runs/_milestone_skp_planta74_2026_05_09/_smoke_out/model.skp` |
| `.skp` size | 96,903 bytes (97,197 post-inspector re-save) |
| `.skp` sha256 | `534f6e677947eaa238990b9fd2ecd46784b243c317180029e55092e2b6d89cd9` |
| consensus | `runs/_milestone_skp_planta74_2026_05_09/consensus.json` |
| consensus sha256 | `f9814dc56f7c746d28bf0ca397e23b46bad7aa9772e1d8f8fdd02990243556a6` |
| amended_observed | n/a (E2 SKIP — sem overrides) |
| fidelity_report | `runs/_milestone_skp_planta74_2026_05_09/fidelity_report.json` (global=0.917) |
| pre_skp_review_report | `runs/_milestone_skp_planta74_2026_05_09/_smoke_out/pre_skp_review_report.json` |
| F0 verdict | **PASS** (recommendation: "safe to export SKP") |
| overrides aplicados | **0** |
| git_commit | `9df2fee73a0e0bbee57d0ed8efc2b08c0b694975` |
| sketchup | `C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe` |
| pipeline | OVERVIEW.md §4.4 (5 passos) — `concave-hull` default true |

## Comparação 5-vis (PDF × cockpit × expected × F0 × SKP)

| Vis | O que mostrou | Capturou o erro? |
|---|---|---|
| **PDF original** | LIVING GRAND WISH JARDIM 74.83 m² — 11 cômodos com paredes claras, separação SALA DE ESTAR / SALA DE JANTAR limpa, SUITE 01 retangular bounded por walls visíveis | (referência, não é "captura") |
| **cockpit SVG overlay** (L1, `_cockpit_overlay.svg`) | Renderiza os MESMOS polygons que o SKP usa — mostra SUITE 01 vazando, SALA fundida, COZINHA com fold | ✅ **MOSTRA** o problema, mas não tem WARNING associado — o overlay é descritivo, não enforcer |
| **expected_match overlay** (L2) | Cada room comparada a `expected_model.json` por **área**: 10/11 in_range, 1 out_of_range_low (TERRACO TECNICO) | ❌ **NÃO captura** — só compara área (SUITE 01 = 24.09 m² está dentro do range [10, 28]). NÃO verifica shape, vazamento ou complexidade |
| **fidelity_report** | global=0.917, room_score=1.0, count_score=1.0, bbox_score=1.0, adjacency_score=0.667; 0 hard_fails, 2 advisory warnings | ❌ **NÃO captura** — mesma razão (área dentro do range == "passa"); shape complexity não é sub_score |
| **pre_skp_review (F0)** | verdict=**PASS**, recommendation="safe to export SKP" | ❌ **FALSO POSITIVO** — F0 lê fidelity_score + hard_fails + warnings count. Como nenhum desses pegou shape complexity, F0 reporta safe |
| **SKP no SU 2026** | Floors visualmente vazando | ✅ Captura o erro mas só EX-POST |

**Conclusão da comparação:** o cockpit overlay (L1) é o ÚNICO surface
pre-SKP que mostrava o problema, mas só visualmente, sem disparar
qualquer flag/warning. Todas as outras 4 layers (expected_match,
fidelity, F0, proposed_actions) são "blind" para o tipo de
defeito que aparece no SKP.

## Análise técnica — onde nasce o defeito

### Mecanismo do polygon — `tools/rooms_from_seeds.py`

```python
# (rooms_from_seeds.py — defaults)
use_voronoi: bool = True              # watershed seeded raster
use_concave_hull: bool = True         # bound by concave_hull(wall endpoints) since Cycle 8b
concave_hull_ratio: float = 0.5
```

Pipeline interno do método `voronoi`:
1. Rasteriza o `planta_region` (PDF coords) em N×M pixels
2. Para cada wall, "queima" a thickness no raster como obstáculo
3. Para cada label/seed point, faz **watershed flood-fill** desde o seed
4. Bound by `shapely.concave_hull(wall_endpoints, ratio=0.5)` — corta
   tudo fora do envelope
5. Para cada região segmentada: extrai contour via OpenCV
   (`cv2.findContours`) + Douglas-Peucker simplification
6. Salva `polygon_pts` + `area_pts2` no JSON

### Métricas que provam o defeito

```
room                 vts   free_vts   long_diags   area_m2
-------------------------------------------------------------
SUITE 02              13          4            4    13.27
BANHO 02              18          4            0     6.22
A.S.                  15          4            3     1.38
TERRACO SOCIAL        13          9            3    11.68
SUITE 01             738        611            3    24.09     ← MASSIVE
BANHO 01               9          1            2     5.46
COZINHA               14          5            1     8.78
LAVABO                 5          0            2     3.37
SALA DE JANTAR        12          8            3    13.05
SALA DE ESTAR         19          8            2    10.82
TERRACO TECNICO      189        150            0     1.59     ← MASSIVE
```

- **vts** = número de vértices no `polygon_pts`
- **free_vts** = vértices que NÃO estão num wall endpoint nem na linha
  de nenhum wall (tolerância 1.5× wall_thickness)
- **long_diags** = edges > 50 pt que não seguem nenhum wall

**Anomalias claras:**
- SUITE 01: 738 vértices, 611 (83%) "free" — polygon é **trace de
  raster contour**, não cells fechadas pelos walls
- TERRACO TECNICO: 189 vts, 150 free — idem, mas resultou num sliver

Polygons "razoáveis" (LAVABO, BANHO 01, BANHO 02) têm 5–18 vts,
poucos free — esses são os cômodos cujo watershed encheu uma
cell bem fechada por walls.

### Mecanismo do exporter — `tools/consume_consensus.rb`

O exporter (chamado via `tools/skp_from_consensus.py` → SU 2026 +
plugin `consume_consensus.rb`) lê cada room do consensus e cria
`Sketchup::Face.new(polygon_pts)` — usando os 738 vértices brutos
como uma única face. O extruder não SABE que esse polygon vaza
sobre BANHO 02 — ele só recebe um array de vertices.

→ **O exporter é honest passthrough — não inventa nem corrige.**
O defeito vem 100% do consensus.

## Respostas objetivas (perguntas Felipe)

### 1. O cockpit já mostrava esse vazamento antes do SKP?
**Sim**, no SVG overlay (L1 — `_cockpit_overlay.svg`, e idem em
`preview_top.png`). Mas **sem flagging** — o overlay é descritivo,
não enforcer. O reviewer humano teria que olhar e perceber.

### 2. O F0 marcou PASS/WARN/FAIL?
**PASS.** `recommendation: "safe to export SKP"`. Falso positivo.

### 3. O fidelity pegou esse problema?
**Não.** `room_score=1.0` porque todas as áreas caíram dentro dos
ranges esperados. `bbox_score=1.0` porque o bounding box bate. A
fidelity v1 não tem métrica de **shape complexity** ou **wall
adherence**.

### 4. O problema nasce em `rooms_from_seeds`?
**Sim — origem primária.** Mecanismo: watershed raster + contour trace
+ concave-hull bound de wall endpoints. Polygons resultantes têm 738
vts (SUITE 01) e diagonais nas regiões onde o concave-hull dos
endpoints inclui áreas sem walls fechando.

### 5. O problema nasce em `apply_overrides`?
**Não.** Não houve overrides aplicados (E2 SKIP). `apply_overrides`
nem rodou nesse path.

### 6. O problema nasce no exporter SKP?
**Não — exporter é honest passthrough.** Recebe 738 vts de SUITE 01
e cria a face com 738 vts. Se o consensus tivesse 4 vts retangulares,
o exporter criaria 1 face retangular limpa.

### 7. O problema é floor polygon, wall graph, opening placement ou todos?
**~~Apenas floor polygon.~~ CORRIGIDO 2026-05-09: TRÊS FAMÍLIAS distintas.**

- **Wall graph (Sintoma B):** 33 walls com escala correta
  (`wall_thickness_pts=5.40`, anchor `t/0.19` válido) MAS
  **14/33 walls < 1m** (fragmentos por carving agressivo de
  openings), aparecem como "barras pretas" isoladas no SU 3D.
  Não é orphan topológico — é fragmentação.
- **Opening placement (Sintoma C):**
  - **10/17 colinear gaps sem opening atribuída** — janelas/peitoris
    do PDF (incluindo PEITORIL H=1,10M de 3.82m) **não detectados**
  - Quando opening vem de door arc, `opening_width_pts` = chord do
    arco (pode discrepar do gap real da wall em ±0.3-0.5m)
  - Quando opening vem de wall_gap, `opening_width_pts` = gap entre
    2 wall fragments — **undershot massivo** (g002 detectada 1.93m,
    PDF mostra 3.20m; o012 detectada 0.91m, PEITORIL 3.82m)
- **Floor polygon (Sintoma A):** método raster trace gera polygons
  com 738 vts (SUITE 01) e diagonais que viram floor leakage no SU.
  **Esse continua sendo o defeito mais visível.**

### 8. Qual a categoria do defeito?
**Algorítmico em `rooms_from_seeds`** — mas Felipe disse "não alterar
detector". Então o **menor fix real** é:
> adicionar gates F0 que BLOQUEIAM o SKP quando os polygons têm essa
> assinatura (vts > N OU free_ratio > X OU long_diags > 0)

## Checks mínimos para BLOQUEAR antes do SKP (proposta)

Adicionar ao `gate_f0` em `scripts/smoke/smoke_skp_export.py` (módulo
existente, sem alterar detector / threshold / baseline):

| Check | Threshold proposto | Veredito ao falhar |
|---|---|---|
| `room.polygon_vts ≤ 50` | rooms simples têm 4–20 vts; >50 indica raster trace | **FAIL** |
| `room.free_vertex_ratio ≤ 0.30` | > 30% de vts fora de qualquer wall ⇒ polygon não cola | **FAIL** |
| `room.shape_complexity_ratio ≤ 2.0` | `perim / (4·sqrt(area))`; rectangle = 1.0; >2.0 = forma muito tortuosa | **WARN** |
| `room.long_diag_count == 0` | edges > 50 pt fora de wall = atalho diagonal | **WARN** |
| `room.area_in_envelope_pct ≥ 0.95` | < 95% da room dentro do envelope wall convex_hull = vazamento | **FAIL** |
| `consensus.orphan_walls_count == 0` | walls sem nenhum room adjacente — surgem como walls "soltas" no SKP | **WARN** |
| `consensus.short_wall_fragments_count ≤ 5` | walls < 1m de comprimento são stubs entre portas; > 5 = carving demais | **WARN** |
| `consensus.colinear_adjacent_pairs_with_door_gap == carving_only` | pares colineares com gap só onde há porta no consensus.openings — se gap sem porta, fragmento órfão | **WARN** |
| `consensus.unmapped_colinear_gaps_count == 0` | gap entre walls colineares (>0.5m) sem opening → janela/peitoril missing | **FAIL** |
| `consensus.opening_width_vs_gap_diff_max ≤ 0.30 m` | opening width detectada não bate com gap do wall em mais de 30 cm = chord vs gap mismatch | **WARN** |
| `consensus.window_or_balcony_min_count_per_external_wall ≥ 1` | walls de envelope sem nenhuma janela/peitoril → detector perdeu janelas (PDF sempre tem) | **WARN** |
| `consensus.opening.host_wall_id` válido em walls[] | toda porta/janela aponta para um wall existente | **FAIL** |

**Implementação sugerida:** módulo novo `tools/structural_checks.py`
(pure-python, sem alterar detector). `gate_f0` chama-o e merge das
violations no `pre_skp_review_v1` (campos additivos
`structural_blockers[]`, `structural_warnings[]`).

**Estimativa:** ~150 LOC + ~15 testes. Nenhuma feature nova,
nenhum ADR novo, nenhum schema bump. Pure validation surface.

**Impacto no run atual:** F0 mudaria para **FAIL** (polygon_vts
SUITE 01=738 e TERRACO TECNICO=189 ambos disparam) — o SKP NÃO
seria exportado. Que é exatamente o comportamento desejado.

## Menor fix real — proposta atualizada após validação GPT-4o

> **Validação externa GPT-4o (2026-05-09):** ver
> [`2026-05-09_skp_visual_failure_fp014_gpt_validation.md`](2026-05-09_skp_visual_failure_fp014_gpt_validation.md)
> para a resposta integral. GPT classifica `rooms_from_seeds` como
> **root cause primário** e Opção C como **gate de proteção
> necessário, mas não substituto**.

### Sequência recomendada (atualizada)

```
1º — (A)  rooms_from_seeds refactor   ← fix que destrava o SKP
2º — (C)  gates F0 estruturais         ← proteção em paralelo
3º — (B)  extract_openings_vector      ← dívida secundária
```

### Opção A — refatorar `rooms_from_seeds` (ROOT CAUSE)
**Por quê:** GPT confirma — "o SKP ruim não está falhando primeiro
por porta/janela. Ele está falhando porque os polígonos dos
cômodos/pisos estão errados". Mesmo com openings perfeitas, o SKP
sai errado se polygon vaza.

**Fix correto:** trocar método raster trace + concave-hull por
`shapely.polygonize(walls)` para obter cells fechadas a partir de
wall segments. Cada room recebe a cell que contém seu seed_pt.
Polygon resultante tem 4–20 vértices, perfeitamente colado aos walls.

**Impacto:** elimina SUITE 01 com 738 vts; elimina TERRACO TECNICO
sliver; elimina diagonais "vazando" entre walls não-adjacentes.

**Reversível:** sim — `--use-polygonize` flag mantém legacy raster
trace como fallback.

### Opção C — gates F0 estruturais (PROTEÇÃO PARALELA)
**Por quê:** GPT — "mesmo que o algoritmo ainda não esteja perfeito,
o sistema NÃO PODE deixar sair SKP visivelmente defeituoso". Gate
deve bloquear: room polygon atravessando parede; floor fora do
envelope; área absurda; triângulo gigante; room com vértices demais.

**NÃO substitui Opção A** — é gate, não fix. Mas previne regressão
mesmo após Opção A landar.

**Implementação:** módulo novo `tools/structural_checks.py` (~150 LOC)
chamado por `gate_f0`. 7 checks definidos na seção
"Checks mínimos para BLOQUEAR antes do SKP" deste documento.

### Opção B — corrigir `extract_openings_vector` (DÍVIDA SECUNDÁRIA)
**Por quê é terceiro:** GPT — "o erro que mata o SKP hoje não é
'janela 20 cm fora' ou 'peitoril perdido' — é 'o cômodo virou um
polígono errado e o piso vazou'". Openings entram depois que room
polygons estiverem estáveis e F0 bloquear export ruim.

**Quando atacar:** após Opção A + C landrarem e estabilizarem.
Foco: detectar peitoris (PEITORIL H=1,10M de 3.82m totalmente
ausente) + medir vão completo (não fragmento entre wall stubs).

### Por que NÃO `room_polygon_override` (ADR-002) agora

ADR-002 §2.8 deixa explícito que SKP exporter é overrides-blind em
v1. Override só fixa fidelity report, não o SKP. Para o override
fluir pro SKP, precisa Slice 6e (`amended_consensus.json`), deferida
no próprio ADR. Sem Slice 6e, `room_polygon_override` não ajuda
este caso de uso. Continua queued para quando reviewer humano quiser
corrigir caso a caso, mas não está no critical path.

## Critério de aceite (próximo SKP)

Para considerar resolvido FP-014:

- [ ] Novo SKP gerado com mesma `planta_74.pdf`
- [ ] **SUITE 01 sem o "triângulo verde"** — polygon limitado pelas
  walls reais
- [ ] **SALA DE ESTAR e SALA DE JANTAR** separadas pela diagonal
  correta (não fundidas)
- [ ] **COZINHA** sem fold triangular esquerdo
- [ ] **Cada floor** com polygon ≤ 30 vértices
- [ ] **Nenhum vazamento** visível entre rooms adjacentes
- [ ] **Portas e janelas** com host_wall válido E ancoradas
  visualmente
- [ ] **F0 PASS apenas se** todos os checks structural acima passam
- [ ] **F0 WARN/FAIL** quando o defeito reaparece (regressão guard)

## Conclusão

O SKP atual é **inutilizável para layout/furniture planning** porque
SUITE 01 (e em menor grau TERRACO TECNICO) têm polygons gerados por
raster contour trace, com 738 e 189 vts respectivamente. O exporter
SU é honest passthrough; o defeito 100% origina em
`tools/rooms_from_seeds.py` (método `voronoi` + bound concave_hull).

**O F0 deu PASS porque a fidelity v1 não mede shape complexity nem
wall adherence — só área e adjacency.** O cockpit overlay mostrou
visualmente, mas sem flag.

**Próximo passo recomendado:** Opção C (structural checks no F0).
Não criar feature nova nem ADR. Não implementar Slice 6.
Apenas adicionar enforcement aos polygons que já existem.

## Referências

- Run dir: `runs/_milestone_skp_planta74_2026_05_09/`
- Pipeline: `OVERVIEW.md §4.4` (5 passos vetoriais)
- Detector: `tools/rooms_from_seeds.py` (voronoi + concave-hull)
- Exporter: `tools/consume_consensus.rb` (honest passthrough)
- Smoke gate F0: `scripts/smoke/smoke_skp_export.py` `gate_f0`
- Schema fidelity v1: `tools/fidelity/compare_generated_to_expected.py`
- ADR-001 §2.10.5 (honest reporting): `docs/adr/ADR-001-validation-cockpit-mutation-surface.md`
- ADR-002 §2.8 (SKP exporter overrides-blind v1): `docs/adr/ADR-002-room-polygon-overrides.md`
- Cycle 8b context (concave-hull promotion): `CLAUDE.md §10`
