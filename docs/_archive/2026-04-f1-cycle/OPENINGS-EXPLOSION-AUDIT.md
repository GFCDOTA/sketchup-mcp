# OPENINGS EXPLOSION AUDIT: planta_74 (15 -> 71 post-hardening)

Comit atual: `f2b896c` (branch `fix/dedup-colinear-planta74`).
Baseline: `dcb9751` (main pre-fix, em `runs/baseline_pre_fix_main`).

Nota: o prompt mencionava 7 openings no baseline; o artefato real tem 15.
A explosao relevante e, portanto, 15 -> 71 (4.7x), nao 7 -> 71 (10x).

## 1. Numeros agregados

| metrica | baseline (pre-fix) | current (pos-hardening) | delta |
|---|---|---|---|
| openings | 15 | 71 | +56 |
| walls | 104 | 230 | +126 |
| rooms (total) | 16 | 48 | +32 |
| rooms legit (>=3000 px2) | 3 | 25 | +22 |
| openings genuine (>=1 lado room legit) | 6 | 67 | +61 |
| openings suspect | 9 | 4 | -5 |

Observacao critica: o baseline pre-fix so tinha 3 rooms acima de 3000 px2 (rooms 1/4/9 com areas 13k/16k/3.5k). O resto (13 das 16) sao slivers. O hardening nao inventou portas; ele passou a fechar poligonos antes perdidos.

## 2. Distribuicoes (post-hardening)

### Por kind

| key | n | % | bar |
|-----|---|---|-----|
| door | 57 | 80.3% | `###################.....` |
| passage | 14 | 19.7% | `#####...................` |

### Por orientacao

| key | n | % | bar |
|-----|---|---|-----|
| horizontal | 64 | 90.1% | `######################..` |
| vertical | 7 | 9.9% | `##......................` |

### Por bucket de largura (px @ 150 DPI)

| key | n | % | bar |
|-----|---|---|-----|
| wide_door_110-200 | 23 | 32.4% | `########................` |
| door_60-110 | 19 | 26.8% | `######..................` |
| tiny_10-60 | 15 | 21.1% | `#####...................` |
| window_or_passage_200-280 | 14 | 19.7% | `#####...................` |

Faixas de referencia: door 60-110; wide door 110-200; window/passage 200-280; tiny 10-60 (suspeito - gap dedup residual); absurd <10 (bug).

## 3. Openings vs rooms (tabela top-genuinos)

Classificacao `genuine = pelo menos um lado do opening cai em room >=3000 px2`. Lado = Point(cx +/- 8px, cy +/- 8px) perpendicular ao vao, via shapely contains.

### Top 10 genuinos (ambos lados em rooms grandes, width proxima de porta padrao)

| opening_id | wall_a | wall_b | room_a (area) | room_b (area) | width | ori | kind | genuine |
|---|---|---|---|---|---|---|---|---|
| opening-21 | wall-52 | wall-53 | room-25 (10712) | room-25 (10712) | 86.5 | H | door | YES |
| opening-42 | wall-94 | wall-95 | room-33 (11100) | room-33 (11100) | 81.5 | H | door | YES |
| opening-5 | wall-16 | wall-17 | room-5 (7968) | room-9 (40376) | 93.0 | H | door | YES |
| opening-34 | wall-82 | wall-83 | room-33 (11100) | room-33 (11100) | 74.5 | H | door | YES |
| opening-48 | wall-102 | wall-103 | room-32 (7505) | room-39 (4036) | 73.3 | H | door | YES |
| opening-43 | wall-95 | wall-96 | room-33 (11100) | room-33 (11100) | 70.7 | H | door | YES |
| opening-8 | wall-28 | wall-29 | room-9 (40376) | room-9 (40376) | 68.7 | H | door | YES |
| opening-35 | wall-83 | wall-84 | room-33 (11100) | room-33 (11100) | 66.7 | H | door | YES |
| opening-20 | wall-51 | wall-52 | room-25 (10712) | room-26 (3184) | 109.1 | H | door | YES |
| opening-6 | wall-18 | wall-19 | room-5 (7968) | room-9 (40376) | 110.0 | H | door | YES |

### Top 10 suspeitos (mais provaveis de serem falsos positivos)

Priorizados por (1) genuine=False e (2) width extremo (<10 ou >280). So 4/71 openings sao classificados suspeitos por este criterio.

| opening_id | wall_a | wall_b | room_a (area) | room_b (area) | width | ori | kind | genuine |
|---|---|---|---|---|---|---|---|---|
| opening-50 | wall-105 | wall-106 | room-38 (2542) | - | 73.3 | H | door | no |
| opening-53 | wall-111 | wall-112 | room-48 (2089) | room-48 (2089) | 73.3 | H | door | no |
| opening-55 | wall-114 | wall-115 | room-48 (2089) | room-43 (946) | 73.3 | H | door | no |
| opening-56 | wall-116 | wall-117 | room-48 (2089) | - | 73.3 | H | door | no |
| opening-1 | wall-9 | wall-10 | room-1 (12384) | room-8 (18097) | 118.5 | H | door | YES |
| opening-2 | wall-10 | wall-11 | room-2 (24858) | room-5 (7968) | 240.7 | H | passage | YES |
| opening-3 | wall-12 | wall-13 | room-5 (7968) | room-5 (7968) | 240.7 | H | passage | YES |
| opening-4 | wall-14 | wall-15 | room-5 (7968) | room-9 (40376) | 243.4 | H | passage | YES |
| opening-5 | wall-16 | wall-17 | room-5 (7968) | room-9 (40376) | 93.0 | H | door | YES |
| opening-6 | wall-18 | wall-19 | room-5 (7968) | room-9 (40376) | 110.0 | H | door | YES |

### Classificacao granular por quantidade de lados legit

- `BOTH` rooms grandes: **53** openings (porta 'perfeita' entre dois ambientes)
- `ONE_SIDE` grande + outro lado sliver/vazio: **14** openings (borda externa ou split)
- `NONE` lado em room legit: **4** openings (suspects puros)

## 4. Histograma textual de width (post-hardening)

```
width_bin  count  bar
    0- 20     3  ###
   20- 40     9  #########
   40- 60     3  ###
   60- 80    11  ###########
   80-100     5  #####
  100-120     7  #######
  120-140     6  ######
  140-160     3  ###
  160-180     3  ###
  180-200     7  #######
  200-220     9  #########
  220-240     1  #
  240-260     3  ###
  260-280     1  #
  280-300     0  
  300-320     0  
```

## 5. Hipoteses (H1/H2/H3)

- **H1 (extras em slivers)**: REJEITADA para a maioria. Apenas 4 openings nao tem nenhum lado em room legit. Se H1 fosse dominante, esperariamos dezenas de openings entre slivers triangulares.
- **H2 (fragmentos que deveriam estar snapados)**: PARCIAL. 15 openings caem no bucket `tiny_10-60` (<60 px, menor que porta real). Sao candidatos a dedup residual: provavelmente dois pedacos de mesma wall que o extractor deixou com gap 20-40 px, e o detector classificou como porta. `_extend_to_perpendicular` nao alcanca estes (snap = 60 px mas gap no meio da wall, nao no endpoint).
- **H3 (ganho real de recall)**: CONFIRMADA como hipotese dominante. Post-hardening: 25 rooms legitimas (vs 3 no baseline), 67/71 openings genuinos (94%). O baseline pre-fix estava falhando em fechar polygonos - pipeline atual finalmente consegue separar os ambientes que o raster original tem.

Evidencia quantitativa: rooms grandes (>10k px2) saltaram de 2 (baseline) para 17 (current). Isso so e possivel se walls novas realmente fecharam poligonos.

## 6. Recomendacoes

Dois ganchos possiveis pra reduzir ruido sem sacrificar recall:

1. **Sliver filter downstream** (preferido, baixo risco): ao filtrar rooms com area < LEGIT_AREA no pos-processamento, dropar tambem openings cujos dois lados caem em slivers ou fora de rooms. Hoje seriam 4 openings removidos. Simples, determinstico, nao mexe em `openings/service.py`.

2. **Reforcar dedup colinear residual em openings/service.py** (ataque H2): 15 openings no bucket 10-60 px sao provavelmente mesma wall fragmentada. Opcoes: (a) aumentar `_MIN_OPENING_PX` de 8 para 40 (corta todos tiny mas risca portas de 30-40 px em desenhos em escala menor); (b) adicionar criterio `confidence = min(wall_a.confidence, wall_b.confidence)` e descartar bridges com `confidence < 0.4` + `width < 60`; (c) checar se wall_a.thickness == wall_b.thickness com tolerancia pequena - se sim E gap < 50 px, e provavel mesma wall.

Recomendacao final: adotar (1) agora (patch 1-linha no room filter pipeline) e agendar (2c) como fase de followup junto com o sliver filter - ambos atacam o mesmo sintoma (fragmentacao residual) por vias complementares.

## 7. Metodologia e artefatos

- Comando extracao: `python main.py extract planta_74.pdf --out runs/openings_audit`
- Scripts: `scripts/audit_openings.py` (enrichment) + `scripts/audit_openings_report.py` (este doc)
- Dados brutos: `runs/openings_audit/observed_model.json`
- Sumario JSON: `runs/openings_audit/audit_summary.json`
- Baseline: `runs/baseline_pre_fix_main/observed_model.json`
- Overlay visual auditado: `runs/openings_audit/overlay_audited.png`

Criterio `genuine`: construimos dois Points deslocados 8px perpendiculares ao opening a partir do center, e verificamos se pelo menos um cai em room com area >= 3000 px2 via shapely Polygon.contains. Threshold 3000 e conservador (apartamento tipo: WC 2-4k, cozinha 4-6k, quarto 6-12k, sala/varanda 10-40k). Slivers diagonais de dedup ficam tipicamente < 2000 px2.

Limitacao da heuristica: quando `room_a == room_b` na tabela, nao significa bug - significa que ambos Points offset caem na mesma room grande (opening esta em wall interna com room passante dos dois lados, ou offset de 8px foi insuficiente pra cruzar a parede). Isso nao afeta o flag `genuine` (satisfeito mesmo com um lado).

Inspecao visual do overlay (`runs/openings_audit/overlay_audited.png`): confirmou presenca de ~15 slivers triangulares nas bordas (R13/R14/R15/R17/R18/R19/R21/R23/R28/R29/R37/R38/R39/R43/R46/R47) - todos abaixo do threshold LEGIT_AREA, consistentes com a contagem de 23 rooms <3000 px2 (48 total - 25 legit). Openings suspect-puro (4) concentram-se em `wall-105..117` na direita da planta, regiao de R43/R48 (slivers). O overlay confirma H3 (ganho real de recall) como hipotese dominante.
