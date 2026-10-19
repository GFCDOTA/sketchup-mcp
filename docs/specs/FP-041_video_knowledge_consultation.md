# FP-041 — consulta das aulas e micro-fixture consultiva de gabinete

## Problema e escopo

O catálogo do PR #252 possui oito receitas citadas, mas faltava um agente que
as consultasse e um caso reproduzível que separasse cálculo de prova real.
Esta fatia adiciona o agente read-only, recuperação lexical e um estudo de
gabinete. Não é o MVP completo do FP-041 nem o contrato `operation_plan.v1`.

As fontes foram registradas no trabalho anterior. Esta continuação valida o
uso do catálogo e o código, sem alegar nova análise de vídeos.

## Contrato da micro-fixture

`tests/data/sketchup_knowledge/cabinet_case.v1.json` usa
`advisory_cabinet_case.v1`: medidas em mm, sintéticas, sem caminho de modelo,
sem campos de execução e sem ferragem presumida. Não modifica `fixtures/`.

Gabinete de estudo: 1200 × 720 mm, profundidade de carcaça 560 mm; painéis 18 mm,
fundo 6 mm e folgas frontais 3 mm. São hipóteses de teste, nunca norma nem cota
do apartamento. Há dois vãos, uma porta à esquerda e três frentes à direita.
As frentes ficam em Y negativo, fora da carcaça; o fundo fica nos últimos 6 mm.
O divisor ocupa a faixa central e os vãos livres têm 573 × 684 mm.

`cabinet-plan` calcula dez painéis/frentes com IDs semânticos, bboxes e uma
hierarquia **proposta**. A caixaria de gaveta e os envelopes de movimento não
são dimensionados sem ferragens. Não gera `_p`, Ruby ou plano de corte.

O resultado é `advisory_cabinet_plan.v1`, com hashes SHA-256 do JSON normalizado
da entrada e do catálogo, três receitas com fontes/timestamps e três estratégias:
volumes como fallback visual, componentes derivados de spec como proposta e
edição avulsa de base regenerável rejeitada. Sempre retorna
`execution_authorized=false` e `BLOCKED_CAPABILITY_MISSING`.

## Aceite e sabotagens

- L1: dimensões finitas/positivas, vãos viáveis, painéis sem sobreposição de
  volume positivo e folgas frontais reais no estudo matemático.
- Entradas com medida de curso/projeto, campo desconhecido, hardware presumido,
  NaN/infinito, bool como medida ou geometria inviável são recusadas.
- Catálogo com prova elevada, ID duplicado ou proveniência ausente é recusado.
- CLI roda de outro cwd, imprime JSON e não escreve arquivo. Código não importa
  jobs, processo SketchUp, executor Ruby, rede ou servidor MCP.
- L2 permanece `PENDING_SKETCHUP`; L3 permanece `PENDING_HUMAN`.

## Reprodução

```bash
python -m tools.sketchup.knowledge list --q gavetas
python -m tools.sketchup.knowledge cabinet-plan --case tests/data/sketchup_knowledge/cabinet_case.v1.json
python -m pytest tests/test_sketchup_knowledge.py tests/test_sketchup_video_knowledge.py -q
```

Nenhum builder, materializador, servidor MCP, fixture canônica ou `.skp` é
alterado. Um executor futuro deve implementar componentes e ferragens a partir
da spec, provar isolamento/compartilhamento e medir resultados no SketchUp.
A existência do agente em Markdown não comprova seu desempenho: a avaliação
geral de competência e o ledger do FP-041 continuam pendentes.
