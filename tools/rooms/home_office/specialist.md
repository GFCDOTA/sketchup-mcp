# Especialista — home_office

> Perfil declarativo ([`specialist.v1.json`](specialist.v1.json)); indice de conhecimento em [`knowledge/index.v1.json`](knowledge/index.v1.json). Nada aqui autoriza execucao.

## Papel

**reuse** (reaproveita `bedroom`). Home office: reaproveita o designer de quarto; sem builder proprio de mesa/prateleira.

## Como decide

1. Resolve projeto, comodo e este perfil pelo registry (`tools/rooms/registry.py`).
2. Le requisitos/cotas do consensus; o que falta e registrado, nao inventado.
3. Consulta as recipes por ID (indice acima) e escolhe a tecnica pelo que o pedido pede.
4. Resolve a capacidade no catalogo (`tools/rooms/capability_catalog.v1.json`); sem capacidade `IMPLEMENTED`, responde `BLOCKED_CAPABILITY_MISSING`.
5. So devolve plano estruturado; execucao exige capacidade + ferramenta na allowlist + autorizacao explicita do fluxo.

## Fontes e capacidades

Nenhuma capacidade executavel registrada para esta categoria: o especialista so aconselha.

Recipes (so conhecimento, `KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP`): `cross.room.material-and-instance-rules`, `room.office.desk-and-storage`, `cabinet.materials-and-texture-direction`, `cabinet.reusable-components`.

## Ferramentas permitidas

- (nenhuma: perfil consultivo)

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

- home office reaproveita o designer de quarto; sem builder proprio

Estados de validacao pertencem a uma versao e a uma faixa de casos; `L2_PASS` nao significa aprovacao visual nem prontidao de fabricacao.
