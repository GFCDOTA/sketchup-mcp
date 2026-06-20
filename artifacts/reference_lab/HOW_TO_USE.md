# Como usar o tradutor de referência — guia do Felipe

> **O que isto é:** o passo-a-passo de como VOCÊ (Felipe) usa o
> REFERENCE_TO_JOINERY_TRANSLATOR. Você CURA referências, o agente TRADUZ em
> marcenaria implementável. **Não é scraper, não baixa imagem em massa, não copia
> pixel.** Curadoria humana → tradução do agente → protótipo isolado → gates →
> render → **seu veredito**.
>
> **Hierarquia absoluta (decora isto):**
> `Pinterest = LINGUAGEM · PDF = POSIÇÃO · Gates = SEGURANÇA · Felipe = PASS.`
>
> O que o agente FAZ: extrair decisões repetíveis (tema, materiais, ergonomia,
> manutenção, buildability) e aplicar como skin/forma DENTRO do envelope do PDF.
> O que o agente NUNCA faz: mover pia/parede/porta/janela/shaft/área de serviço,
> inventar ilha, mudar a planta por causa de uma foto, ou cravar PASS sozinho.

---

## O ciclo em 6 passos

```
1. COLAR    você larga prints/URLs curados em  inbox/
2. ANALISAR agente lê → analyzed/<nome>.analysis.md  (10 saídas + 4 gates)
3. COMPILAR vira card (cards/) + token (references/tokens/) + spec (specs/)
4. PROTÓTIPO aplica num COMPONENTE ISOLADO / skin-swap — NUNCA a cozinha real direto
5. VALIDAR  roda gates + render (V-Ray)
6. VEREDITO para. Você julga A/B/C → PASS / WARN / reprovar
```

Regra-mãe que atravessa os 6 passos:
```
Medida/forma de Pinterest = HIPÓTESE.
PDF + ergonomia + gate    = VERDADE.
```

### Passo 1 — COLAR (você cura, sem scraping)
- Joga os prints curados em `inbox/`: `pinterest_001.png`, `pinterest_002.png`…
  (qualquer fonte; pode ser URL no sidecar). Curadoria humana — **nada de
  download em lote ou cópia literal de imagem.**
- O melhor lote é 1–5 referências boas. **10 cards bem feitos > 500 imagens.**
- Ver `inbox/README.md`.

### Passo 2 — ANALISAR (agente → sidecar)
- Para CADA imagem, o agente produz `analyzed/<nome>.analysis.md` seguindo
  `templates/reference_analysis_template.md`: **as 10 saídas** + a tabela dos
  **4 gates** (PASS/WARN/FAIL). Exemplo trabalhado real:
  `analyzed/pinterest_001_dark_walnut.analysis.md`.
- O sidecar SEPARA `FORMA × PELE` (senão o agente mistura "botar pedra bonita" com
  "mudar layout" e destrói a planta).

### Passo 3 — COMPILAR (card + token + spec)
- A decisão repetível vira um **Reference Card** em `kitchen/cards/<id>.json`
  (contrato fixo em `kitchen/cards/card_schema.json`). Todo card declara uma
  **categoria** — é ela que protege o PDF:

  | categoria | camada | pode mexer? |
  |---|---|---|
  | `joinery_form_token` | FORMA (torre, gola, coifa, filler, sóculo, proporção) | só dentro do envelope do PDF; **nunca move âncora** |
  | `material_token` | PELE (fendi, madeira, pedra, inox) | livre (acabamento) |
  | `lighting_token` | LUZ (LED linear, rig) | livre |
  | `camera_token` | CÂMERA (crop/FOV/hero) | livre (não toca geometria) |
  | `safety_gate` | TRAVA (pia fixa, circulação) | bloqueia |

- Parâmetro reusável vira **token** em `references/tokens/` (fonte ÚNICA — o card
  só referencia, não copia). Tokens prontos: `planned_fridge_tower`,
  `warm_fendi_upper`, `coordinated_oak_base`, `subtle_veined_stone`,
  `under_cabinet_led`, `premium_shadow_gap`.
- O conjunto de cards de um caso vira a **DesignGrammarSpec**
  (`kitchen/specs/<nome>.json`, ex. `modern_warm_kitchen.json`) e/ou um **theme
  preset** em `themes/<NOME>.json` (consumido por `KITCHEN_THEME`).

### Passo 4 — PROTÓTIPO (isolado, NUNCA a cozinha real)
- A tradução é aplicada **num componente isolado / skin-swap sobre a MESMA
  geometria congelada da planta_74** — nunca direto na cozinha real e nunca antes
  da spec existir.
- É skin-swap, não rebuild: muda PELE/LUZ/CÂMERA e FORMA só dentro do envelope.
  A geometria da cozinha planta_74 está **congelada** (DECISION 001) — não se
  toca `.skp`/`kitchen_layout.py`/âncora sem autorização explícita do Felipe.

### Passo 5 — VALIDAR (gates + render)
- Roda os **4 gates de inteligência de uso** (abaixo) + os gates de fidelidade já
  existentes. Renderiza A/B/C (hero + montagem) pra comparação visual real.
- Se um gate dá FAIL/WARN, ele vira regra/ajuste antes de mostrar — não se
  empurra defeito pro seu olho.

### Passo 6 — VEREDITO (para pro Felipe)
- O agente PARA e te mostra. **GPT é checkpoint, você é o juiz.** Nada vira
  golden sample sem o seu PASS.
- Seu processo (DECISION 003): fecha preferências → atualiza agente → gera 3
  variações reais → julga A/B/C → **só depois** olha Pinterest em lote e desce
  pra material/cuba/manutenção/custo. **Não gerar 30 imagens no olhômetro.**

---

## Os 4 gates de inteligência de uso

Além dos gates de fidelidade (kitchen_validation, furniture_overlap,
geometry_sanity). Definição completa em `gates/reference_system_gates.md`. Cada
análise e cada theme preset declara um veredito por gate.

1. **theme_fit_gate** — a vibe transfere pra cozinha COMPACTA linear da planta_74,
   ou só funciona em mansão/loft? FAIL se exige ilha / bancada em L / coifa
   industrial gigante / pé-direito alto.
2. **ergonomics_gate** — alturas/alcance/circulação fazem sentido pro uso diário?
   Ferramenta: `tools/kitchen_ergonomics.py` (12 medidas; bancada 88–92, sóculo
   10–15, aéreo 30–35, coifa 45–65, torre 60–75, etc.). Medida da referência entra
   como hipótese; o gate valida contra a faixa + o PDF.
3. **maintenance_gate** — vai dar dor de cabeça na vida real? FAIL: vão que só pega
   poeira, madeira na zona molhada sem proteção (`wood_wetzone_gate`), nicho fundo
   sem acesso, ripado que junta gordura. WARN: preto fosco/ultra-gloss marca dedo.
4. **buildability_gate** — marcenaria executa, ou é truque de render? FAIL:
   balanço impossível, eletro que não cabe no nicho, "flutua" sem suporte, medida
   que ignora espessura de chapa/eletro/norma.

Para temas escuros/premium (BLACK_WOOD_GOLD) há os checks extras de
`gates/reference_system_gates.md` (cave_check, daylight_reflection_check,
reflecta_control_gate, black_floor_gate, fake_luxury_check…). Critério de sucesso
do tema escuro: **impacto MAS continuar usável, limpável e claro de dia.**

---

## OUTPUT PADRÃO por referência (o que você recebe de volta)

Cada referência colada volta com este pacote (é o miolo das 10 saídas + adaptação
à planta). Formato fixo em `templates/reference_analysis_template.md`:

```
1.  NOME / fonte ............ slug + de onde veio (curadoria sua)
2.  O QUE TEM DE BOM ........ tema/paleta/textura/luz/sensação que vale copiar
3.  O QUE NÃO COPIAR ........ layout de mansão, ilha, coifa gigante, vão de poeira,
                              madeira na zona molhada, estrutura que só cabe em loft
4.  GRAMÁTICA (forma×pele) .. o que é FORMA (joinery) vs PELE (material/luz/câmera)
5.  MATERIAIS .............. famílias + acabamento (fosco/satin), com risco de uso
6.  PALETA ................. RGB/famílias de cor + temperatura de luz (2700K…)
7.  TOKENS SUGERIDOS ....... reusar token existente em references/tokens/ ou criar novo
8.  RISCOS DE MANUTENÇÃO ... poeira/mancha/digital/limpeza (vira nota no maintenance_gate)
9.  COMO ADAPTAR À planta_74 medidas/proporção/intensidade ajustadas ao COMPACTO linear
10. V-RAY vs GEOMETRIA ..... o que é só render (material/luz/câmera) vs o que mexe forma
11. PRÓXIMO EXPERIMENTO .... a próxima variação A/B/C a gerar
```

E a tabela de veredito:

```
| gate              | veredito        | nota |
| theme_fit_gate    | PASS/WARN/FAIL  | ...  |
| ergonomics_gate   | PASS/WARN/FAIL  | ...  |
| maintenance_gate  | PASS/WARN/FAIL  | ...  |
| buildability_gate | PASS/WARN/FAIL  | ...  |
```

**V-Ray vs geometria** (item 10) importa pra você saber o custo de cada decisão:
- **Só V-Ray / barato** = `material_token` + `lighting_token` + `camera_token`
  (skin-swap; pele, luz, enquadramento — não toca .skp).
- **Mexe geometria / caro e travado pelo PDF** = `joinery_form_token` (torre,
  gola, coifa, sóculo, proporção) — só dentro do envelope, nunca a âncora.

---

## Estrutura de pastas

```
artifacts/reference_lab/
  HOW_TO_USE.md                ← este guia
  README.md                    ← o que é o lab + FORMA×PELE + KB vs Lab
  DECISIONS.md                 ← decisões congeladas (DECISION 001/002/003)
  GOLDEN_SAMPLES.md            ← biblioteca de temas com seu PASS
  FELIPE_KITCHEN_PREFERENCES.md ← suas preferências = restrição do agente
  gates/
    reference_system_gates.md  ← os 4 gates + checks de tema escuro
  templates/
    reference_analysis_template.md ← formato do sidecar (10 saídas + 4 gates)
  inbox/                       ← VOCÊ cola os prints curados aqui (sem scraping)
  analyzed/                    ← agente escreve <nome>.analysis.md aqui
    pinterest_001_dark_walnut.analysis.md ← exemplo trabalhado real
  themes/                      ← presets aplicáveis (KITCHEN_THEME): 4 temas
  renders/                     ← heros + montagens A/B/C
  kitchen/
    EXAMPLE_001_KITCHEN.md     ← o "professor 001" (régua de comparação)
    cards/                     ← Reference Cards 01..10 + card_schema.json
    specs/                     ← DesignGrammarSpec (modern_warm_kitchen.json)
  kitchen_dark_walnut/         ← EXAMPLE_002 + cards + spec (variante autoral)
  kitchen_hotel_boutique/      ← preset boutique

references/                    ← KB (livro-texto, NÃO casos): fonte única
  tokens/                      ← 6 tokens canônicos (cards referenciam, não copiam)
  joinery_rules/               ← kitchen_ergonomics, anti_patterns,
                                 appliance_niches, premium_details
  materials/  palettes/  design_rules/
```

> **KB (`references/`) vs Lab (`artifacts/reference_lab/`):** a KB é o livro-texto
> (materiais, ergonomia, anti-padrões, tokens — conhecimento geral, fonte única);
> o Lab são estudos de caso concretos com antes/depois e cards. O card referencia
> o token da KB, **não copia**.

---

## Atalhos importantes (leia estes)

- **`FELIPE_KITCHEN_PREFERENCES.md`** — suas preferências viram RESTRIÇÃO do
  agente (DECISION 003). Direção aprovada: **BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE**
  (preto fosco + madeira quente + pedra escura/quente com veio dourado SUTIL +
  cuba/torneira pretas + bronze discreto + LED 2700K). Gostou: armário até o teto,
  gavetões, LED linear quente, reflecta/champagne pontual com LED, sem puxador
  tradicional. NÃO gostou: pia com textura de madeira, tudo preto sem luz, piso
  preto demais, veio dourado exagerado, reflecta em todos os aéreos, LED frio.
- **`GOLDEN_SAMPLES.md`** — biblioteca de temas com seu PASS. Hoje:
  `warm_compact_premium` (a clara VENDE), `dark_walnut_moody_premium` (a dark
  IMPRESSIONA), `hotel_boutique_warm_luxury` (a boutique CONVENCE) +
  `black_wood_gold_industrial_boutique` (GPT PASS, aguarda seu veredito). Seu
  ranking pro apê real: 1º boutique · 2º warm · 3º dark.
- **Seu perfil** — vive em `FELIPE_KITCHEN_PREFERENCES.md` (perfil de cozinha) +
  `EXAMPLE_001_KITCHEN.md` (a régua). *Não há um perfil em JSON separado hoje — o
  perfil é o `.md` de preferências + os gates; se um dia virar JSON, mora em
  `references/`.*
- **A skill que opera tudo isto:**
  `.claude/skills/reference-to-joinery-translator/SKILL.md`.

---

## O que NUNCA acontece (suas travas)

- Mover pia / ponto hidráulico / parede / porta / shaft / área de serviço.
- Inventar ilha ou mudar a planta por causa de uma foto.
- Aplicar na cozinha REAL sem spec/protótipo + gates antes.
- Copiar imagem literalmente / scraping em massa.
- Tratar medida de Pinterest como verdade técnica (é hipótese).
- O agente cravar PASS sozinho — **o golden sample só nasce com o SEU OK.**
