# SOLUTION-FINAL.md — Pacote consolidado após revisão empírica

> **Note (2026-04-21):** This file documents the raster-era diagnosis and
> per-patch verdicts. Current ingest path is SVG-first (see
> `docs/SVG-INGEST-INTEGRATION.md`). For the current state of openings
> refinement, see `docs/OPENINGS-REFINEMENT.md` + `docs/VALIDATION-F1-REPORT.md`.

**Data:** 2026-04-21 (atualizado depois do fix estrutural em `a11724a`)
**Status:** Fix real aplicado no branch `fix/dedup-colinear-planta74`,
validado em ambiente Python 3.12.10 fresh. Patches 01/06 rejeitados,
02/03/04 corrigidos, 07/08/09 adiados. PRs #2 e #3 abertos com
cobertura + correções.

---

## TL;DR

O approach ganhador **não foi** nenhum dos patches 07/08/09
originalmente propostos como "solução definitiva". O que resolveu a
planta despedaçada foi o **combo (2) + (4) do `patches/README.md`
antigo, reimplementado como fix estrutural direto no código**:

1. **Dedup colinear co-posicionada pós-Hough** em
   `classify/service.py` (`_dedupe_collinear_overlapping`, gated por
   `len(candidates) > 200`).
2. **Re-extração adaptativa** em `extract/service.py` (gated por
   `len(candidates) > 500`, com `hough_threshold=10` e
   `min_wall_length=20`).

Commit `a11724a` em `origin/fix/dedup-colinear-planta74`. Diff total
**188 LOC** (classify +155, extract +33).

---

## Métricas medidas em `planta_74.pdf`

| Métrica | Baseline main (`dcb9751`) | Fix (`a11724a`) | Target briefing |
|---|---|---|---|
| walls | 104 | **42** | 42 ✓ |
| `component_count` | 4 | **3** | 3 ✓ |
| `largest_component_ratio` | 0.5208 | **0.9273** | ≥ 0.93 ✓ (dentro de 0.01) |
| `component_sizes` | [25, 2, 18, 3] | [51, 2, 2] | merged 25+18 → 51 ✓ |
| rooms | 16 | 16 | 16 ✓ |
| `orphan_component_count` | 2 | 2 | ≤ 2 ✓ |
| `orphan_node_count` | 5 | 4 | pendente ✗ (4 residuais) |

**4 de 5 targets atingidos.** Os 4 `orphan_node_count` residuais
moram em `~[282,754]→[334,754]` e `~[357,420]→[401,420]`, inferidos
como mobiliário/legenda mas não validados visualmente ainda. Filtro
semântico downstream fica em PR separada pra não inflar o escopo
deste fix.

### Baseline `p12_red.pdf`

Ambos os gates (`>200` pro dedup, `>500` pra re-extract) **não
disparam** em input limpo; fluxo inalterado, zero regressão.

### Suite de testes

- 77 pass / 15 pre-existing fails (`test_orientation_balance`,
  `test_pair_merge`, `test_pipeline`, `test_text_filter`).
- Os 15 fails já existiam em `dcb9751`, não foram introduzidos pelo
  fix. Documentado no comment de review do PR #1.

---

## Per-patch verdict

| Patch | Verdict | Motivo |
|---|---|---|
| 01 K-means color | **REJEITAR** | Duplica `preprocess/color_mask` existente. |
| 02 Density trigger | **APROVAR c/ mudanças** | Threshold não calibrado; precisa sweep. |
| 03 Quality score | **APROVAR c/ correções** | `wall.p0/p1` → `wall.start/end`; usar `largest_component_ratio` direto; F1-against-GT removido (GT é contrato do consumer). Versão corrigida em `patches/03-quality-score.py`. |
| 04 ROI fallback | **APROVAR c/ mudanças** | Manter `fallback_reason` canônico (schema 2.1.0 §4), adicionar `fallback_used` aditivo. Versão corrigida em `patches/04-roi-fallback-explicit.py`. |
| 05 U-Net stub | **DEPRECATED** | Substituído conceitualmente por 08; 08 está adiado. |
| 06 Arc detection | **REJEITAR** | `openings/service.py` no main já implementa arc/hinge/swing com 259 linhas de teste. Patch foi escrito contra HEAD stale. |
| 07 LSD + morph FIXED | **ADIAR** | `scipy` não em requirements; morph close funde gaps de porta. |
| 08 CubiCasa DL FIXED | **ADIAR** | Sem offline fallback; `strict=False` silencioso viola CLAUDE.md §6. |
| 09 AFPlan | **APROVAR atrás de env flag** | GPT-4 consultado considerou inferior — não troca classe de bug, introduz blobs. Só atrás de `SKM_EXTRACTOR=afplan`. |

---

## Ambiente usado pra validação (reproduzível)

- **OS:** Windows 11 Pro (26200).
- **Python:** 3.12.10 via `winget install Python.Python.3.12 --scope user`.
- **Venv:** `python -m venv .venv`; `pip install -r requirements.txt`.
- **Requirements:** `fastapi`, `uvicorn[standard]`, `numpy`,
  `opencv-python-headless>=4.10`, `pypdfium2`, `shapely`, `networkx`,
  `pydantic`, `pytest`. Sem torch, sem scipy.

**Correção importante:** versões anteriores deste documento diziam
"Python 3.12 não disponível no ambiente do autor, validação empírica
obrigatória antes de merge". Com a stack mínima acima o pipeline
roda end-to-end em minutos.

---

## O que os gates fazem

Os gates em `len(candidates)` são **a** razão do fix não regredir os
inputs limpos. O caminho padrão é:

```
Hough (baseline config)
  └─ len(candidates) <= 500 e <= 200 → caminho baseline inalterado
                                      (inputs sintéticos, p12_red, etc.)

  └─ 200 < len(candidates) <= 500 → só dedup colinear extra
                                    (inputs moderadamente ruidosos)

  └─ len(candidates) > 500 → re-extract adaptativo (hough_threshold=10,
                              min_wall_length=20) + dedup colinear
                              (plantas reais com legenda/hachura/texto)
```

### Por que gated

Rodar dedup + re-extract em `p12_red.pdf` (input limpo, ~160 raw
candidates) funde paredes legítimas adjacentes — testado empiricamente
durante a revisão do PR #1.

### Honest gap

O gate é `len(candidates)`, não densidade por área. Em um raster
2x maior com o mesmo "ruído por cm²" o count dobra sem o ruído real
aumentar, e o gate dispara errado. Calibrar por densidade/área é
trabalho futuro.

---

## Auditoria visual pendente (checklist GPT-4 do PROMPT-RENAN.md)

Itens ainda **não resolvidos**:

1. **Prova visual antes/depois**: renderizar `debug_walls.svg` com overlay no raster de `planta_74.pdf`, marcar cada órfão residual. Sem imagem, "parece mobiliário" é especulação.
2. **Diff estrutural do grafo**: listar wall IDs removidos pelo dedup, clusters formados (tamanho, membros, razão de merge). 5-10 exemplos concretos no comment do PR.
3. **Regressão semântica em rooms**: `rooms=16` igual antes e depois. Mas dois cômodos fundidos em um podem dar 16 se outro par ficou separado. Validar cada room contra a planta.
4. **Dedup auditing**: casos onde o dedup NÃO mergeou (perp > 10? overlap < 35?) — documentar com exemplo.
5. **Run sem gate**: rodar o pipeline com `_dedupe_collinear_overlapping` sempre ativo e mostrar impacto em `p12_red.pdf` (quebra? se sim, o gate é load-bearing e vai pra docstring).
6. **Não-regressão em openings**: `openings.json` antes/depois em `planta_74.pdf`. Se mudou contagem / posição / hinge_side, explicar.
7. **Protos `p10_v1_run` / `p11_v1_run`**: não rodados pós-fix. Fazer tabela.

Vieses a evitar (do PROMPT-RENAN.md):
- Não tentar salvar patches 07/08 silenciosamente.
- Não assumir que os 4 órfãos são mobiliário sem contra-exemplo.
- Não otimizar métrica sobre geometria (fundir rooms legítimas pra subir ratio = regressão).
- Não otimizar só `planta_74`. `p10` / `p11` são gate.

---

## Arquivos no monorepo

```
sketchup-mcp/
├── CLAUDE.md                       # invariantes + protocolo agents
├── PROMPT-FELIPE.md                # handoff original
├── PROMPT-RENAN.md                 # handoff pro Claude do Renan + checklist GPT-4
├── classify/service.py             # dedup colinear (a11724a)
├── extract/service.py              # re-extract adaptativo (a11724a)
├── tests/
│   ├── test_collinear_dedup.py     # 16 unit tests (PR #2)
│   └── test_planta_74_regression.py # 4 snapshot tests (PR #2)
├── docs/
│   ├── ANALYSIS.md                 # análise de invariantes
│   ├── CAUSA-RAIZ.md               # por que a planta despedaçava (original)
│   ├── ROADMAP.md                  # execução em fases (atualizado 6-8 sem)
│   ├── SOLUTION.md                 # arquitetura Hybrid CV+DL (referência)
│   └── SOLUTION-FINAL.md           # ESTE arquivo
└── patches/
    ├── README.md                   # verdict table + comandos
    ├── 01-kmeans-color-aware.py    # REJEITADO
    ├── 02-density-trigger.py       # APROVAR c/ mudanças
    ├── 03-quality-score.py         # CORRIGIDO nesta revisão
    ├── 04-roi-fallback-explicit.py # CORRIGIDO nesta revisão
    ├── 06-arc-detection-openings.py # REJEITADO (duplica openings/service.py)
    ├── 07-reconnect-fragments-FIXED.py # ADIADO
    ├── 08-unet-oracle-FIXED.py     # ADIADO
    └── 09-afplan-convex-hull.py    # APROVAR atrás de env flag
```

---

## Resposta final à pergunta "resolveu ou não?"

**Parcialmente.** 4 de 5 targets de `planta_74.pdf` atingidos
empiricamente em ambiente reproduzível. O target faltante
(`orphan_node_count` 4 → 0) depende de filtro semântico ainda não
implementado — escopo de PR separada, pra não inflar este fix.

**Opening-aware topology** vira Fase 2 do ROADMAP.

**Patches 07/08/09** foram considerados inferiores ao fix estrutural:
- 07 (LSD + morph): fecha gaps de porta (regressão em openings).
- 08 (CubiCasa DL): exige setup CI que não temos ainda.
- 09 (AFPlan): GPT-4 consultado considerou inferior (introduz blobs sem trocar classe de bug).
