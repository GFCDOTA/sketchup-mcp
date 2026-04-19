# plan-extract-v2

Microservico novo, desacoplado de legado, para extrair geometria observada de plantas em PDF e produzir um modelo canônico auditável.

## Objetivo

O pipeline foi separado em estagios independentes e testaveis:

`PDF -> ingest -> extract -> classify -> topology -> model -> debug`

Premissas mantidas no codigo:

- nao inventar rooms
- nao esconder `rooms=[]`
- nao usar bounding box como substituto de room
- nao adaptar o codigo a um PDF especifico
- reportar falhas explicitamente

## Estrutura

- `api/`: FastAPI com `POST /extract`
- `ingest/`: leitura e rasterizacao do PDF
- `extract/`: extracao de segmentos de parede a partir de raster
- `classify/`: consolidacao e merge de candidatos em paredes canonicas
- `topology/`: grafo, junctions, conectividade e polygonize
- `model/`: montagem do `observed_model.json` e orquestracao
- `debug/`: geracao obrigatoria de SVGs e relatorio de conectividade
- `tests/`: testes sinteticos em memoria, sem PDF real

## Decisoes Tecnicas

1. Ingest faz rasterizacao com `pypdfium2`.
2. Extract trabalha sobre raster binario e usa morfologia para localizar linework horizontal e vertical.
3. Classify nao tenta inferir semantica arquitetonica. Tudo que passa aqui continua sendo geometria observada de parede.
4. Topology divide paredes nas intersecoes, monta grafo e roda `polygonize` para detectar rooms reais.
5. Se `polygonize` nao gerar poligonos fechados, `rooms` permanece vazio. Isso e tratado como informacao observada, nao como correcao silenciosa.
6. Debug artifacts sao sempre escritos:
   - `debug_walls.svg`
   - `debug_junctions.svg`
   - `connectivity_report.json`

## Estado Atual e Limitacoes

O servico esta preparado para ser honesto e depuravel, mas ainda nao resolve todos os casos do mundo real.

### Pipeline classify (seis estagios)

1. Consolidate Hough duplicates (cluster por coord perpendicular com tolerance = max(4.0, median thickness)).
2. Text-baseline filter (chains de 3+ strokes paralelos com gap uniforme e overlap >= 20 px).
3. Orientation dominance filter multi-scale (120 e 240 px cells; drop curtos em ratio >=4:1; drop todos em ratio >=10:1).
4. Aspect ratio filter (drop strokes com length < 2 x thickness).
5. Pair-merge (combina duas faces paralelas de uma parede em uma centerline).
6. Aspect ratio filter novamente (aplica a centerlines sintetizadas pelo pair-merge).

### Pipeline topology

- `_split_walls_at_intersections` + snap (radius = 1.5 x median thickness).
- Per-page graph: junctions, connectivity, polygonize.
- `min_area = (2 x median_thickness)^2` para rejeitar slivers degenerados.
- `orphan_component_count` e `orphan_node_count` reportados sem dropar evidencia.
- Warning `many_orphan_components` dispara com >= 5 componentes com <=3 nos.

### Limitacoes observadas

- A extracao atual e mais forte para linework ortogonal em raster.
- Elementos inclinados, curvos ou muito degradados podem nao ser extraidos corretamente.
- PDFs de folha unica com blocos paralelos nao-planta (NOTAS, LEGENDA, TORRE 2, rodape) produzem ruido residual. Ver `many_orphan_components` no warnings.
- Hachura decorativa com espacamento >50 px entre linhas passa pelos filtros atuais.
- O score e observacional. Nao substitui validacao humana nem ground truth.
- Se o PDF real gerar `rooms=0`, isso aparece explicitamente no modelo e debug.

### Numeros no PDF de referencia `planta_74m2.pdf` (74 m^2, uma pagina)

Estado v19 (post-filtros acumulados):
- walls: 328 (meta em apto similar: ~40-100)
- junctions: 221, end=110, tee=43, cross=37, pass_through=31
- rooms: 32 (dos quais ~8 com area plausivel, ~24 residuos)
- scores: geometry=0.38, topology baixo, rooms=?
- warnings: `walls_disconnected`, `many_orphan_components`

Melhorias aprovadas pelo Codex nesta sessao (round-review iterativo):
- `f434438` CLI com extract e serve subcommands.
- `e206578` schema 2.1.0: run_id, source (sha256/page_count), bounds per page.
- `ab0fb41` per-line thickness via distance transform (nao global max).
- `d5f9b79` pair-merge de strokes paralelos em centerline.
- `6a1c8eb` text-baseline filter.
- `c729429` orientation-dominance filter.
- `9e51d90` multi-scale + extreme cutoff.
- `3b89806` polygonize min_area robusto a fragmentos.
- `4e115d9` aspect ratio filter.
- `a585934` snap tolerance 1.5 x median.
- `9410820` orphan component reporting (sem dropar).
- `0d77765` aspect min 2.0.

## API

### `POST /extract`

Entrada:

- arquivo PDF

Saida:

- `observed_model`
- caminhos dos artefatos gerados

## Como Rodar

Python 3.12 nao esta instalado nesta maquina e nenhuma dependencia foi instalada aqui. O codigo foi apenas gerado.

Quando houver um ambiente Python disponivel:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

Para executar os testes sinteticos:

```bash
pytest
```

## Testes Cobertos

- quadrado simples -> 1 room
- 2 salas com parede compartilhada -> 2 rooms
- L-shape -> valido
- T-junction -> detectado corretamente
- walls desconectadas -> `rooms=0`

## Proximos Passos

1. **ROI crop** pre-Hough: detectar a regiao arquitetonica principal (maior densidade de cross/tee junctions) e processar apenas essa area. Elimina de uma vez blocos de texto/mini-plantas fora do escopo.
2. **Dimension-line filter**: detectar cotas por signature "linha longa com perpendiculares curtos nas pontas".
3. **Classificacao semantica** (structural/partition/peitoril/unknown) usando cor, espessura normalizada e contexto.
4. **Regression suite para PDFs reais**: conforme mais PDFs entrarem, adicionar fixtures com snapshots aprovados do observed_model.
5. Revalidar tolerances em PDFs de plantas com paredes duplas vs single-line.
