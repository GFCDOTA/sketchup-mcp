# Dedup Audit — `_dedupe_collinear_overlapping`

## Resumo

O segundo passe de dedup em [`classify/service.py`](../classify/service.py#L271-L461) (`_dedupe_collinear_overlapping`) corre depois do `_consolidate_hough_duplicates`, dentro de `classify_walls`. Objetivo: colapsar detecções Hough duplicadas de um mesmo traço físico que escaparam do primeiro passe por ficarem fora da tolerância exata — twin detections sub-pixel e collinear splits em planta raster escalada. Algoritmo representative-anchored (sweep por `(page, orientation)` ordenado por coordenada perpendicular, cluster aberto com bound duro `perp_spread <= perp_tolerance` e gate de `parallel_overlap >= overlap_ratio` contra a seed mais longa). O cluster fecha quando spread excederia o bound OU overlap cai — substitui o union-find anterior que produzia super-clusters transitivos (F3 audit: cluster de 56 membros com spread=151px em planta_74). Bound `perp_spread <= perp_tolerance` é garantido por construção e validado no report.

## Parâmetros

| Constante | Valor | Comentário |
|---|---|---|
| [`_DEDUP_PERP_TOLERANCE`](../classify/service.py#L79) | `20.0` px | Tolerance=10 era conservador demais (só 22 de 220 mergeados, rooms 16→54). 20 absorve twin chains em raster 2x (perp jitter dobra) e deixa dupla alvenaria (perp >= 25) intacta. |
| [`_DEDUP_OVERLAP_RATIO`](../classify/service.py#L80) | `0.35` | Overlap mínimo (fração do segmento mais curto) contra a seed. Evita fundir collinears que só se tocam na ponta. |
| [`_TWIN_DETECTION_PERP_PX`](../classify/service.py#L87) | `5.0` px | Boundary de anotação: `spread <= 5` → `merge_reason="twin_detection"`; acima → `collinear_split`. Puramente informativo para o revisor. |
| [`_DEDUP_ACTIVATION_RATIO`](../classify/service.py#L95) | `0.05` | Gate por densidade (fração dos candidates com parceiro colinear próximo). Substitui o antigo `len > 200` — escala-invariante. Plantas limpas tipo p12_red observam ~0; planta_74 observa >> 0.05. |

## Casos onde MERGEOU com justificativa geométrica

Dados extraídos de [`runs/validate_hardening/dedup_report.json`](../runs/validate_hardening/dedup_report.json) (planta_74.pdf, 220 candidates → 184 kept, 36 merged em 22 clusters; todos em `page_index=0`).

### Caso 1 — Spread mínimo observado (quase-twin)

| Campo | Valor |
|---|---|
| `cluster_id` | 10 |
| `orientation` | horizontal |
| `member_count` | 2 |
| `perp_spread_px` | 6.166 |
| `min_parallel_overlap_ratio` | 1.0 |
| `merge_reason` | `collinear_split` |

Duas detecções horizontais separadas por ~6px perpendicular, com overlap paralelo integral (1.0 — o menor contém 100% do outro). Spread apenas 1.16px acima do boundary twin (5.0), indica stroke real com jitter Hough levemente acima do esperado para twin puro — consistente com raster 2x. Merge é seguro: membros compartilham geometria paralela inteira.

### Caso 2 — Spread médio com overlap parcial

| Campo | Valor |
|---|---|
| `cluster_id` | 3 |
| `orientation` | horizontal |
| `member_count` | 3 |
| `perp_spread_px` | 15.25 |
| `min_parallel_overlap_ratio` | 0.646 |
| `merge_reason` | `collinear_split` |

Três collinears horizontais com spread 15.25px (75% do tolerance) e overlap mínimo 64.6% (bem acima do gate de 35%). Cenário típico de collinear split: wall única detectada em três fragmentos Hough com ruído perpendicular moderado. O gate de overlap (0.646 >> 0.35) confirma coerência paralela — não é caso de dois segmentos encostando pontas.

### Caso 3 — Maior cluster (spread próximo ao bound)

| Campo | Valor |
|---|---|
| `cluster_id` | 13 |
| `orientation` | vertical |
| `member_count` | 6 |
| `perp_spread_px` | 19.245 |
| `min_parallel_overlap_ratio` | 1.0 |
| `merge_reason` | `collinear_split` |

Seis verticais co-lineares com spread 19.245px — 96% do tolerance, borderline. Overlap integral (1.0) em todos os pares contra a seed. É o pior caso que ainda respeita o bound: se fosse 20.5px, o cluster fecharia antes do último membro entrar e emitiria dois clusters. Sem o refactor representative-anchored (F1), o union-find encadearia esses 6 com outros próximos e o spread total explodiria — exatamente a patologia observada (56 membros, spread=151).

### Observação sobre `twin_detection`

Nenhum dos 22 clusters deste run caiu em `merge_reason=twin_detection` (todos têm `perp_spread > 5.0`). Em planta_74 o primeiro passe `_consolidate_hough_duplicates` já absorve twins sub-pixel via coordinate_tolerance, sobrando para este segundo passe apenas os collinear splits que escaparam. O boundary 5.0 permanece relevante para plantas com Hough mais ruidoso.

## Casos onde NÃO MERGEOU

O `dedup_report.json` só emite clusters com `member_count >= 2` ([`_emit_cluster`](../classify/service.py#L346-L349) retorna early senão), então os 184 candidates que sobreviveram sozinhos não aparecem nomeados. A aritmética é rastreável: `candidate_count_before=220`, `kept_count=184`, `merged_count=36`, 22 clusters emitidos, 36 merged distribuídos nesses clusters (avg member_count ≈ 2.6).

### Caso A — Dupla alvenaria (`perp_spread > tolerance`)

Duas walls paralelas de dupla alvenaria separadas por ~25-30px perpendicular (threshold físico de construção). Cenário:

- Sweep ordena por perpendicular. Primeiro membro abre cluster com `open_min_perp = open_max_perp = p1`.
- Segundo membro entra com `p2 = p1 + 28`. [Linha 419-421](../classify/service.py#L419-L421): `new_max - new_min = 28 > 20` (tolerance). `spread_ok = False`.
- [Linha 438](../classify/service.py#L438): `_emit_cluster(open_cluster, ...)` fecha o cluster aberto. Como só tem 1 membro, `_emit_cluster` retorna sem emitir ([linha 348](../classify/service.py#L348)). O segundo membro seeds um novo cluster.
- Ambos sobrevivem em `keep_mask=True`, não aparecem no report.

Garantia: um par dupla-alvenaria NUNCA pode aparecer como cluster neste report porque o bound `spread <= 20` é checado antes de admitir na emissão.

### Caso B — Pair colinear disjoint (`overlap_abs = 0`)

Dois segmentos no mesmo y (perp idêntico), `seg1 = [x=0, x=50]`, `seg2 = [x=200, x=250]`. Cenário:

- Ordenados por perp coincidem, seed = seg1, `seed_length=50`.
- Candidato seg2: [linha 424](../classify/service.py#L424) `overlap_abs = max(0, min(50, 250) - max(0, 200)) = max(0, 50 - 200) = 0`. `overlap_ok = 0/50 < 0.35 = False`.
- Mesmo que `spread_ok=True` (mesmo perp), a conjunção [linha 427](../classify/service.py#L427) `spread_ok AND overlap_ok` falha. Cluster atual fecha (1 membro → não emitido), seg2 seeds novo.
- Ambos preservados.

## Limite da confiança no dedup

- **Escala-invariante**: o gate `_DEDUP_ACTIVATION_RATIO` mede densidade de pares colineares-próximos, não count absoluto. Teste mental: render em 2x DPI dobra total de candidates mas também dobra pares dentro de 20px perp → razão preservada. Substitui o antigo `len > 200` que era frágil pra canvas grande.
- **NÃO resolve over-polygonization de rooms**: walls dedupadas ainda podem formar polígonos espúrios na topologia. Filtro separado em `topology/` check trata disso.
- **NÃO toca openings**: dedup opera em candidates antes de identificar portas/janelas. Gaps de porta preservados por construção (um stroke de ombreira não é candidate de wall).
- **Report só mostra agrupamentos**: clusters com 1 membro (que não mergearam) ficam invisíveis. Para auditar não-merges precisa olhar `candidate_count_before - kept_count == merged_count` e inferir pelos bounds do algoritmo.

## Como rodar sua própria auditoria

```bash
# Pipeline completo, gera runs/audit/dedup_report.json
python main.py extract <pdf> --out runs/audit/

# Top 10 clusters com maior spread
python -c "import json; r=json.load(open('runs/audit/dedup_report.json')); \
  [print(c) for c in sorted(r['clusters'], key=lambda x: -x['perp_spread_px'])[:10]]"

# Sanity check do bound
python -c "import json; r=json.load(open('runs/audit/dedup_report.json')); \
  assert all(c['perp_spread_px'] <= 20.0 for c in r['clusters']), 'BOUND VIOLATION'; \
  print(f'OK: {len(r[\"clusters\"])} clusters, max_spread={max(c[\"perp_spread_px\"] for c in r[\"clusters\"]):.3f}')"
```

## Invariantes

| Invariante | Bound | Por quê |
|---|---|---|
| `perp_spread_px <= perp_tolerance` | `<= 20.0` | F1 refactor (representative-anchored) garante por construção: cluster fecha antes de admitir membro que violaria o bound. |
| `min_parallel_overlap_ratio >= overlap_ratio` | `>= 0.35` | Gate de entrada contra a seed. Um membro só entra se overlap com a seed mais longa >= 35% do segmento mais curto. |
| `kept_count + merged_count == candidate_count_before` | igualdade exata | Contabilidade: cada input ou sobrevive (slot preservado ou substituído pelo representante) ou é descartado via `keep_mask=False`. |
| Todo cluster tem `member_count >= 2` | `>= 2` | [`_emit_cluster`](../classify/service.py#L348-L349) retorna early se tamanho 1. Singletons nunca aparecem no report. |
