# Reference Lab — compilador de referência visual → regra procedural

> Operado pelo especialista [`reference-to-joinery-translator`](../../.claude/skills/reference-to-joinery-translator/SKILL.md)
> (aka REFERENCE_GRAMMAR_COMPILER).
> **Referência bonita ≠ copiar imagem. Referência bonita → extrair decisões repetíveis.**

## Hierarquia absoluta
PDF manda na **posição** · Gates mandam na **circulação/segurança** · Referência manda na
**linguagem visual** · Felipe/GPT mandam no **PASS**.

## A separação que impede destruir o PDF: FORMA × PELE
Todo card declara uma **categoria** — senão o agente mistura "botar pedra bonita" com
"mudar layout" e destrói a planta:

| Categoria | Camada | Pode mexer? |
|---|---|---|
| `joinery_form_token` | FORMA (torre, gola, coifa, filler, sóculo, proporção) | só dentro do envelope do PDF; **nunca move âncora** |
| `material_token` | PELE (fendi, madeira, pedra, inox) | livre (acabamento) |
| `lighting_token` | LUZ (LED linear, rig) | livre |
| `camera_token` | CÂMERA (crop/FOV/hero) | livre (não toca geometria) |
| `safety_gate` | TRAVA (pia fixa, circulação) | bloqueia |

## KB (`references/`) vs Lab (`artifacts/reference_lab/`)
- **`references/`** = livro-texto (conhecimento geral): materiais, ergonomia, anti-padrões,
  paletas e **tokens** (fonte única).
- **`artifacts/reference_lab/`** = estudos de caso (exemplos concretos com antes/depois e
  cards JSON implementáveis). Tokens referenciados de `references/tokens/`, não copiados.

## Estrutura
```
artifacts/reference_lab/
  README.md
  kitchen/
    EXAMPLE_001_KITCHEN.md          ← KITCHEN_WARM_COMPACT_PREMIUM (a régua / professor 001)
    cards/
      card_schema.json              ← contrato fixo do card
      01..10_*.json                 ← 10 Reference Cards implementáveis (com categoria)
    specs/modern_warm_kitchen.json  ← DesignGrammarSpec
```

## A saída do especialista é PATCH DE INTENÇÃO, não crítica
```
APPLY:  planned_fridge_tower, warm_fendi_upper, ...
DO NOT: move sink / change wall / invent island / over-marble
```

## Lição-raiz (3 camadas)
```
loose_object    → planned_niche_system           (FORMA)
flat_material   → warm_layered_materiality        (PELE)
spot_test_light → continuous_architectural_light  (LUZ)
```

## Como crescer o lab
Felipe cola 1–5 referências boas → o especialista lê → separa FORMA/MATERIAL/LUZ/CÂMERA →
cria/atualiza Cards JSON (formato fixo) → reusa/cria token em `references/tokens/` → aplica
num componente → renderiza → GPT julga → Felipe dá o PASS. **10 cards bem feitos > 500 imagens.**
