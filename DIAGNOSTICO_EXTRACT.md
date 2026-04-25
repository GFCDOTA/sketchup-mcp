# Diagnóstico — extract pipeline em `planta_74.pdf` cru

Data: 2026-04-21
Run analisado: `runs/planta_74/` (94 walls, 14 rooms, 12 componentes, 7 órfãos)
Baseline: `runs/proto/p12_v1_run/` (35 walls / 19 rooms / 1 componente, sobre PDF pré-vermelhado)

## Evidência

`runs/planta_74/observed_model.json` (`grep "source"`):

```
46 hough_horizontal
44 hough_vertical
 2 paired_horizontal
 2 paired_vertical
```

Apenas 4 de 94 walls passaram por `_pair_merge_strokes`. O resto sobreviveu como
stroke único — ou seja, as duas faces (interior+exterior) de cada wall
arquitetural permaneceram como segmentos paralelos NÃO fundidos. Isso explica
o aspecto "despedaçado" e o perimetral aberto em `debug_walls.png`: cada
parede do perímetro virou 2 linhas finas paralelas separadas por ~5–13 px,
sem centerline comum.

ROI funcionou (`applied=true`, bbox 1113×664, 88.137 dark px, 1712 componentes).
Todo o ruído de NOTAS/LEGENDA/Torre 1/Torre 2 foi cortado fora antes do
`extract_from_raster`.

## (a) Causa raiz mais provável — guarda `len(strokes) > 200`

`classify/service.py:70-84` envolve `_remove_text_baselines`,
`_drop_orientation_imbalanced` E `_pair_merge_strokes` no mesmo gate
`if len(strokes) > 200`. O comentário admite que a guarda existe pra evitar
matar paredes em input já limpo.

**Bug**: a guarda agrupa três filtros com finalidades diferentes. ROI já
remove os blocos de texto que justificam os filtros 1 e 2 — então no path
ROI-aplicado o número de strokes pós-consolidação cai abaixo de 200
(planta_74: ~94 strokes pós-consolidate). O `_pair_merge_strokes` é pulado
junto. Sem pair-merge, a centerline nunca é sintetizada e o perimetral
real fica como duas faces órfãs, fragmentando a topologia downstream
(12 componentes, 7 órfãos, perímetro aberto).

`_pair_merge_strokes` JÁ tem proteção contra o caso "input limpo single-stroke"
via `_detect_hachura_indices` + `_PAIR_MIN_OVERLAP_RATIO=0.7` + janela
`[_PAIR_MIN_GAP=4, _PAIR_MAX_GAP=100]`. Logo, rodá-lo sempre é seguro:
strokes sem par compatível passam unchanged.

## (b) Patch proposto (mínimo)

```diff
--- a/classify/service.py
+++ b/classify/service.py
@@ -55,6 +55,7 @@ def classify_walls(
 ) -> list[Wall]:
     if not candidates:
         return []
+    n_in = len(candidates)

     if coordinate_tolerance is None:
         coordinate_tolerance = _infer_tolerance(candidates)

     # Stage 1: collapse redundant Hough detections of the same stroke.
     strokes = _consolidate_hough_duplicates(candidates, coordinate_tolerance)

-    # Filtros de ruido (text baselines + orientation imbalance) so fazem
-    # sentido em planta real bagunsada. Quando o input ja vem limpo
-    # (poucas centenas de candidatos), eles matam paredes legitimas.
-    if len(strokes) > 200:
-        strokes = _remove_text_baselines(strokes)
-        strokes = _drop_orientation_imbalanced(strokes)
+    # Noise filters: only kick in para input bagunsado. Mantem gate atual,
+    # mas reporta quando descartam acima do limiar pra nao mascarar bugs.
+    if len(strokes) > 200:
+        before = len(strokes)
+        strokes = _remove_text_baselines(strokes)
+        strokes = _drop_orientation_imbalanced(strokes)
+        if before and (before - len(strokes)) / before > 0.6:
+            import warnings as _w
+            _w.warn(
+                f"classify: noise filters dropped "
+                f"{before - len(strokes)}/{before} strokes (>60%)",
+                RuntimeWarning,
+            )

-    # Stage 4: drop strokes whose length / thickness ratio is too low to be
-    # a wall (blob-shaped glyph fragments and tick marks).
+    # Stage 4: aspect.
     strokes = _drop_low_aspect_strokes(strokes)

-    # Stage 5: pair parallel strokes que representam as 2 faces de uma
-    # wall double-line. Quando input ja vem limpo (single-stroke walls),
-    # esse merge causa falsos positivos e mata walls de banheiros pequenos.
-    if len(strokes) > 200:
-        wall_candidates = _pair_merge_strokes(strokes)
-    else:
-        wall_candidates = list(strokes)
+    # Stage 5: pair-merge SEMPRE roda. Plantas reais sao desenhadas em
+    # double-line independente de quanto ruido a pagina tem. Strokes sem
+    # par compativel (gap fora de [4,100] ou overlap < 0.7*max_len) passam
+    # unchanged, entao banheiros pequenos com single-stroke ja sao seguros.
+    before_pm = len(strokes)
+    wall_candidates = _pair_merge_strokes(strokes)
+    if before_pm and (before_pm - len(wall_candidates)) / before_pm > 0.8:
+        import warnings as _w
+        _w.warn(
+            f"classify: pair_merge consumed "
+            f"{before_pm - len(wall_candidates)}/{before_pm} strokes (>80%)",
+            RuntimeWarning,
+        )

     # Stage 6: aspect again.
     wall_candidates = _drop_low_aspect_strokes(wall_candidates)
```

## Hipóteses alternativas (descartadas mas possíveis)

2. **`extract.ExtractConfig.hough_max_line_gap=40` + perimetral interrompido
por portas/janelas largas.** Hough aceita gap de até 40 px; portas reais
rendem ~50–80 px. Sintoma seria perimetral em N segmentos colineares por
parede, NÃO duas linhas paralelas. Menos provável dado o source breakdown
acima, mas combina com o problema. Patch alternativo: subir
`hough_max_line_gap` para 80 (validar com `tests/`).

3. **ROI margin 5% inadequado para plantas com cota externa.** `roi/service.py:51`
usa `margin_ratio=0.05`. Se cota dimensional fica fora do componente principal,
ela é cortada — mas isso não fragmentaria o INTERIOR. Descartado: bbox ROI
(46,252)–(1159,916) cobre toda a planta visível em `raw_page.png`.

## (c) Plano de validação

1. Rodar `python main.py extract planta_74.pdf` pós-patch.
   Esperado: walls cai de 94 → ~40–55, com `paired_*` dominando.
   `connectivity_report.component_count` deve cair de 12 → ≤3.
2. Rodar `python run_p12.py` (PDF pré-vermelhado).
   Esperado: rooms ≥ 19 mantido, walls ≈ 35 ± 5 (regressão zero — input
   limpo continua passando estável pelo pair-merge porque sem pares
   compatíveis o filtro é no-op).
3. `pytest tests/` — qualquer fixture sintética que dependa do antigo
   short-circuit precisa ser revisada.
4. Comparar `debug_walls.png` antes/depois inline (pdf+skp side-by-side
   per regra do projeto).
5. Verificar warning emitido pelo gate dos filtros 1+2 quando rodando em
   PDF cru — confirma instrumentação ativa.

## Invariantes preservadas

- Não inventa walls: pair-merge só funde pares geométricos reais; sem par,
  stroke passa unchanged.
- Não acopla a planta_74: parâmetros (`_PAIR_*`, `>200`, novos limiares
  de warning 60%/80%) são genéricos.
- Warning emitido quando filtro descarta >60% (filtros 1+2) ou >80%
  (pair-merge) — atende a invariante "mudança gera warning quando filtro
  descarta >X%".
