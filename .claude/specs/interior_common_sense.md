# Interior Common Sense Engine

> Motor de **bom senso espacial**. O Claude não "coloca móvel" — ele **resolve
> restrições**: entende a planta como grafo, pontua paredes, gera candidatos e
> rejeita layouts burros (TV de costas pra cozinha, sofá no corredor). Cada erro
> humano observado vira regra → fixture → gate → score → regressão.

## Componentes (em `interior/semantics/` + `interior/planners/` + `interior/validators/`)

1. **RoomGraph** (`room_graph.py`, feito): cômodos + walls + aberturas + **adjacência**
   (qual porta/passagem/balcão conecta quais cômodos). `artifacts/review/interior/room_graph_*.json`.
2. **WallAffordanceMap** (`wall_affordance.py`, feito): pontua cada parede do cômodo pra
   TV/rack e sofá. Regra-chave: **TV exige parede LIMPA** — porta/janela/passagem/balcão
   DESQUALIFICA (uma parede-corredor de 15 m com porta NÃO ganha de uma parede limpa de 4 m).
3. **CirculationGraph** (a fazer): caminhos entrada→cozinha→corredor→varanda→quartos.
4. **NoFurnitureZones** (a fazer): buffers de circulação + giro de porta + frente de
   rack/guarda-roupa → zonas proibidas/penalizadas.
5. **Placement solver** (a fazer): gera candidatos → score (hard reject + soft penalty)
   → escolhe o melhor → ValidationReport (por que ganhou / por que rejeitou os outros).
6. **Gates** (a fazer): TVPlacementGate, SofaPlacementGate, ClearanceGate,
   OrientationGate, room_common_sense_gate.

## Regras profissionais (viram score/gate)

**Sala**
- TV/rack: parede LIMPA, longa o suficiente, ancorada; **não** em parede de porta/
  janela/passagem; **não** de costas pra cozinha integrada (aberta).
- Sofá: de frente pra TV (ângulo ≤ ~25°); **não** cruza circulação principal; não
  bloqueia porta/passagem; respiro na frente.
- Mesa de centro: só entre sofá e rack se sobrar distância útil.
- Poltrona: só se não roubar passagem.
- Tapete: ancora sofá + mesa + rack.

**Quarto**
- Cama: cabeceira em parede limpa; circulação lateral mínima; não bloqueia porta/guarda-roupa.
- Criados: um de cada lado, se couber. Guarda-roupa: parede longa, frente livre.

## Fixtures de ERRO (ensina por contra-exemplo) — a fazer

`fixtures/interior/living_room/`: `fail_tv_back_to_kitchen` (FAIL),
`fail_sofa_blocks_corridor` (FAIL), `fail_tv_on_door_wall` (FAIL),
`fail_sofa_not_facing_tv` (FAIL), `valid_sofa_tv_axis` (PASS). Cada um: planta simples
+ layout + teste que reprova o errado / aprova o certo.

## Tradução erro humano → sistema

| Humano | Sistema |
|---|---|
| "TV não pode ficar de costas pra cozinha" | reject se `tv.back_vector → kitchen_opening` |
| "sofá está no corredor" | reject se `sofa ∩ circulation_buffer` ou passagem < 0.80 m |
| "sofá não olha pra TV" | reject se `angle(sofa_front, →tv) > 25°` |
| "rack na parede errada" | WallAffordanceMap: parede com abertura desqualifica |

**Hard rules**: não mexer em parede/janela; só **propor** layout (não inventar geometria);
artefatos em `artifacts/review/interior/`; provar em micro-fixture antes da planta real.
