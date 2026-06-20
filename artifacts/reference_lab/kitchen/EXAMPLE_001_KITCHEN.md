# EXAMPLE_001 — KITCHEN_WARM_COMPACT_PREMIUM (planta_74)

> O primeiro exemplar golden — o **professor 001**. Toda referência nova é comparada com
> esta. Ensina "marcenaria bonita implementável", não "imagem bonita".

**reference_intent:** cozinha planejada compacta premium (apto 74m², layout linear FIXO).

## Antes → Depois
| | ANTES | DEPOIS |
|---|---|---|
| Forma | "Minecraft" — geladeira solta, blocos | torre de geladeira **planejada** + gola/reveal + sóculo recuado |
| Cor (cima) | branco chapado (risco de MDF barato) | **fendi quente acetinado** |
| Cor (baixo) | — | base **madeira coordenada** (sem bicolor) |
| Bancada | cinza liso (parede pintada) | **pedra clara com veio sutil** (tampo+backsplash contínuos) |
| Metal | bloco cinza fosco | **inox reflexivo** (eletro premium) |
| Luz | flat, sem profundidade | **LED linear contínuo 2700K** + sóculo grafite |

## Lição-raiz (4 camadas)
```
FORMA:   loose_object     → planned_niche_system
PELE:    flat_material    → warm_layered_materiality
LUZ:     spot_test_light  → continuous_architectural_light
VOLUME:  white_block      → warm_fendi_satin_volume
```
(o contraponto escuro vive em [EXAMPLE_002 — DARK_WALNUT](../kitchen_dark_walnut/EXAMPLE_002_KITCHEN_DARK_WALNUT.md))

## Separação FORMA × PELE (o que foi mexido em cada camada)
- **FORMA** (só dentro do envelope do PDF, sem mover âncora): torre integrada · filler ·
  coifa slim embutida · gola/reveal · sóculo grafite recuado · proporção aéreo/base.
- **PELE** (acabamento livre): fendi acetinado · madeira quente coordenada · pedra veio
  sutil · inox reflexivo.
- **LUZ**: LED linear 2700K + rig key/fill.
- **CÂMERA**: crop/FOV/hero + denoise.

## O caminho (loop GPT-validado, geometria CONGELADA)
Cada passo foi um defeito de PELE/LUZ/CÂMERA que o GPT apontou → regra → fix → re-render.
**Sem mover pia/parede/porta/módulos.**
1. **Brancão** → BRDF coordenado (`material_token`). 2. **2 hotspots meia-lua** → **LED
linear** (`lighting_token`). 3. **Vazio lateral** → **reframe** (`camera_token`). 4.
**Backsplash chapado** → **pedra veio sutil** (`material_token`). 5. **Granulação** →
denoise.

**Veredito GPT:** PASS de pele — *"congelaria a pele; resíduo só técnico, não conceito."*
**Veredito Felipe:** _pendente_ (golden sample só com o OK dele).

## Evidência
- Antes/depois: [`cozinha_antes_depois.png`](../../planta_74/furnished/kitchen_angles/cozinha_antes_depois.png)
- Hero: [`cozinha_vray_hero.png`](../../planta_74/furnished/kitchen_angles/cozinha_vray_hero.png)
- Montagem 3 ângulos: [`cozinha_vray_montagem.png`](../../planta_74/furnished/kitchen_angles/cozinha_vray_montagem.png)

## Cards (10) — `cards/*.json` (formato implementável, com categoria)
| # | card | categoria |
|---|---|---|
| 01 | integrated_fridge_tower | joinery_form |
| 02 | warm_fendi_upper | material |
| 03 | coordinated_oak_base | material |
| 04 | subtle_veined_stone_backsplash | material |
| 05 | under_cabinet_linear_led | lighting |
| 06 | shadow_gap_reveal | joinery_form |
| 07 | graphite_technical_toe_kick | joinery_form |
| 08 | integrated_slim_hood | joinery_form |
| 09 | inox_premium_appliance | material |
| 10 | hero_camera_compact_kitchen | camera |

## Patch de intenção (como o agente aplica este exemplo)
```
APPLY: planned_fridge_tower, warm_fendi_upper, coordinated_oak_base,
       subtle_veined_stone_backsplash, under_cabinet_linear_led,
       shadow_gap_reveal, graphite_technical_toe_kick, integrated_slim_hood,
       inox_premium_appliance, hero_camera_compact_kitchen
DO NOT: move sink / change wall / invent island / over-marble backsplash / mover layout PDF
```

## Spec
[`specs/modern_warm_kitchen.json`](specs/modern_warm_kitchen.json)
