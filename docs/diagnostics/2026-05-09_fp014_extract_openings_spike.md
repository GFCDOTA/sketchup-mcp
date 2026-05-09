# FP-014 — spike detector: por que `extract_openings_vector` perde peitoris

> **Achado:** o filtro `WINDOW_WALL_LEN_RATIO_MAX = 0.7` descarta
> peitoris longos paralelos a walls, mesmo quando a forma é
> claramente uma janela. Combinado com walls fragmentados (FP-014
> Sintoma B), peitoris contínuos como `PEITORIL H=1,10M` (3.82m)
> NUNCA são detectados.
>
> **Status:** documentado, sem fix. P2 do FP-014 (refinar
> `extract_openings_vector`) continua na fila depois de Opção α
> (refactor `build_vector_consensus`).

## Reprodução

Spike usa `tools/structural_checks` + leitura direta de PDF paths:

```python
import pypdfium2 as pdfium, pypdfium2.raw as pdfium_c, ctypes
pdf = pdfium.PdfDocument('planta_74.pdf')
page = pdf[0]

# Region of PEITORIL TERRACO SOCIAL (bottom edge of envelope)
REGION = (40, 390, 270, 415)
for obj in page.get_objects():
    if obj.type != 2: continue
    l, b, r, t = obj.get_pos()
    cx, cy = (l+r)/2, (b+t)/2
    if not (REGION[0] <= cx <= REGION[2] and REGION[1] <= cy <= REGION[3]):
        continue
    # Inspect drawmode + segments
    raw = obj.raw
    fm = ctypes.c_int(0); st = ctypes.c_int(0)
    pdfium_c.FPDFPath_GetDrawMode(raw, ctypes.byref(fm), ctypes.byref(st))
    print(f'{(l,b,r,t)} fill={fm.value} stroke={st.value}')
```

**Saída na região do PEITORIL:**

```
obj  type   bbox                                   size       fill stroke nseg ncubic
367  path  ( 49.2, 401.9, 103.1, 407.3)  53.9x  5.4    2   0    7      2  -- WALL (filled)
368  path  ( 48.7, 401.4, 103.6, 407.8)  54.9x  6.4    0   1    8      2  -- outline
490  path  (103.4, 403.1, 259.6, 406.0) 156.1x  2.9    0   1    5      1  -- WINDOW candidate (long, thin, stroked)
491  path  (103.4, 400.6, 262.1, 408.5) 158.7x  8.0    0   1    4      1  -- WINDOW candidate
500  path  ( 54.1, 406.8,  60.0, 412.7)   5.9x  5.9    0   1    2      1  -- pequeno (pilastra?)
501  path  ( 72.8, 406.8,  78.7, 412.7)   5.9x  5.9    0   1    2      1
```

Há **2 caminhos stroked elongados** que passariam pelo classificador
de window:
- path 491: **158.7 × 8.0**, aspect = 19.8 — clássico window-shape
- path 490: 156.1 × 2.9 (short_side = 2.9 < THICK*1.5 = 8.1, OK)

Ambos satisfazem:
- `WINDOW_LONG_MIN(25) <= long_side <= WINDOW_LONG_MAX(250)` ✓
- `short_side <= thickness * WINDOW_DEPTH_FACTOR(1.5) = 8.1pt` ✓
- `aspect >= WINDOW_ASPECT_MIN(3.0)` ✓

**Mas são descartados pelo filtro:**

```python
# tools/extract_openings_vector.py
WINDOW_WALL_LEN_RATIO_MAX = 0.7  # drop window if long_side >= this
                                  # fraction of the wall — likely a
                                  # wall outline stroke
```

## Por que o filtro mata peitoris longos

Na região do PEITORIL TERRACO SOCIAL:
- Wall mais próxima: **path 367 (filled, 53.9pt long)** — pedaço da
  parede paralela ao peitoril
- Window candidate path 491: **158.7pt long**
- Ratio: **158.7 / 53.9 ≈ 2.9**, **MUITO maior que 0.7** → DESCARTADO

O filtro foi desenhado para evitar falsos positivos (wall outline
stroke), mas tem efeito colateral catastrófico em peitoris contínuos:
- Peitoril contínuo de 3.82m + walls fragmentadas curtas →
  `peitoril_long / wall_curto >> 0.7` sempre
- Resultado: 100% dos peitoris longos são descartados

## Combinação fatal com Sintoma B (wall fragments)

FP-014 Sintoma B documentou: **14/33 walls < 1m, alguns 26 cm**.
Esse é o WINDOW_WALL_LEN_RATIO_MAX evaluator olhando para "wall
length", e wall length é tipicamente o fragment próximo (não o wall
inteiro original pre-carving).

Resultado em planta_74:
- **PEITORIL TERRACO SOCIAL** (3.82m, expected as window) → não
  detectado (ratio com wall_curto >> 0.7)
- **PEITORIL TERRACO TECNICO** (~1.20m) → não detectado
- **JANELA SUITE 01 INFERIOR** (~1.40m) → talvez não detectado
- Etc.

## Por que ele foi escolhido assim

O filtro existe para evitar que o stroked outline da própria wall
seja detectado como window. Em PDFs simples, walls têm:
- Path filled (corpo da wall) — vira wall no consensus
- Path stroked (outline da wall) — descartado pelo filtro

Em PDFs com peitoris/janelas longas:
- Path filled (wall fragmento curto, comprimento similar ao peitoril)
- Path stroked (peitoril/janela longo) → descartado erroneamente

O filtro foi calibrado para o caso simples; falha no caso real com
peitoris.

## Mitigações possíveis (NÃO IMPLEMENTAR sem decisão Felipe)

### A — diminuir/remover `WINDOW_WALL_LEN_RATIO_MAX`
**Risco:** wall outlines stroked viram falsos positivos windows.
Precisa testar em todo o corpus synth + planta_74. Hoje o detector
emite 11 openings; sem o filtro pode emitir muito mais (ruidoso).

### B — comparar contra wall TOTAL (post-merge), não wall_segment
Após merge dos colinear pairs (ver `_find_colinear_gaps` em
`tools/structural_checks.py` C8), comparar window long_side
contra a wall LÓGICA total (peitoril 3.82m vs wall total 5m =
ratio 0.76 — ainda > 0.7 mas próximo do limite). Continua perdendo
casos como PEITORIL TERRACO 3.82m vs wall total ~4m (ratio 0.95).

### C — separar window candidates de peitoril candidates
Adicionar PEITORIL como classe distinta. Heurística: stroke + low
height + height ~= peitoril typical (PEITORIL H=1.10M no PDF
indica que o symbol em PDF é desenhado com altura proporcional →
não usar "near wall thickness" como filtro).

Esse é o caminho do **detector real**: tratar peitoril como tipo
distinto (não tentar caber em window).

### D — depender 100% de soft_barrier detection
soft_barriers já são detectados (8 no consensus atual, incluindo o
peitoril TERRACO via sb000 com 30 vértices). Talvez **promover
soft_barriers a openings** (`kind_v5: peitoril`) seria caminho
mínimo. Não muda detector, só pós-processa.

## Status

🔴 Peitoris não detectados como openings (Sintoma C do FP-014).
🟡 4 mitigações propostas (A/B/C/D). Sem implementação.
🟢 Gate γ (PR #105) já bloqueia SKP defeituoso por outras razões;
  perda de peitoris contribui para `unmapped_colinear_gaps_count`
  (C8) que é blocker.

## Recomendação

Mitigação **D** (promover soft_barriers a openings de tipo
`peitoril`) é o **menor fix**:
- Não muda detector
- Não muda thresholds
- Pure pós-processo: `for sb in soft_barriers: emit opening with
  kind_v5='peitoril', wall_id=nearest_wall, opening_width_pts=sb_length`
- Resolve apenas o caso "soft_barrier exists but kind missing"

Se Felipe quiser implementar D em PR pequeno (~80 LOC), avisar.
Mitigação A é arriscada (falsos positivos), B/C são refactor maior.

## Próximo passo (decisão Felipe)

1. Implementar mitigação D? (soft_barrier → peitoril opening)
2. Adiar até P0 Opção α (refactor `build_vector_consensus`) que
   pode resolver as 4 famílias junto?
3. Continuar refinando MY_OPENINGS visualmente até PDF e PNG
   serem visualmente idênticos?

Eu recomendo **opção 3** primeiro — gerar v3 com correções extras
identificadas + validar com Felipe → só DEPOIS decidir entre 1/2.

## Refs

- FP-014: `docs/diagnostics/2026-05-09_skp_visual_failure_fp014.md`
- GPT validation: `..._gpt_validation.md`
- γ gate (já mergeado PR #105): `tools/structural_checks.py`
- Repro script: `..._fp014_repro.py`
- MY_OPENINGS v2 (refinado pós-GPT): mesmo script linha ~106
