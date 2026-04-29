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

## 2026-04-21 — PR `feat(openings): close 33->24 gap` (commit `b1827a2`)

Duas mudancas fecharam o gap para o target arquitetonico:

1. **Filtro C relax**: `perp_mul` 1.0 -> 1.5. Analise empirica dos 33
   restantes identificou 4 pares de duplicatas horizontais em offset
   perp 7-8 px (> 1 x thickness mas < 1.5 x thickness). Com o gate
   relaxado, mais o efeito transitivo via union-find, o filtro C
   captura 11 merges (vs 4 antes).
2. **Filtro D implementado** (`postfilter_roomless_openings`): roda
   apos `build_topology`, drop openings cujos 2 side-points
   perpendiculares caem fora de qualquer room legitimo
   (area >= thickness^2 x 25). Conservador: mantem porta externa
   onde um lado tem room interior. Em planta_74m2 remove os 3 "no_legit"
   (opening-36, -38, -39 no canto inferior esquerdo entre walls sem room).

```
openings: 33 -> 26 -> 24  (filter C relaxed: -7 extra; filter D: -2)
```

---

## Estado atual (pos A+B+C+D)

```
walls:       261
rooms:       23
junctions:   75
openings:    24      <-- DENTRO DO TARGET (15-25)
warnings:    []
```

Reducao total: **68 -> 24 (-65%)**.

### Breakdown final das 24

- **18** com ambos os lados em room legitimo (portas internas)
- **6** com um lado em room legitimo (portas externas / perimetro)
- **0** sem nenhum lado legitimo (filtro D removeu)

### Auditoria visual

Geracao:
```
python scripts/render_openings_conclusion_png.py --out runs/openings_conclusion.png
```

`openings_conclusion.png` (2x2 grid): baseline / +A / +A+B / +A+B+C+D.
Cada painel mostra walls em cinza claro e openings como circulos
coloridos por etapa, com contador e delta chip no topo.

### Proximos candidatos (fora deste ciclo)

- **Validacao em outros SVGs**: planta_74m2 foi o unico input; SVGs de
  outras origens podem expor novos edge cases.
- **Openings schema richer**: adicionar `bridge_wall_id` como campo do
  `Opening` permitiria auditoria mais direta do vinculo opening <-> bridge.
- **Proximo passo arquitetural** (por memoria): schema freeze +
  Ruby/SketchUp bridge (Fase 6 do ROADMAP).
