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

## Rodada 2 (2026-10-23) — busca de posição: invariantes fora do laço, índice espacial e podas exatas

Perfil do `develop` depois da rodada 1: ~300 mil chamadas individuais ao shapely, concentradas em dois laços de busca.

| Onde | Antes | Problema (DSA) | Mudança exata |
|---|---|---|---|
| `service/layout._table_set` (mesa do terraço) | 1,23 s | `p.buffer(pm)` de cada obstáculo e `zone.buffer(-0.02)` recalculados **para cada ponto da grade × diâmetro** (invariante dentro do laço); teste de obstáculo linear O(C·O); `intersection(circ).area` mesmo sem contato | buffers e polígonos preparados calculados 1× por chamada; `STRtree` com predicado `intersects` (O(log O), mesmo resultado do `any(...)`); intersecção só com contato; **poda**: disco contido ⇒ centro contido, testa o centro (ponto × polígono preparado) antes de construir o círculo |
| `living/furnishing._candidate` (jantar da sala) | 1,09 s | moldes da mesa/cadeira refeitos por candidato; união de ~40 polígonos por candidato só para saber se encosta em móvel | moldes 1× por chamada; união só quando algum polígono toca a ocupação (`shapely.intersects` vetorizado contra polígono preparado — sem contato a área é 0); **poda**: candidato exige exatamente 2 assentos, então conta as cadeiras que cabem antes de montar as ~45 caixas (a checagem original continua como rede de segurança) |

**Resultado (3 rodadas intercaladas, mesma máquina, processo novo a cada medição):**

| Mobiliar a planta_74 inteira | antes de tudo (`af910c7`) | rodada 1 (`456bea7`) | rodada 2 |
|---|---|---|---|
| 1ª chamada (fria) | 5,30 s | 2,86 s | **2,06 s** (−61%) |
| chamadas seguintes (quente) | 5,16 s | 2,27 s | **1,50 s** (−71%) |
| saída | `c2a57f92…` | `c2a57f92…` | `c2a57f92…` — **idêntica** |

Suíte `planta74_scale`: 59,5 s (antes de tudo) → 32,6 s (rodada 1) → **27,7 s**; sweep SU-free de 4 variantes: 21,8 s → 11,2 s → **9,4 s**.
Prova adicional: `tests/test_layout_search_pruning.py` compara o `_table_set` novo com a implementação antiga **literal** em 7 zonas
(livre, obstáculos, circulação, L, nada cabe, desce para 0,80 e 0,60 m) — saída igual em todas.

**O que ficou de fora (de propósito):** o gate de circulação ainda é chamado por candidato da grade da sala (~0,9 s em 95
chamadas). Podar isso exigiria mudar a ordem/estratégia da busca — e com ela, potencialmente, o layout escolhido. Também não
cacheei o modelo espacial inteiro por cômodo: o ganho (~0,2 s) não paga o estado escondido que vazaria entre testes que fazem
monkeypatch no construtor.

## Rodada 3 (2026-10-23) — estratégia da busca da mesa de jantar (aprovação visual do Felipe)

Mudança de **estratégia** (não só de implementação), por isso com antes/depois visual em
`artifacts/review/perf/dining_search_2026-10-23/`. O gate de circulação era chamado 95× na busca da mesa; o mapa exaustivo
mostrou que 83 reprovam só por corredor (poda pelas cadeiras: ~10%, descartada) e que 67 chamadas eram do refinamento ao
redor de uma âncora já no limite do corredor (0,81 m p/ 0,80 m). Agora o refinamento começa pela âncora de **maior folga de
corredor** (`circulation_gate.corridor_slack_m`): 95 → **37** chamadas, mesma posição escolhida, snapshots idênticos.

| Mobiliar a planta_74 inteira | antes de tudo | rodada 1 | rodada 2 | **rodada 3** |
|---|---|---|---|---|
| fria | 5,30 s | 2,86 s | 2,06 s | **1,20 s** (−77%) |
| quente | 5,16 s | 2,27 s | 1,50 s | **0,95 s** (−82%) |

Suíte `planta74_scale`: 59,5 s → **24,7 s**. Trava determinística: a busca chama o gate no máximo 40 vezes.

## Rodada 4 (2026-10-23) — sessão do gate: cada checagem pela metade do custo, mesmo veredito

Pergunta do Felipe: "não dá pra diminuir essas chamadas?". Medido: cada checagem custava ~5,4 ms, e até um FAIL nas
cadeiras custava 4,3 ms — o custo era **fixo e repetido**: refazer o modelo espacial da sala e as pegadas dos ~90 móveis
parados em cada uma das 37 checagens, quando só a mesa candidata muda.

- `circulation_gate.GateSession(con, base, sala)`: modelo espacial, célula, portais (e seus papéis) e bloqueios da mobília
  fixa calculados **uma vez, de forma preguiçosa** (só na 1ª checagem — anotar antes mudava `_semantics_provenance` de
  caixas que nenhum candidato chegou a testar; o hash pegou). `gate()` virou `GateSession(con, [], sala).check(boxes)`.
- `decide_only=True` (buscas): cadeiras primeiro e parada no primeiro portal que reprova; num PASS calcula tudo.
- As duas buscas da sala (mesa de jantar em modo decisão; mesa de centro em modo completo) usam a sessão.

| | antes (develop) | depois |
|---|---|---|
| custo por checagem do gate | 5,4 ms | **2,7 ms** |
| gate na busca (37 checagens) | 0,20 s | **0,10 s** |
| mobiliar o apartamento (fria / quente) | 1,20 / 0,95 s | **1,04 / 0,83 s** |
| saída | `c2a57f92…` | `c2a57f92…` (idêntica) |

**Por que não reduzir o NÚMERO de checagens:** as 28 da grade são todas as posições válidas da mesa na sala (passo de
15 cm) e só 2 passam no gate — a região viável é minúscula. Grade mais grossa pularia essa região e a mesa sairia da sala;
o ganho de tempo restante (≤ 0,1 s) não paga esse risco. Prova: `tests/test_layout_search_pruning.py` — sessão e gate
completo com saída idêntica em todos os cômodos da planta; modo decisão com o mesmo veredito; sessão preguiçosa.

**Acumulado (mesma máquina):** mobiliar a planta_74 inteira 5,30 s → **1,04 s** (fria, −80%) e 5,16 s → **0,83 s** (quente, −84%).
