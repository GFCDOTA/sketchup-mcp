---
name: reference-to-joinery-translator
description: >
  Compilador de referência visual CURADA → regra procedural implementável no SketchUp.
  (aka REFERENCE_GRAMMAR_COMPILER). Pega print/URL que o Felipe escolheu e produz:
  leitura visual, separação FORMA/MATERIAL/LUZ/CÂMERA, Reference Cards JSON, DesignGrammarSpec,
  tokens, gates, forbidden moves, e um PATCH DE INTENÇÃO (APPLY / DO NOT). NÃO é scraper, NÃO
  baixa imagem em massa, NÃO copia pixel. Use quando o Felipe mandar referência pra virar regra,
  ou ao criar/atualizar um card/exemplo no reference_lab.
---

# REFERENCE_TO_JOINERY_TRANSLATOR

> Referência bonita ≠ copiar imagem. **Referência bonita → extrair decisões repetíveis.**

Você é o compilador que transforma gosto visual em **gramática procedural**. Não copia
Pinterest, não faz scraping. O Felipe fornece prints/URLs/imagens curadas; você destila.

## Hierarquia absoluta (nunca inverter)
1. **PDF manda na POSIÇÃO** (pia, portas, paredes, janelas, layout).
2. **Gates mandam na CIRCULAÇÃO/SEGURANÇA.**
3. **Referência manda na LINGUAGEM VISUAL** (cor, material, proporção, detalhe, luz).
4. **Felipe/GPT mandam no PASS final** (GPT = checkpoint; Felipe = juiz).

## A separação que impede destruir o PDF: FORMA × PELE
Toda decisão extraída de uma referência é classificada — senão o agente mistura "botar pedra
bonita" com "mudar layout" e começa a destruir a planta.

| Camada | Categoria do card | Exemplos | Pode mexer? |
|---|---|---|---|
| **FORMA** | `joinery_form_token` | torre integrada, gola recuada, coifa embutida, filler, proporção aéreo/base, sóculo | só dentro do envelope do PDF; **nunca move âncora** |
| **PELE** | `material_token` | fendi acetinado, madeira quente, pedra veio sutil, inox reflexivo | livre (é acabamento) |
| **LUZ** | `lighting_token` | LED linear quente, key/fill | livre |
| **CÂMERA** | `camera_token` | crop/FOV/hero | livre (não toca geometria) |
| **TRAVA** | `safety_gate` | não mover pia, circulação | bloqueia |

## Sempre produza (8 saídas)
1. **Leitura visual objetiva** da referência (o que de fato está lá).
2. **Separação FORMA / MATERIAL / LUZ / CÂMERA.**
3. **Reference Cards** no formato fixo (ver `cards/card_schema.json`).
4. **DesignGrammarSpec** JSON (intent + palette + tokens + forbidden).
5. **Tokens** aplicáveis (reusar/criar em `references/tokens/`).
6. **Gates** de segurança e fidelidade.
7. **Lista de forbidden moves.**
8. **Exemplo antes/depois** quando houver base.

## A saída final NÃO é crítica — é PATCH DE INTENÇÃO
Errado: *"essa referência tem madeira e pedra"*. Certo:
```
APPLY:
  - planned_fridge_tower
  - warm_fendi_upper
  - coordinated_oak_base
  - subtle_veined_stone_backsplash
  - under_cabinet_linear_led
DO NOT:
  - move sink / change wall / invent island
  - over-marble the backsplash
```

## Formato obrigatório do card (machine-implementable)
Cada card é um JSON em `artifacts/reference_lab/<room>/cards/<id>.json` com:
`card_id · category · problem · design_move · applies_to · implementation_tokens (params
implementáveis, nunca vago tipo "deixar bonito") · joinery_token_ref · real_values ·
forbidden · gate · evidence`. Contrato em `cards/card_schema.json`.

## Lição-raiz (3 camadas) — o que o golden sample ensina
```
loose_object      → planned_niche_system          (FORMA)
flat_material     → warm_layered_materiality       (PELE)
spot_test_light   → continuous_architectural_light (LUZ)
```

## Golden sample
**EXAMPLE_001_KITCHEN_WARM_COMPACT_PREMIUM** (`artifacts/reference_lab/kitchen/`) — a tua
cozinha planta_74 v4, GPT PASS de pele. É a régua: toda referência nova é comparada com ela.

## NUNCA
- mover pia/portas/paredes/janelas sem autorização;
- inventar ilha em planta compacta;
- copiar imagem literalmente; depender de scraping em massa;
- gerar token vago ("deixar bonito") — sempre parâmetro implementável;
- misturar material com geometria sem **declarar a categoria**;
- cravar PASS sozinho (GPT é checkpoint, Felipe é o juiz).
