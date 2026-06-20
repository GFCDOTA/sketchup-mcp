# References — Knowledge Base de marcenaria planejada

> KB reutilizável que ensina o auto-mobiliado do `sketchup-mcp` a falar a
> LINGUAGEM de marcenaria planejada (cozinha primeiro; planta_74 como caso).
> **Não** é scraper, **não** guarda imagem. São arquivos de conhecimento curado
> (medidas, materiais, paletas, tokens, anti-padrões) que os agentes/pipeline
> consomem na hora de gerar e validar a marcenaria.

## Regra de ouro (vale pra tudo aqui)

```
referência = LINGUAGEM   ·   PDF = POSIÇÃO   ·   gates = SEGURANÇA   ·   Felipe = PASS
```

- **Referência manda na LINGUAGEM e na MEDIDA** — material, cor (RGB), acabamento,
  proporção, altura, clearance, anti-padrão.
- **O PDF manda na POSIÇÃO** — pia, ponto hidráulico, parede, porta, janela,
  circulação são IMUTÁVEIS. Nenhuma referência move a pia. O layout se organiza
  EM TORNO do que o PDF fixa.
- **Os gates são a segurança** — `tools/kitchen_ergonomics.py`,
  `tools/furniture_overlap_gate.py` etc. reprovam o que viola medida/colisão
  antes de mostrar.
- **Felipe é o PASS final** — veredito VISUAL (IMPROVED/SAME/WORSE) é humano,
  nunca auto.

Princípio mestre que atravessa toda a KB: **`loose_object → planned_niche_system`**
— nenhum eletro/objeto fica solto; cada um vira nicho planejado (painel + frente
flush + filler + respiro + fechamento).

## Golden sample (a régua já construída)

A cozinha da `planta_74` (`tools/kitchen_layout.py`, room `r004`) é a régua de
qualidade. Toda escolha desta KB é julgada contra a coerência dela:

| Papel | Material | RGB |
|---|---|---|
| Inferiores (corpo/porta/gaveta) | carvalho/freijó CLARO coordenado | `[191,167,137]` |
| Aéreo / torre / filler | laca FENDI quente (off-white, não branco puro) | `[224,215,199]` |
| Tampo + backsplash | pedra clara veio sutil | `[222,219,212]` |
| Sóculo / toe-kick | grafite fosco recuado | `[40,41,45]` |
| Puxador slim | grafite | `[44,45,50]` |
| Geladeira | inox escovado claro | `[216,220,227]` |
| Cooktop | vidro preto | `[22,22,26]` |
| Nicho de acento | madeira escura/mel | `[138,104,66]` |
| LED sob aéreo | quente 2700K | `[255,250,232]` |

Medidas-âncora (de `tools/kitchen_ergonomics.py`): bancada 85–92 cm · sóculo
10–15 cm · tampo 2–4 cm · profundidade base 55–60 cm · aéreo 30–35 cm ·
clearance bancada→aéreo 50–60 cm · coifa under-cabinet 45–65 / chaminé 70–80 cm ·
torre da geladeira 55–75 cm.

---

## Índice da KB

### `materials/` — LINGUAGEM de material (markdown curado)
Cada arquivo: tipos do material, aparência com **RGB aproximado**, custo relativo
(`$`–`$$$$`), prós/contras, **ONDE FALHA / anti-padrão**, e uma seção "decisão
rápida (para o gerador)".

| Arquivo | Cobre |
|---|---|
| [`materials/wood.md`](materials/wood.md) | carvalho, freijó, nogueira, MDF amadeirado, ripado — frentes, painéis, nichos |
| [`materials/stone.md`](materials/stone.md) | quartzo, granito, mármore, porcelanato/Dekton, nanoglass — tampo, backsplash, ilha |
| [`materials/lacquer.md`](materials/lacquer.md) | laca fosca/acetinada/gloss; a decisão fendi vs branco puro — aéreos, torres, fillers, ilha |
| [`materials/metal.md`](materials/metal.md) | inox escovado/polido, grafite, preto fosco, latão — puxadores, perfis, eletro, coifa, sóculo |

### `joinery_rules/` — MEDIDA + regra (markdown curado)
| Arquivo | Cobre |
|---|---|
| [`joinery_rules/kitchen_ergonomics.md`](joinery_rules/kitchen_ergonomics.md) | tabela mestra de medidas (cm) + porquê + erro comum de cada faixa; mapeada às constantes de `kitchen_layout.py` |
| [`joinery_rules/appliance_niches.md`](joinery_rules/appliance_niches.md) | a anatomia de 6 partes de qualquer nicho (geladeira/forno/micro/cooktop/coifa); checklist `loose_object → planned_niche_system` |
| [`joinery_rules/anti_patterns.md`](joinery_rules/anti_patterns.md) | os 8 defeitos builder-grade: sintoma → correção (objeto solto, branco chapado, madeira saturada, coifa solta, cuba rasa, pia fora do ponto, sem reveal, bicolor) |
| [`joinery_rules/premium_details.md`](joinery_rules/premium_details.md) | os 8 detalhes que "leem caro": shadow gap, handle-less, filler, torre integrada, LED, backsplash de pedra, tampo fino, sóculo recuado |

### `palettes/` — paletas coordenadas (JSON)
Mapa de papéis → material/finish/**RGB**, casado com os `kind`s `kc_*` que o
`kitchen_layout.py` colore. Inclui `pairing_rules` e `anti_pattern`.

| Arquivo | Conteúdo |
|---|---|
| [`palettes/modern_warm.json`](palettes/modern_warm.json) | paleta-mestra completa do golden sample (base/upper/tower/stone/toe_kick/appliance/hardware/led/wood_accent) |
| [`palettes/fendi_oak_stone.json`](palettes/fendi_oak_stone.json) | a tríade reduzida (FENDI + OAK + STONE + acentos grafite/inox) — 80% da leitura visual |

### `tokens/` — tokens de design acionáveis (JSON)
Schema comum: `name`, `title`, `rule` (texto), `params` (RGB + faixas em cm/m),
`applies_to_kinds` (`kc_*`), `anti_pattern`, `cost_relative`, `appearance`,
`gate_refs` (tools que validam), `source`. São a ponte direta entre a linguagem
e o gerador/gates.

| Arquivo | Token |
|---|---|
| [`tokens/coordinated_oak_base.json`](tokens/coordinated_oak_base.json) | base carvalho claro coordenada (mata o bicolor) |
| [`tokens/warm_fendi_upper.json`](tokens/warm_fendi_upper.json) | aéreo/torre fendi quente, nunca branco puro |
| [`tokens/subtle_veined_stone.json`](tokens/subtle_veined_stone.json) | tampo + backsplash pedra clara contínua, veio sutil |
| [`tokens/planned_fridge_tower.json`](tokens/planned_fridge_tower.json) | torre da geladeira integrada (`loose_object → planned_niche_system`) |
| [`tokens/premium_shadow_gap.json`](tokens/premium_shadow_gap.json) | reveal entre módulos + sóculo grafite recuado |
| [`tokens/under_cabinet_led.json`](tokens/under_cabinet_led.json) | fita LED quente 2700K sob o aéreo |

### `design_rules/` — rule cards (pré-existente, schema próprio)
| Arquivo | Conteúdo |
|---|---|
| [`design_rules/design_rule.schema.json`](design_rules/design_rule.schema.json) | JSON Schema do `DesignRuleCard` (room_type / rule_type / dimensions_m / source / implementation_target) |
| [`design_rules/furniture_rule_cards.json`](design_rules/furniture_rule_cards.json) | rule cards de mobília por cômodo |

---

## Como o pipeline consome

| Quem | Lê | Para |
|---|---|---|
| **`planned-joinery-translator`** (skill/agente) | `tokens/*.json` + paletas (gramática) | traduzir referência visual → GRAMÁTICA de design → componentes SketchUp editáveis, sem copiar imagem; obedecendo POSIÇÃO do PDF |
| **`joinery-ergonomics-reference`** (skill/agente) | `joinery_rules/kitchen_ergonomics.md` + as faixas dos tokens | validar alturas/clearances/profundidades (a metade "medida" do método) |
| **`kitchen_layout._KC`** (`tools/kitchen_layout.py`) | `palettes/*.json` (mapa `kc_*` → RGB) | colorir os `kind`s da marcenaria com a paleta coordenada do golden sample |
| **`vray_export` / `tweak_vrscene`** | `materials/*.md` (RGB base, finish, roughness/metalness, ONDE FALHA em render) | escolher cor difusa, acabamento e reflexo dos materiais V-Ray sem cair nos anti-padrões (branco-papel, gloss plástico, dourado cafona) |
| **gates** (`tools/kitchen_ergonomics.py`, `tools/furniture_overlap_gate.py`) | os `gate_refs` dos tokens + faixas de `kitchen_ergonomics.md` | reprovar medida fora da faixa ou colisão de módulos ANTES de mostrar |

**Fluxo:** referência/token define a LINGUAGEM e a MEDIDA → o PDF fixa a POSIÇÃO
→ o gerador (`kitchen_layout.py`) monta com as paletas → os gates de ergonomia/
overlap conferem a SEGURANÇA → o veredito VISUAL do Felipe dá o PASS.

> Onde estender: novo material → `materials/`; nova medida/regra → `joinery_rules/`;
> nova paleta coordenada → `palettes/`; novo token acionável (com `gate_refs` e
> `applies_to_kinds`) → `tokens/`. Sempre com RGB aproximado, custo relativo e
> ONDE FALHA — é o que torna a KB curada, não genérica.
