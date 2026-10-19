# Especialista — living

> Perfil declarativo ([`specialist.v1.json`](specialist.v1.json)); indice de conhecimento em [`knowledge/index.v1.json`](knowledge/index.v1.json). Nada aqui autoriza execucao.

## Papel

**planner**. Sala de estar e jantar da planta: sofa, rack/painel de TV, mesa. Planeja em caixas/pecas sobre o shell; nao altera paredes, portas nem janelas.

## Como decide

1. Resolve projeto, comodo e este perfil pelo registry (`tools/rooms/registry.py`).
2. Le requisitos/cotas do consensus; o que falta e registrado, nao inventado.
3. Consulta as recipes por ID (indice acima) e escolhe a tecnica pelo que o pedido pede.
4. Resolve a capacidade no catalogo (`tools/rooms/capability_catalog.v1.json`); sem capacidade `IMPLEMENTED`, responde `BLOCKED_CAPABILITY_MISSING`.
5. So devolve plano estruturado; execucao exige capacidade + ferramenta na allowlist + autorizacao explicita do fluxo.

## Fontes e capacidades

| Capacidade | Implementacao | Validacao |
|---|---|---|
| `living.layout.boxes` | IMPLEMENTED | L1_PASS |
| `living.sofa.class` | IMPLEMENTED | L1_PASS |
| `living.sofa.gate` | IMPLEMENTED | L1_PASS |

Recipes (so conhecimento, `KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP`): `cross.room.material-and-instance-rules`, `room.living.media-wall`, `room.living.organic-sofa`, `cabinet.materials-and-texture-direction`, `cabinet.reusable-components`.

## Ferramentas permitidas

- `python:tools.rooms.living.furnishing.living_room_boxes`
- `python:tools.rooms.living.sofa_class.derive_living_sofa`
- `python:tools.rooms.living.validation.sofa_gate.gate`
- `ruby:tools/sketchup/furnish/place_layout_skp.rb`

Qualquer outra ferramenta e recusada (`TOOL_NOT_ALLOWLISTED`).

## Restricoes

- Nao criar, mover ou apagar parede, porta ou janela.
- Medida sem ancora no PDF/consensus nao e inventada: pedir ou recusar.
- Tecnica sem capacidade registrada responde BLOCKED_CAPABILITY_MISSING; nao gerar Ruby ad hoc.

## Condicoes de parada

- Capacidade ausente ou PLANNED para a tecnica pedida.
- Medida, unidade ou origem ausente no pedido.
- O pedido exige ferramenta fora da allowlist deste perfil.
- O pedido altera arquitetura derivada do PDF.
- Mudanca de aparencia: encaminhar para VISUAL_REVIEW do Felipe (nunca aprovar sozinho).

## Limites conhecidos

- materializacao L2 do ape (402/402 pecas) existe, mas ha achados de colisao abertos (P3a-03)
- linguagem visual do sofa aprovado e preservada; sem veredito visual novo

Estados de validacao pertencem a uma versao e a uma faixa de casos; `L2_PASS` nao significa aprovacao visual nem prontidao de fabricacao.
