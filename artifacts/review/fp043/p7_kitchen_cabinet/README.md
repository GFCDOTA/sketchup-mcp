# FP-043 / P7 — pedido inédito → gabinete na cozinha da planta_74, salvo, reaberto e inspecionado (L2)

**O que está provado:** um pedido novo ao especialista de cozinha percorre o fluxo registrado e termina num `.skp` **editável,
salvo, reaberto em outro processo e inspecionado**, com um trace que liga o pedido à capacidade catalogada (não a um placeholder).
**O que NÃO está provado:** qualidade estética, posição "boa" de projeto, fabricação, ferragem/gaveta/Shaker, veio da madeira.

| | |
|---|---|
| Código sob prova | commit `8317dce`, árvore limpa (o L2 foi rodado duas vezes: a 1ª achou um defeito real, ver abaixo) |
| SketchUp | 26.0.429, Windows 11, `interactive`, processo próprio por chamada; cada PID subido foi fechado **pelo PID** |
| Base | **cópia** do `.skp` mobiliado canônico da planta_74 (`artifacts/planta_74/furnished/planta_74_furnished.skp`, SHA-256 `d2846ab6…`); o canônico não é aberto e segue idêntico (`summary.json: canonical_unchanged=true`) |
| Pedido | [`request.json`](request.json): 480×545×780 mm, painéis 15/15/4/16 mm, folgas 1,5/2,5 mm, 1 frente, materiais `mdf_grafite`/`hdf_grafite`/`mdf_nogueira`, pose (2,25 m; 15,90 m; 0°). **Medidas e pose foram escolhidas por quem pediu a prova** (origem `user_request`): não são decisão de design da cozinha. Estas medidas não aparecem nos testes de implementação |
| Reprodução | `l2_p7.py <saída> request.json <base.skp>` (neste diretório), repo no `PYTHONPATH`, `PT_TO_M=0.0259` |

## Trace positivo ([`trace.json`](trace.json)) — `DONE_L2_VERIFIED`

`request` → `project_room` (planta_74 / r004 COZINHA) → `consensus_requirements` (SHA-256 do consensus e da base) → `knowledge`
(binding `bind.kitchen.cabinet`, recipes `cabinet.reusable-components` e `cabinet.front-gaps-and-profiles`, ambas
`KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP`) → `specialist_plan` + `capability` (`shared.cabinet.parametric` 1.0.0 /
`kitchen.cabinet.plain-fronts`) → `parameters` (valor+unidade+origem de cada um) → `plan_validation` (4 gates: **âncora hidráulica,
arquitetura, mobília planejada, circulação — todos PASS**) → `allowlist` (as 7 ferramentas usadas estão na allowlist do perfil) →
`baseline_inspect` → `job` (build, PID próprio, salva) → `reopen_inspection` (outro PID reabre o arquivo salvo; **42 verificações
PASS**, erro máx. de vértice 3,6e-15 m) → `kitchen_anchor_after` (PASS) → `evidence`.

- `non_cabinet_fingerprint_before == after` (`751a56d4…`): shell, mobília e demais objetos do modelo ficaram como estavam.
- Chave de idempotência `ea1b341ef89d…`; reexecução com a mesma chave devolve `ALREADY_DONE` sem subir o SketchUp (testado em L1).
- [`cabinet.skp`](cabinet.skp) é o arquivo salvo; [`top.png`](top.png) / [`iso.png`](iso.png) são só ilustração (a cor do gabinete é derivada do
  nome do material, não é acabamento; na vista isométrica ele fica atrás da parede). **Nenhum veredito visual** — `NOT_REVIEWED`.

## Negativos reais ([`negatives.json`](negatives.json)) — nenhum sobe o SketchUp, entrada e base intactas, sem prova positiva

| Caso | Estado |
|---|---|
| recipe Shaker sem builder | `BLOCKED_CAPABILITY_MISSING` |
| ferramenta fora da allowlist (`mcp:su_apply_edits`) | `BLOCKED_TOOL_NOT_ALLOWED` |
| geometria impossível (largura 30 mm) | `BLOCKED_PLAN_REFUSED` (`INFEASIBLE_INNER_WIDTH`) |
| entrada sem unidade / sem origem | `BLOCKED_INPUT_INCOMPLETE` (vira pergunta, não execução) |
| "…e remover a parede oeste" (alterar arquitetura) | `BLOCKED_ARCHITECTURE_CHANGE` |
| pose fora da cozinha | `BLOCKED_PLAN_REFUSED` (gate `architecture`) |

**Job interrompido de verdade** ([`interrupted_job.json`](interrupted_job.json)): o processo do SketchUp (filho que subimos, via handle) é
encerrado 6 s depois do início do build → `SU_EXITED`, **nenhum `.skp` de saída**, cópia não editada removida, nenhum arquivo de
resultado, base intacta, nenhuma prova positiva.

## Defeito que o L2 achou (e foi corrigido antes de valer)

Na 1ª execução (commit `ceb2d74`) o negativo "gabinete de cozinha e **remover a parede oeste**" **passou** (`DONE_L2_VERIFIED`):
a regra de detecção de alteração de arquitetura exigia "remover parede" colado e não pegou "remover a parede oeste". Nenhuma parede foi
alterada (o fingerprint comprova), mas o pedido deveria ter sido barrado antes. Corrigido (commit `8317dce`): verbo de alteração +
artigos + elemento arquitetônico, sem confundir "mover o gabinete para a parede" nem as portas do próprio gabinete; testes L1 novos.
Toda a evidência acima é da **2ª** execução, no commit corrigido.

## Reexecução da matriz da P6b no mesmo commit ([`p6b_matrix_rerun.json`](p6b_matrix_rerun.json))

Como `materialize` mudou (descarte da cópia não editada), a prova de L2 do construtor foi refeita: **13/13 PASS** de novo
(3 dimensões × 0°/90°/30°, reexecução sem duplicar, repetição, `make_unique`, edição local, propagação só quando pedida).

## Limites

- Material = nome + cor derivada (sem textura); **veio: `NOT_SUPPORTED`**. Sem ferragem, gaveta, Shaker, recorte de bancada/cuba, lista de corte.
- A pose é arbitrária e o gabinete fica no corredor da cozinha: passa nos gates do projeto, o que **não** significa que seja um bom layout.
- Revisão visual pendente (`NOT_REVIEWED`); nenhum modelo canônico foi alterado ou promovido.
