# Caminhos quentes de geometria — medição e otimização (2026-10-22)

> Pedido do Felipe: "complexidade de tempo e espaço, se for bastante ganho, para facilitar a execução e os cálculos de
> geometria de cada componente". Regra seguida: **medir antes**, otimizar só o que pesa, e provar que o resultado é
> **idêntico** (nenhuma tolerância nova, nenhum atalho de geometria).

## Onde o tempo estava (cProfile de `room_regression_diff.capture()` — mobiliar a planta_74 inteira)

| Ponto | Chamadas | Tempo | Por quê |
|---|---|---|---|
| `circulation_gate.gate` | 95 | 3,7 s | busca binária da largura do gargalo: 5.042 testes de conectividade, **cada um** com `polygon.buffer(-w/2)` — 54 mil `buffer` (2,4 s), repetindo as mesmas larguras (0,50 / 1,00 / 0,75 / …) sobre o MESMO polígono (o cômodo vazio) em todos os portais e em todas as chamadas |
| `spatial_model.build_spatial_model` | 126 | 1,8 s | recalculava pegadas de parede, envelope e `compute_room_floors` (todos os cômodos) a cada chamada, para 11 cômodos |
| restante (shapely nos planners) | — | ~1,3 s | candidatos de posição; sem repetição exata a explorar sem mudar algoritmo |

Os outros testes "lentos" (2 s cada) eram timeout de porta fechada (oráculos offline), não geometria.

## O que mudou

1. **`circulation_gate._eroded_regions(polygon_wkb, width)`** — `lru_cache(maxsize=2048)` da erosão. É função pura de
   (forma, largura): a chave é o WKB do polígono, então outro móvel/outro cômodo gera outra chave. Custo de espaço limitado
   (≤ 2048 conjuntos de regiões). Busca binária por portal continua O(log((hi−lo)/tol)) ≈ 7 passos, mas cada passo repetido
   vira busca em dicionário em vez de `buffer` (que é O(n log n) nos vértices).
2. **`spatial_model._consensus_geometry(con)`** — pegadas, envelope e pisos de todos os cômodos calculados **uma vez por
   conteúdo de consensus** (sha1 do JSON, ~0,6 ms), com LRU de 8 plantas. Consensus editado no mesmo processo → outra
   chave → nunca reaproveita geometria velha. O dicionário devolvido a quem chama continua sendo novo a cada chamada (nada
   mutável compartilhado).

## Resultado (mesma máquina, mesma suíte)

| Medida | Antes | Depois |
|---|---|---|
| `capture()` da planta_74 (frio) | 5,25 s | **2,84 s** (−46%) |
| `capture()` (cache quente, 2ª chamada no processo) | 5,2 s | **2,23 s** (−58%) |
| `buffer` por captura | 54.405 | 46.592 (erosões: 4.188 acertos de cache × 854 cálculos) |
| `build_spatial_model` (126 chamadas) | 1,8 s | **0,33 s** |
| `test_variant_sweep` (sweep SU-free de 4 variantes) | 21,8 s | **11,2 s** |
| suíte `PT_TO_M=0.0259 -m planta74_scale` | 59,5 s | **32,6 s** |

**Igualdade provada:** o snapshot completo do apartamento (`capture()`: caixas por cômodo, gates, digests) serializado
antes e depois é **byte a byte idêntico**, na 1ª e na 2ª chamada. Testes de corretude dos caches em
`tests/test_geometry_hot_paths.py` (erosão = `buffer` direto; gargalo inalterado; chave por conteúdo; cache limitado).

## Por que não mexi em mais

- Nenhum dos dois pontos está no fecho de uma capacidade L2 (`tools.rooms.evidence_closure --explain` conferido): sem
  custo de refazer prova.
- O restante (~1,3 s em candidatos dos planners) exigiria mudar o algoritmo de busca (ex.: índice espacial `STRtree` por
  cômodo). Com ~10–20 obstáculos por cômodo o ganho esperado é pequeno e o risco de mudar a ordem dos candidatos (e com
  ela o layout escolhido) é real. Fica registrado como próxima microfase **só se** a planta crescer.
