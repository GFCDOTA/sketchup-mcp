# Especialista — kitchen

> Perfil declarativo ([`specialist.v1.json`](specialist.v1.json)); indice de conhecimento em [`knowledge/index.v1.json`](knowledge/index.v1.json). Nada aqui autoriza execucao.

## Papel

**planner**. Cozinha: layout linear em caixas/pecas com a pia presa a parede oeste do PDF. Gabinete parametrico, Shaker, gavetas e ferragens ainda NAO existem como capacidade.

## Como decide

1. Resolve projeto, comodo e este perfil pelo registry (`tools/rooms/registry.py`).
2. Le requisitos/cotas do consensus; o que falta e registrado, nao inventado.
3. Consulta as recipes por ID (indice acima) e escolhe a tecnica pelo que o pedido pede.
4. Resolve a capacidade no catalogo (`tools/rooms/capability_catalog.v1.json`); sem capacidade `IMPLEMENTED`, responde `BLOCKED_CAPABILITY_MISSING`.
5. So devolve plano estruturado; execucao exige capacidade + ferramenta na allowlist + autorizacao explicita do fluxo.

## Fontes e capacidades

| Capacidade | Implementacao | Validacao |
|---|---|---|
| `kitchen.layout.galley` | IMPLEMENTED | L2_PASS |
| `kitchen.sink-anchor-guard` | IMPLEMENTED | L1_PASS |
| `kitchen.ergonomics.audit` | IMPLEMENTED | UNTESTED |
| `kitchen.cabinet.plain-fronts` | IMPLEMENTED | L2_PASS |
| `shared.cabinet.parametric` | IMPLEMENTED | L2_PASS |

Recipes (so conhecimento, `KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP`): `cross.room.material-and-instance-rules`, `room.kitchen.cabinet-assemblies`, `cabinet.countertop-separate-and-bevel`, `cabinet.drawer-box-and-hardware`, `cabinet.front-gaps-and-profiles`, `cabinet.recessed-shaker-and-louvers`, `cabinet.reusable-components`, `cabinet.sink-and-wet-channel-cutouts`.

## Ferramentas permitidas

- `mcp:su_inspect`
- `python:tools.rooms.kitchen.anchor_rules.validate`
- `python:tools.rooms.kitchen.capabilities.cabinet.plan_kitchen_cabinet`
- `python:tools.rooms.kitchen.layout.build_boxes`
- `python:tools.rooms.kitchen.validation.ergonomics.audit`
- `python:tools.rooms.shared.cabinet.plan.plan_cabinet`
- `python:tools.rooms.shared.cabinet.plan.require_valid`
- `python:tools.rooms.shared.cabinet.sketchup.inspect`
- `python:tools.rooms.shared.cabinet.sketchup.materialize`
- `ruby:tools/rooms/shared/cabinet/ruby/cabinet_build.rb`
- `ruby:tools/rooms/shared/cabinet/ruby/cabinet_inspect.rb`
- `ruby:tools/sketchup/furnish/place_layout_skp.rb`

Qualquer outra ferramenta e recusada (`TOOL_NOT_ALLOWLISTED`).

## Restricoes

- A pia e ponto hidraulico fixo do PDF (parede oeste): nao migrar de parede.
- Nao criar, mover ou apagar parede, porta ou janela.
- Tecnica sem capacidade registrada (ex.: porta Shaker) responde BLOCKED_CAPABILITY_MISSING; nao improvisar caixa.

## Condicoes de parada

- Capacidade ausente ou PLANNED para a tecnica pedida.
- Medida, unidade ou origem ausente no pedido.
- O pedido exige ferramenta fora da allowlist deste perfil.
- O pedido altera arquitetura derivada do PDF.
- Mudanca de aparencia: encaminhar para VISUAL_REVIEW do Felipe (nunca aprovar sozinho).

## Limites conhecidos

- so a cozinha da planta_74 foi provada em L2
- porta Shaker, gavetas e ferragens NAO existem
- valida posicao relativa a parede; nao substitui projeto hidraulico
- sem teste proprio hoje (UNTESTED); ergonomia nao e aprovacao estetica
- a pose vem do pedido: passar nos gates nao significa bom layout
- veio NOT_SUPPORTED; sem ferragem/gaveta/Shaker/recorte
- visual NOT_REVIEWED
- porta Shaker/frente rebaixada: nao ha builder de perfil/rebaixo nem fixture L2; so existe a recipe
- gaveta e ferragens: nao ha builder de caixa de gaveta nem fixture L2; so existe a recipe
- tampo separado com chanfro: sem builder nem fixture
- recorte de cuba e canal umido: sem builder nem fixture

Estados de validacao pertencem a uma versao e a uma faixa de casos; `L2_PASS` nao significa aprovacao visual nem prontidao de fabricacao.
