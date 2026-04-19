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

- A extracao atual e mais forte para linework ortogonal em raster.
- Elementos inclinados, curvos ou muito degradados podem nao ser extraidos corretamente.
- PDFs com pouco contraste ou com walls representadas por preenchimentos complexos podem exigir refinamento futuro na etapa `extract`.
- O score atual e observacional. Ele nao substitui validacao humana nem ground truth.
- Se o PDF real gerar `rooms=0`, isso continua sendo aceitavel e aparece explicitamente no modelo e no debug.

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

1. Medir o extractor com PDFs reais sem alterar a logica especificamente para um arquivo.
2. Expandir `extract` para casos nao ortogonais e para melhor separacao entre linework e ruido raster.
3. Adicionar benchmarks e fixtures de regressao a partir de falhas reais observadas.
