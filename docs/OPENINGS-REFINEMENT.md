# OPENINGS-REFINEMENT.md — historico do pipeline pos-deteccao

Append-only. Cada entrada documenta uma mudanca numerica em
`openings` no pipeline SVG e o raciocinio.

---

## 2026-04-21 — baseline apos main-component filter

Entrada: `planta_74m2.svg` (Anexo-1.-Planta-padro-74-93m-T1).
`thickness=6.25` SVG user-units.

```
walls:       261
rooms:       23
junctions:   75
openings:    68      <-- alto (meta 15-25)
warnings:    []
```

Diagnostico: dos 68 openings, 28 referenciam walls que foram dropadas
pelo `select_main_component` (carimbo, legenda, miniplanta). Seus
bridges tambem foram dropados — ficam fantasmas no JSON, nao fecham
polygon nenhum.

---

## 2026-04-21 — PR `feat(openings): prune orphan openings` (commit `55e6cb1`)

Filtro A: `prune_orphan_openings`. Droppa opening se `wall_a` e `wall_b`
estao ambos fora de `main_walls`. Mantem se pelo menos um sobreviveu
(caso de porta externa com fachada em componente separado).

```
openings: 68 -> 40  (-28, -41%)
```

Validacao espacial: 100% das 28 dropadas fora do bbox do apartamento
(y > 583, rodape). 0 das 40 kept fora do bbox.

Raster: `planta_74.pdf` `observed_model.json` sha256 identico.

---

## 2026-04-21 — PR `feat(openings): filter tiny gaps` (commit `8425c7f`)

Filtro B: `filter_min_width_openings`. Floor em `thickness * 3.5`
(~21.9 px). Em SVG, portas reais tem >= 50 px (8+ x thickness);
abaixo disso sao dedup residual de linha dupla.

```
openings: 40 -> 37  (-3, -7.5%)
```

Dropadas: widths 19.5, 19.7, 21.6. Thresholds via env var
`OPENINGS_MIN_WIDTH_MUL` para rollback.

---

## 2026-04-21 — PR `feat(openings): dedup colinear` (commit `06f934f`)

Filtro C: `dedup_collinear_openings`. Funde openings duplicadas de
parede dupla usando 4 gates combinados:

1. Mesma orientation
2. Perpendicular coord dentro de `thickness` (=offset de parede dupla)
3. Centers < `thickness * 4` de distancia no eixo paralelo
4. Overlap >= 30% entre os intervalos paralelos

Threshold validado via ChatGPT consult (memoria: `consult_chatgpt`):
portas reais adjacentes em corredor estao a > 38 x thickness, bem acima
do gate.

```
openings: 37 -> 33  (-4, -11%)
```

Merged openings: `opening-11`, `opening-47`, `opening-55`, `opening-63`
(cada um colapsado na versao mais larga do par).

Raster: sha256 identico em todos os 4 runs (baseline / A / A+B / A+B+C).

---

## Estado atual (pos A+B+C)

```
walls:       261
rooms:       23
junctions:   75
openings:    33      <-- ainda acima do target 15-25
warnings:    []
```

Reducao total: **68 -> 33 (-51%)**.

### Gap para target

33 openings restantes, meta arquitetonica 15-25. Delta 8-18.

Proximos candidatos (fora deste ciclo):
- **Filtro D** (`postfilter_roomless_openings`): opt-in, remove openings
  cujos 2 lados nao tocam room legitimo (area > `thickness^2 * 25`).
  Risco: pode remover porta externa onde um lado e fachada sem room
  interno. Default OFF.
- **Arc coverage detection** (raster-first): patch 06 rejeitado no ciclo
  raster anterior; reconsiderar para SVG se aparecer real falso positivo.
- **Validacao em outros SVGs**: planta_74m2 e sintetico; SVGs de outras
  origens podem revelar se 33 sao legit ou se ha mais filtros aplicaveis.

### Auditoria visual

Artefato visual gerado com:
```
python scripts/plot_openings_comparison.py \
  --before runs/openings_refine_baseline/observed_model.json \
  --after  runs/openings_refine_v1_c/observed_model.json \
  --out    runs/openings_refine_v1_c/openings_final_diff.svg
```

`openings_final_diff.svg`: openings kept em verde (33), dropped em
vermelho (35). Todos os reds estao fora do bbox da planta principal
ou sao tiny gaps (<22px). Nenhum tocou porta visualmente legit.
