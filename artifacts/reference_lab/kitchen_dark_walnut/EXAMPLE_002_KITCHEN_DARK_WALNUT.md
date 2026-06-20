# EXAMPLE_002 — KITCHEN_DARK_WALNUT_MOODY

> Referência CURADA pelo Felipe (cozinha black + walnut moody). Primeiro teste real do
> REFERENCE_TO_JOINERY_TRANSLATOR. Aqui guardamos a **gramática** extraída, não o pixel.

**reference_intent:** cozinha contemporânea escura premium — marcenaria preto fosco +
nogueira quente, ambiência moody/low-key. (Contraponto ao EXAMPLE_001 claro/fendi.)

## Leitura visual (decisões repetíveis, não a imagem)
- **Marcenaria preto fosco** (slab handle-less, gola/reveal) — pele dominante, ultra-matte.
- **Nogueira** no backsplash **E** no tampo, **mesmo material contínuo** (o tampo "sobe" a
  parede) — veio dramático, quente, é a estrela contra o preto.
- **Coifa caixa** proeminente (chaminé) preta com **fundo de madeira** + tela perfurada
  decorativa — peça de assinatura, não slim.
- **Torres dark floor-to-ceiling** flanqueando.
- **Fixtures monocromáticas pretas** (torneira/cuba/cooktop) — preto-no-preto, o contraste
  vem da madeira.
- **LED linear quente** sob o aéreo — **pop alto** porque o armário é escuro.
- **Luz low-key quente** — ambiência escura/dramática, key quente.

## Lições centrais (camadas)
```
FORMA:   slab handle-less + coifa-caixa + torre cheia → planned_dark_volume
PELE:    preto fosco + nogueira contínua            → matte_black + warm_walnut_layering
LUZ:     low-key quente + LED que estoura no escuro  → moody_warm_with_led_pop
```
(complementa as 4 lições do EXAMPLE_001 — o `white_block → warm_fendi_satin_volume` é o
INVERSO desta: lá clareia, aqui escurece com madeira pra não virar caverna.)

## Cards (`cards/*.json`)
| card | categoria |
|---|---|
| matte_black_joinery | material |
| warm_walnut_surface | material |
| box_hood_wood_underside | joinery_form |
| matte_black_fixtures | material |
| moody_low_key_warm_light | lighting |
| compact_dark_cave_gate | safety_gate |
| wood_wetzone_gate | safety_gate |
Reusa do EXAMPLE_001: `under_cabinet_linear_led` (LED linear), `shadow_gap_reveal`
(handle-less), `integrated_fridge_tower` (torre cheia).

## Patch de intenção — aplicar este estilo na planta_74 (linear, compacta)
```
APPLY (PELE/LUZ, livre):
  - matte_black_joinery        (aéreos/base preto fosco)
  - warm_walnut_surface        (tampo + backsplash nogueira contínua)
  - matte_black_fixtures        (torneira/cuba/cooktop preto)
  - under_cabinet_linear_led    (LED já provado, vai estourar mais no escuro)
  - moody_low_key_warm_light    (rig mais quente/baixo)
APPLY (FORMA, só dentro do envelope do PDF):
  - box_hood_wood_underside     (trocar a coifa slim pela caixa c/ fundo madeira)
  - shadow_gap_reveal / handle-less
DO NOT:
  - inventar ILHA (a planta_74 é linear, sem ilha)
  - virar L (posição é do PDF)
  - mover pia / parede / porta
  - usar madeira crua no tampo molhado sem selagem (ver wood_wetzone_gate)
  - ir 100% preto numa cozinha compacta sem luz (ver compact_dark_cave_gate)
```

## Status
Gramática EXTRAÍDA e bancada. **Não aplicada/renderizada** na planta_74 (seria um estilo
NOVO, escuro, vs a cozinha clara que o GPT já passou). Aguardando Felipe: aplicar como
**variante dark** (render lado a lado com a clara) ou só guardar no lab?
