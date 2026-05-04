# Auditoria do órfão residual — `planta_74.pdf`

Status: investigativo. Nenhum filtro foi aplicado. Recomendação no fim.

Pipeline rodado em `f2b896c` (HEAD de `fix/dedup-colinear-planta74`):

```
python main.py extract planta_74.pdf --out runs/orphan_audit
```

Saída chave:
- `runs/orphan_audit/connectivity_report.json` → `orphan_component_count=0`, `orphan_node_count=0`
- `runs/orphan_audit/overlay_audited.png` → header `walls=230 orphans=1 rooms=48 juncs=71 geom=0.2495 topo=1.0`

Divergência: connectivity diz 0, overlay diz 1. Este doc explica por quê e qual wall é.

## 1. O que "magenta" significa no overlay

Fonte: `debug/overlay.py`, função `_compute_orphan_wall_ids` (linhas 141-166) e constante `_ORPHAN_MAX_NODES = 3` (linha 27).

Algoritmo:
1. Agrupa walls por `page_index`.
2. Constrói `networkx.Graph` onde cada wall vira uma aresta `(start, end)` com atributo `wall_id`.
3. Para cada componente conexo com `len(component) <= 3` nós, marca todos os `wall_id` como órfão.
4. Desenha em magenta (`_ORPHAN_WALL_COLOR = (217, 70, 239)`) por cima dos walls normais.

Regra efetiva: **"wall cujo componente conexo em endpoint-grafo tem ≤ 3 vértices"**.

### Por que isso diverge do connectivity_report

`topology/service.py` (linhas 77-97) também constrói um grafo por página, mas sobre os `split_walls` (pré-`_merge_colinear_segments`, linha 61). Após os splits, um wall horizontal pode ter sido particionado em vários sub-segmentos que compartilham endpoints com paredes vizinhas — formando um único componente grande. O merge final (`_merge_colinear_segments`) reconstrói walls "coesos" mas pode recuperar um wall cujos endpoints agora não casam com nenhum outro wall no output final.

O `overlay` opera sobre o output merged (`observed_model.walls`). O `connectivity_report` opera sobre `split_walls`. Logo, um wall isolado no output não necessariamente é um componente isolado no split graph. É exatamente o caso deste órfão.

## 2. O wall magenta atual

Extraído de `runs/orphan_audit/observed_model.json`:

```json
{
  "wall_id": "segment-1",
  "parent_wall_id": "wall-1",
  "page_index": 0,
  "start": [121.032, 297.778],
  "end":   [254.175, 288.055],
  "thickness": 13.37,
  "orientation": "horizontal",
  "source": "hough_horizontal",
  "confidence": 1.0
}
```

Comprimento: 133.5 pt. Inclinação: ≈ -0.073 (slight slope down-to-left, dentro do limiar "horizontal" do classificador). Thickness 13.37 está dentro da banda típica de paredes estruturais (mediana=11.46, máx=15.28).

Endpoints viram duas `junctions` de grau 2 `pass_through` (junction-1 e junction-15) — mas ambas **só tocam segment-1** no output final. Não há outro wall compartilhando coordenadas exatas com esses pontos; as verticais mais próximas (segment-217 / segment-258 / segment-282) começam em y=329 ou y=379, ou seja, a ≥ 32 pt abaixo.

room-1 incorpora os dois endpoints como vértices do seu polygon:
```
room-1 polygon = [
  (254.175, 288.055),   # = segment-1.end
  (121.032, 297.778),   # = segment-1.start
  (129.08,  379.479),
  (259.221, 394.2),
  (256.821, 329.267)
]
```
— ou seja, segment-1 é o "teto" do polygon de room-1, mas os dois vértices inferiores dele não são conectados por wall real ao topo. O polygon foi fechado por proximidade de endpoint, não por aresta explícita.

### Comparação com o PDF

`runs/orphan_audit/orphan_zoom_unmarked.png` (crop x=[100,280] y=[250,400]) mostra que **não existe parede estrutural no topo da SALA DE ESTAR** nesta região. A fachada real fica logo acima (fora do crop), e entre ela e os textos "1.79" / "2.40" há apenas cotas e whitespace.

`runs/orphan_audit/orphan_region_crop_marked.png` sobrepõe segment-1 ao raster: a linha magenta passa por cima de **texto de cotas** ("1.79" à esquerda, "2.40" à direita) e das linhas horizontais que formam o hachurado de parede acima de "SUÍTE 02".

Inferência: **segment-1 é falso-positivo do Hough horizontal**, disparado por:
- as linhas horizontais do hachurado de parede da SUÍTE 02 no lado direito (y≈288),
- as linhas horizontais internas da cota "1.79" no lado esquerdo (y≈297),
- fundidos pelo `_merge_colinear_segments` em um único segmento de 133 pt cruzando a região "SALA DE ESTAR" (que não tem parede).

Não é legenda de rodapé (y<300, está no topo). Não é mobiliário (thickness 13.37 é de parede, não de mobília). É **ruído estrutural causado por hachurado + cota lidos como colinear**.

## 3. Histórico

| Commit | Descrição | `orphan_component_count` | órfãos visuais no overlay |
|---|---|---|---|
| `dcb9751` (pré-hardening, main) | opening bridges + clean-input heuristics | 2 (5 nós em 2 comps) | — |
| `a11724a` (fix original) | collinear dedup | 2 (4 nós em 2 comps) | — |
| `2a268fe` (pós-hardening, F3+F2+F1) | representative-anchored dedup + density gates | 0 | 1 (segment-1) |
| `f2b896c` (HEAD atual) | docs sync | 0 | 1 (segment-1) |

O hardening zerou os órfãos de nível de **split graph** (`connectivity_report`), mas **não elimina** walls isolados no **merged graph** quando todos os sub-segmentos foram absorvidos em um único wall pós-merge. O overlay continua expondo isso porque ele opera sobre o output, não sobre o split.

## 4. Recomendação

**Preservar como sinal; não filtrar automaticamente.**

Justificativa:

1. O órfão é falso-positivo de percepção (hachurado + cota fundidos). Qualquer filtro simples (tamanho, posição, confidence) vai remover só o sintoma. A causa está em `_merge_colinear_segments` promovendo sub-segmentos fracamente ligados a uma parede única, ou em Hough detectando linhas de hachurado como parede.

2. Filtrar por "componente ≤ 3 nós no merged graph" é tentador (1 linha de código em `extract/service.py`), mas:
   - risco: legítimas paredes-de-fechamento-de-varanda tipicamente têm componente 2 (dois verticais curtos + um horizontal), e podem cair no mesmo filtro.
   - perde-se o sinal visual que esse overlay foi explicitamente construído pra expor (`debug/overlay.py` linha 6-10: "GPT-flagged check: if these are legend / furniture fragments, they cluster visually").

3. O fix correto é upstream:
   - **A**: no extrator Hough, usar `cv2.morphologyEx` com kernel vertical fino pra destruir hachurado-de-parede antes da detecção horizontal (preprocess_walls.py já tem infra pra isso).
   - **B**: no merge colinear, exigir que o wall resultante tenha **pelo menos 1 endpoint compartilhado com outro wall** no output final; caso contrário, reverter pro sub-segmento mais longo ou descartar.
   - **C**: na classificação, usar OCR ou heurística de densidade de texto nas proximidades do wall candidato pra rejeitar segmentos que passam dentro de bbox de texto.

Opção B é a mais cirúrgica. Custo: ~20 LOC em `topology/service.py` depois do merge, antes do `output_walls` ser devolvido. Risco baixo (descarta walls que não conectam — definicionalmente não contribuem pra polígono de sala).

Se filtrar agora for necessário (ex: deadline de demo), o critério mais seguro seria:

```python
# pos-merge, pre-output:
final_graph = nx.Graph()
for w in output_walls:
    final_graph.add_edge(tuple(w.start), tuple(w.end), wall_id=w.wall_id)
orphan_wall_ids = {
    data["wall_id"]
    for comp in nx.connected_components(final_graph)
    if len(comp) <= 2
    for _u, _v, data in final_graph.subgraph(comp).edges(data=True)
}
output_walls = [w for w in output_walls if w.wall_id not in orphan_wall_ids]
```

— mas **isto deve passar pela suíte adversarial** em `tests/` antes de qualquer merge, porque plantas com varandas/sacadas pequenas podem quebrar.

## 5. Artefatos reproduzíveis

- `runs/orphan_audit/connectivity_report.json`
- `runs/orphan_audit/observed_model.json`
- `runs/orphan_audit/dedup_report.json`
- `runs/orphan_audit/overlay_audited.png`
- `runs/orphan_audit/orphan_region_crop_marked.png`
- `runs/orphan_audit/orphan_context_top_left.png`
- `runs/orphan_audit/orphan_zoom_unmarked.png`
- `runs/orphan_audit/orphan_zoom_raw.png`

Comando pra regenerar tudo:

```
python main.py extract planta_74.pdf --out runs/orphan_audit
```

(crops adicionais: snippet Python no fim da seção 2 deste doc, via pypdfium2 + PIL.)
