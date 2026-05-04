# Plano — main-plan isolation no fluxo SVG integrado

## Context

Pipeline SVG integrado em `feat/svg-ingest` produz `rooms=54` em `planta_74m2.svg` (meta ~15-20). O delta não é problema estrutural de detecção — `geometry_score=1.0`, filtro `is_wall_interior` zerou slivers, pipeline é determinístico e reproduz os 3 blocos físicos do SVG. O excesso vem de **escopo**: o pipeline processa carimbo, legenda, mini-planta e rodapé como geometria igual à planta principal. Este plano resolve escopo sem mexer em detecção.

## 1. Diagnóstico

Os 54 rooms atuais dividem-se em duas classes:

- **Rooms reais da planta** (~18-22): no miolo central do overlay (R15-R36 aproximadamente — suíte, sala, cozinha, banheiros, área de serviço, circulação, etc.). São ciclos fechados em walls de fato da habitação.
- **Ciclos legítimos fora do escopo** (~32-36): `R1-R8` rodapé (carimbo + tabela de metragem), `R9-R14` cabeçalho (box do título), `R52-R54` mini-planta do pavimento. São retângulos fechados no SVG — o `polygonize` os detecta *corretamente*; apenas não pertencem ao apartamento.

A diferença crítica:

| | room falso estrutural | ciclo legítimo fora do escopo |
|---|---|---|
| Origem | artefato de algoritmo (sliver, imprecisão de pixel) | geometria real, desenhada assim no SVG |
| Assinatura | short_side ≈ wall_thickness | short_side normal; forma normal |
| Solução | filtro geométrico (`is_wall_interior`) | filtro de **escopo** (seleção de plano principal) |
| Estado atual | ✅ resolvido | ❌ pendente |

Nenhum dos 54 é estruturalmente inválido. Todos são polígonos bem-formados. O que falta é recortar *antes* do polygonize as walls que não pertencem ao apartamento.

## 2. Estratégia recomendada: maior componente conectado (após openings)

Entre as opções:

- **Maior connected component**: walls da planta formam um único grafo conectado (paredes se tocam em cantos). Carimbo/legenda são componentes separados. Depois que `detect_openings` adiciona bridges nas portas, o apartamento vira **um único componente consolidado**.
- **Cluster espacial** (DBSCAN): depende de parâmetro `eps` sensível a escala; não-determinístico em casos de empate. Risco.
- **Bbox do plano principal**: a ideia do `find_main_plan_bbox` do PoC. Depende de `unary_union` dos buffers, que pode fundir legenda e plano se estiverem próximos. Menos robusto semanticamente.
- **Combinação**: overhead sem ganho real.

**Escolha**: componente conectado de maior bbox-area (não por contagem de walls — legenda densa poderia vencer). Determinístico, O(V+E), explicável.

Por que bbox-area e não total-length: uma tabela de legenda pode ter muitas linhas curtas; o apartamento tem poucas linhas mas cobre área muito maior. Bbox-area é o discriminante natural entre "planta" e "anotação".

**Tie-breaker de segurança**: se a maior bbox-area não é pelo menos 3× a segunda maior, `select_main_component` retorna walls inalteradas (fallback seguro — nunca corta arbitrariamente em caso de dúvida).

## 3. Ponto exato de integração

**Depois** de `detect_openings`, **antes** de `build_topology`, dentro de `_run_pipeline_from_walls` em `model/pipeline.py`.

Justificativa:

- **Antes de detect_openings**: as bridges ainda não existem; paredes do apartamento separadas por portas formam 5-10 componentes pequenos. A seleção "maior" pode errar.
- **Depois de detect_openings**: bridges fecham os gaps das portas; apartamento vira 1-2 componentes grandes. Discriminação limpa.
- **Depois de build_topology/polygonize**: impossível distinguir sem voltar pras walls; além disso, o polygonize já terá gerado os 54 rooms — trabalho desperdiçado.

Resultado: `build_topology` recebe apenas walls do apartamento, gera apenas rooms do apartamento.

## 4. Heurística concreta

```
Input: walls: list[Wall] (já inclui bridges de detect_openings), wall_thickness: float
Output: list[Wall] filtrado

Passos:
  1. snap_tol = wall_thickness / 2
  2. Construir grafo G:
     - nós = endpoints das walls (quantizados em grid de snap_tol)
     - arestas = walls (endpoint_start, endpoint_end)
  3. components = connected_components(G)
  4. Para cada component c, calcular:
     - walls_in_c = walls cujos endpoints ambos pertencem a c
     - bbox = união dos bbox das walls em c
     - bbox_area = bbox.width * bbox.height
  5. Ordenar components por bbox_area desc
  6. main = components[0]
  7. Se len(components) >= 2 e bbox_area(components[0]) < 3.0 * bbox_area(components[1]):
       return walls  # fallback: não existe componente dominante claro
  8. return walls_in_main
```

- Determinístico (componentes ordenados por índice de nó).
- O(V+E) via `networkx.connected_components`.
- Nenhum threshold específico por PDF. A razão 3.0 é genérica (planta típica é >>3× qualquer anotação).
- Loga: número de componentes, bbox_area do vencedor, razão vs segundo lugar.

## 5. Critérios de segurança

A heurística **nunca** pode cortar:

1. **Cômodos conectados por porta** — garantido porque `detect_openings` adiciona bridges *antes* do filtro.
2. **Banheiro periférico / área de serviço pequena** — garantido porque são parte do grafo conectado do apartamento.
3. **Bloco com pequena descontinuidade** — se está próximo e dentro do bbox, pertence ao componente principal (após bridges).
4. **Plantas com 2 blocos legítimos** (ex: apê + varanda desconectada por uma escada) — capturado pelo guard de fallback: se a bbox_area do #2 é >= 33% da #1, retorna walls inalteradas.
5. **Casos sem anotação** (SVG "limpo") — único componente é o maior por default, filtro é no-op.

Additional: **jamais** aplicar este filtro no pipeline raster. Raster já tem `detect_architectural_roi` fazendo papel análogo via CV na imagem. Rodar os dois seria redundante e potencialmente prejudicial.

## 6. Plano de implementação

### Passo 1 — novo módulo
`D:\Claude\svg_poc\feat-svg-ingest\topology\main_component_filter.py` (~60 LOC):

```python
def select_main_component(
    walls: list[Wall],
    snap_tolerance: float,
    dominance_ratio: float = 3.0,
) -> tuple[list[Wall], dict]:
    """Returns (filtered_walls, report) where report contains:
      component_count, selected_bbox_area, second_bbox_area,
      dominance_applied: bool, walls_dropped: int.
    """
```

Retorna tupla (walls_filtradas, report_dict) pra permitir logging no caller sem side-effects.

### Passo 2 — wiring em `model/pipeline.py`

Dentro de `_run_pipeline_from_walls`, **apenas** nesse fluxo:

```python
walls, openings = detect_openings(walls, ..., wall_thickness=wall_thickness)
walls, main_component_report = select_main_component(
    walls, snap_tolerance=wall_thickness / 2
)
observed_model["metadata"]["main_component"] = main_component_report  # logging
split_walls, junctions, rooms, connectivity_report = build_topology(...)
```

`run_pdf_pipeline` e `_run_pipeline` (caminho raster) **não** recebem nenhuma mudança.

### Passo 3 — tests

`D:\Claude\svg_poc\feat-svg-ingest\tests\test_main_component_filter.py`:

1. `test_drops_isolated_small_component`: apartamento (5 walls grande bbox) + legenda (5 walls bbox 10×10). Filtro mantém só o apartamento.
2. `test_fallback_when_no_dominant`: dois componentes com bbox-area próximas. Filtro retorna walls inalteradas.
3. `test_single_component_is_noop`: 1 componente → retorna os mesmos walls.
4. `test_report_has_expected_shape`: report dict tem todas as chaves.

Adicional em `tests/test_svg_pipeline.py` (já existe): atualizar `test_pipeline_on_minimal_room` para também exercitar o novo filtro (minimal_room tem 1 componente → passa pelo caminho do fallback/no-op).

### Passo 4 — artefato comparativo

Script read-only `runs/compare_before_after_main_filter.py` (não commitado — só artefato local) gerando PNG lado-a-lado pré-filtro vs pós-filtro.

Nenhuma mudança em `main.py`, `api/app.py`, `openings/`, `extract/`, `classify/`, `roi/`, `ingest/service.py`.

## 7. Plano de validação

### Métricas (pipeline SVG em `planta_74m2.svg`)

| | antes | depois (alvo) |
|---|---:|---:|
| rooms | 54 | 15-20 |
| walls | 359 | 180-240 |
| junctions | 142 | 70-110 |
| openings | 68 | 25-40 |
| geometry_score | 1.0 | 1.0 (inalterado) |
| topology_score | 0.35 | **↑** (menos orphans) |
| warnings | `[walls_disconnected]` | `[]` ou só notes |

Meta forte: `rooms in [15, 20]`. Fora desse range = rollback candidato.

### Artefatos visuais
- `runs/svg_planta74m2_main_only/overlay_audited.png` (novo baseline)
- `runs/compare_before_after_main_filter.png` (lado a lado)
- `runs/svg_planta74m2/` preservado como evidência "sem filter"

### Regressão no raster
- `pytest tests/` deve continuar em 97 pass / 15 pre-existing fail
- `python main.py extract planta_74.pdf --out runs/raster_ctrl` deve produzir saída byte-por-byte idêntica ao pré-filtro (raster não é afetado)

### Prova de correção semântica

1. **Visual**: overlay_audited.png do SVG não contém nenhum carimbo/legenda/mini-planta
2. **Numérico**: `observed_model.metadata.main_component.dominance_applied == True` e `walls_dropped` entre 100-180
3. **Estabilidade**: rodar 3× seguidos dá output byte-idêntico (determinismo)

## 8. Condição de rollback

Abandonar e reverter o commit se qualquer um acontecer:

1. **`rooms < 10`** — filtro cortou cômodo real
2. **`rooms > 30`** — filtro não funcionou (legenda ainda presente)
3. **Algum cômodo visualmente identificável do PoC v5 sumiu** no overlay (comparação manual side-by-side)
4. **`topology_score` piorou** (não deveria; filtro só remove walls "desconectadas" do main)
5. **Raster pipeline regride** (jamais deveria, mas guard de sanidade)
6. **Teste `test_fallback_when_no_dominant` falha** — filtro está sempre cortando, falta o tie-breaker de segurança

Rollback = `git reset --hard HEAD~1` na branch `feat/svg-ingest`. Pipeline SVG volta a 54 rooms. Próxima tentativa: investigar se bbox-area deveria ser substituído por outra métrica (ex: `hull_area / bounding_box_area` = solidez) ou se filtro deveria rodar em fase diferente.

## Out of scope

- Não refactorar `_run_pipeline_from_walls` ou `_run_pipeline` (compartilhamento de código entre paths — tema separado se desejado)
- Não aplicar `select_main_component` no caminho raster (ROI já cobre)
- Não parametrizar `dominance_ratio` via CLI/config (constante 3.0 é o padrão; só expor se valor se mostrar insuficiente em múltiplas plantas)
- Não detectar semanticamente "carimbo" ou "legenda" (overengineering — a heurística de bbox já resolve indiretamente)

## Arquivos do plano

- **Novo**: `topology/main_component_filter.py` (~60 LOC)
- **Novo**: `tests/test_main_component_filter.py` (4 tests, ~60 LOC)
- **Modificado cirurgicamente**: `model/pipeline.py` (+3 linhas em `_run_pipeline_from_walls`)
- **Intocado**: tudo mais (raster, classify, extract, roi, ingest, api, main)

## Impacto esperado no produto

Pós-integração, pipeline SVG produz artefato visual limpo (só apartamento), contagens dentro de range arquitetônico, warnings vazios. O contrato `observed_model.json` ganha um campo `metadata.main_component` (backward compat — campo novo, clientes ignoram se não esperam).

Isso fecha o ciclo PoC → produto para o input `planta_74m2.svg`. Próxima fronteira (fora deste plano): múltiplos SVGs de origens diferentes, plantas multi-pavimento, detector de arco de porta para reduzir openings.
