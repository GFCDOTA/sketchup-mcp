# External Validation Report — 2026-04-27

Validação do pipeline V6.2 contra plantas brasileiras externas (gov + social housing). Objetivo: medir generalização além do baseline `planta_74` + `p10/p11/p12_red`.

## Datasets testados

5 PDFs externos baixados em `test_data/external/` (sites gov/edu sem auth):

| PDF | Tamanho | Pages | Format | Source |
|---|---:|---:|---|---|
| caixa_especificacoes_min | 121 KB | 3 | A0 land. | autogestao.unmp.org.br (CAIXA UH Fase 3 spec) |
| funasa_3quartos | 1.7 MB | 10 | A4 | saojoaodalagoa.mg.gov.br (3-quartos hab. social) |
| agehab_projetos | 4.2 MB | 14 | A4 | agehab.ms.gov.br (multi-tipologia) |
| natal_planta_baixa | 6.3 MB | 7 | A0 | natal.rn.gov.br (UERN planta) |
| codhab_planta_baixa | 7.5 MB | 23 | A0 | codhab.df.gov.br (hab. social DF) |

## Resultados

### External (5 PDFs)

| Plant | walls | rooms | open | orph | ratio | quality | warnings | status |
|---|---:|---:|---:|---:|---:|---|---|---|
| funasa_3quartos | 373 | 155 | 38 | 80 | 0.19 | poor | 4 | **FAIL** |
| caixa_especificacoes_min | 93 | 58 | 17 | 33 | 0.33 | poor | 3 | **FAIL** |
| codhab_planta_baixa | **7093** | **3875** | 784 | 496 | 0.20 | poor | 4 | **FAIL** |
| natal_planta_baixa | 3248 | 1063 | 172 | 337 | 0.46 | poor | 4 | **FAIL** |
| agehab_projetos | 460 | 213 | 39 | 60 | 0.30 | poor | 3 | **FAIL** |

### Baseline interna (referência)

| Plant | walls | rooms | open | orph | ratio | quality | status |
|---|---:|---:|---:|---:|---:|---|---|
| p12_red (golden) | 33 | 18 | 6 | 0 | 1.0 | good | OK |
| p11_red | 33 | 16 | 6 | 0 | 1.0 | good | OK |
| p10_red | 31 | 17 | 6 | 0 | 1.0 | good | OK |
| planta_74 (smoke) | 133 | 15 | 13 | 0 | 1.0 | good | OK |
| test_plan (sintético) | 6 | 3 | 0 | 0 | 1.0 | good | OK |

### Protos preprocess (variantes do `planta_74`)

| Plant | walls | rooms | ratio | quality | comment |
|---|---:|---:|---:|---|---|
| p4_roi | 40 | 9 | 0.96 | **fair** | ROI crop preprocess — único proto OK |
| p9_red | 16 | 2 | 0.79 | fair | preset red parcial |
| p8_red | 16 | 1 | 0.77 | fair | idem |
| p5_skeleton | 61 | 4 | 0.41 | poor | skeletonize sozinho não basta |
| p2_thickness | 28 | 0 | 0.48 | poor | filter thickness sem ROI explode |
| p3_kmeans | 2 | 0 | 1.00 | good (vazio) | kmeans agressivo demais |
| p1_components | 10 | 1 | 0.42 | poor | connected-components sem ROI |
| planta_74_clean | 0 | 0 | - | poor | PDF 0.20% dark — input vazio (descartado) |

## Diagnóstico

### Padrão de falha em externas (5/5)
Todos os 5 PDFs externos apresentam **mesma assinatura de falha**:

1. **`walls_disconnected`**: largest_component_ratio entre 0.19–0.46 (deveria ser ≥0.90)
2. **`many_orphan_components`**: 33–496 nodes órfãos (deveria ser 0)
3. **`room_count_deviation`**: 58–3875 rooms detectados (esperado 5–20 em planta residencial real)
4. **Quality `poor`** uniforme

Visualmente (overlay_audited.png em `runs/external_*/`): pipeline pega cotas, eixos de grid, blocos de texto, hachura, mobiliário, **legendas e tabelas** como walls. Resultado é uma "manta" de rooms sobrepostos que não tem relação com a planta real.

### Causa raiz
O baseline `planta_74` + `p10/p11/p12_red` foram tunados com:
- Color preset `red` ativado (planta_74 e variantes desenham walls em vermelho)
- A4-size única página
- Gates de classify (`text_baseline_filter`, `pair_merge`) calibrados pra esse caso

PDFs externos brasileiros desenham walls em **preto fino sobre branco** com cota e texto denso. Pipeline default (sem preprocess) trata cada linha como candidate wall.

### Evidência positiva
`p4_roi` (mesma `planta_74` mas com **ROI crop preprocess** ativo) entrega `ratio=0.96 / quality=fair / 9 rooms`. Confirma: **com preprocess certo, pipeline funciona em planta diferente do baseline tuning**.

## Proposta — V6.3 generalization wave (não implementado)

Em ordem de leverage:

1. **Auto-detect color preset** via K-means em fingerprint cromático antes de extrair. Pipeline tem `color_mask color: auto` flag mas não está ativando essas plantas (provavelmente pq paleta dominante é cinza claro vs branco — não detecta wall layer).
2. **Auto-detect single page**: identificar a página com MAIS estrutura geométrica em PDFs multi-page. Hoje processa primeira página fixa (codhab → primeira página é capa/índice → explode).
3. **Cap de "explode" + retry**: rejeitar runs com walls>500 OR rooms>50, re-tentar com preset diferente automaticamente.
4. **Adicionar essas 5 plantas como REGRESSION GATES NEGATIVAS**: `expected_quality: poor` na fixture; teste falha se acidentalmente passarem (sinal de over-fit reverso).

## Arquivos

- `run_external_plant.py` — runner genérico
- `runs/external_*/observed_model.json` — outputs detalhados
- `runs/external_*/overlay_audited.png` — debug PNGs (gitignored)
- `runs/_thumbnails/*.jpg` — thumbnails 600px JPEG (gitignored, regeneráveis)
