# Reference Lab — compilador de referência visual → regra procedural

> Operado pelo especialista [`reference-to-joinery-translator`](../../.claude/skills/reference-to-joinery-translator/SKILL.md)
> (aka REFERENCE_GRAMMAR_COMPILER).
> **Referência bonita ≠ copiar imagem. Referência bonita → extrair decisões repetíveis.**
>
> **Começando? Leia primeiro [`HOW_TO_USE.md`](HOW_TO_USE.md)** — o passo-a-passo do Felipe
> (curar → traduzir → protótipo → gates → veredito). O perfil dele (uso/estética/manutenção)
> agora é fonte de verdade estruturada em
> [`kitchen/specs/felipe_kitchen_preference_profile.json`](kitchen/specs/felipe_kitchen_preference_profile.json).

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
  HOW_TO_USE.md                     ← guia do Felipe: o ciclo de 6 passos + 4 gates
  DECISIONS.md  GOLDEN_SAMPLES.md  FELIPE_KITCHEN_PREFERENCES.md
  gates/reference_system_gates.md   ← os 4 gates de inteligência de uso + checks de tema escuro
  templates/  inbox/  analyzed/  themes/
  kitchen/
    EXAMPLE_001_KITCHEN.md          ← KITCHEN_WARM_COMPACT_PREMIUM (a régua / professor 001)
    specs/
      modern_warm_kitchen.json      ← DesignGrammarSpec do golden
      felipe_kitchen_preference_profile.json ← perfil do Felipe (uso/estética/manutenção), fonte de verdade
    references/
      versalle_cozinhas_planejadas.md ← referência curada (board Pinterest) lida como LINGUAGEM
    rules/                          ← regras acionáveis por eixo (perfil aterrado)
      material_maintenance.md       ← maintenance_gate virado decisão (SIM/CUIDADO/NÃO por material)
      appliance_niche_rules.md      ← obrigatórios + fluxo + respiro/tomada por eletro
      lighting_rules.md             ← LED quente 2700–3000K, mood noturno + daylight_reflection
    cards/
      card_schema.json              ← contrato fixo do card
      01..10_*.json                 ← 10 Reference Cards do golden (com categoria)
      11_hot_tower_appliance_column.json    (joinery_form_token — torre quente)
      12_reflecta_led_display_cabinet.json  (material_token — reflecta/champagne pontual + LED)
      13_no_white_block_cabinets.json       (material_token — escuro/meio-termo, anti branco puro)
      14_lower_drawer_storage.json          (joinery_form_token — gavetões inferiores)
      15_appliance_counter_clutter.json     (joinery_form_token — tirar eletro solto da bancada)
      16_maintenance_reality_check.json     (safety_gate — manutenção viável trava render bonito)
      17_warm_dark_industrial_palette.json  (material_token — paleta black_wood_gold)
```

## Tokens novos na KB (`references/tokens/`) — derivados do perfil do Felipe
- `coordinated_medium_dark_wood_base.json` — base madeira MÉDIA/ESCURA quente coordenada
  (alternativa escura ao `coordinated_oak_base`; industrial preto+madeira, anti branco).
- `reflecta_champagne_led_cabinet.json` — módulo(s) de vidro reflecta/champagne com LED interno
  como ponto de destaque (NÃO fachada; 1–2 módulos, respeita `reflecta_control_gate`).
- `hot_tower_niche.json` — torre quente forno+micro+airfryer em nichos coluna (respiro + tomada
  interna + altura ergonômica; handle-less).

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
