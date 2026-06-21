# Geladeira — cozinha planta_74 (REFRIGERATION SPEC)

> Spec acionável pra cozinha linear BLACK_WOOD_GOLD do apto ~74 m² (Felipe +
> namorada, visitas eventuais, uso moderado). A POSIÇÃO da torre vem do PDF/layout
> (geladeira numa ponta da bancada, torre integrada até o teto). Esta spec dita
> TIPO, CAPACIDADE, DIMENSÃO DE NICHO e ACABAMENTO — vira input do
> `kitchen_layout.py` (constantes `GEL_*`) e do prévio pro arquiteto/marceneiro.
>
> **Direção aprovada:** preto/grafite fosco + madeira quente + pedra escura com
> veio dourado + cuba/torneira preta + bronze discreto + LED 2700K. Geladeira
> NÃO pode virar "bloco branco/inox brilhante" no meio da marcenaria escura.

---

## 0. TL;DR — a recomendação (ler isto primeiro)

- **Tipo:** geladeira **inverse / bottom-freezer** (freezer embaixo, gaveta) —
  porta única de geladeira na altura dos olhos, freezer-gaveta embaixo.
- **Capacidade:** **400–460 L** (faixa "frost free duplex grande / inverse de
  60 cm"). Folga real pra 2 pessoas + visita eventual + futuro, sem virar
  side-by-side de família grande.
- **Acabamento:** **preto fosco / black inox antidigital** (Brastemp Black Inox,
  Electrolux Black, ou linha "dark" equivalente). Casa direto com black_wood_gold
  e some o problema #1 do inox claro (marca de dedo).
- **Nicho da torre:** **largura 75 cm × profundidade 70 cm × altura útil 185–190 cm
  pro corpo** (geladeira ≤ 180 cm de altura), com **armário até o teto por cima**.
  Respiro: **≥ 3 cm cada lado lateral, ≥ 5 cm no topo (entre topo da geladeira e
  fundo do armário), ≥ 5 cm atrás** pro condensador respirar.
- **Casa com a torre atual da planta_74?** **Quase.** `GEL_W 70 / GEL_D 66 /
  GEL_H 180` está coerente em altura e profundidade, mas a **largura de nicho de
  70 cm é apertada pra uma geladeira de corpo 60 cm com respiro de verdade** — ver
  §6. Recomendo subir o nicho pra **GEL_W 0.75** e manter `GEL_H 1.80` /
  `GEL_D 0.66`.

---

## 1. Tipos de geladeira — qual entra nesta cozinha

Ordenado do menos pro mais indicado pra ESTA cozinha (linear compacta, 2 pessoas,
torre integrada, visual escuro).

### 1 porta (frigobar / 1 porta convencional)
- **O que é:** um compartimento, freezer minúsculo interno ou nenhum.
- **Prós:** estreita (50–55 cm), barata, cabe em qualquer canto.
- **Contras:** congelador ridículo pra casal que faz hambúrguer/bife/frituras
  (precisa estocar carne). Sem frost free na maioria → vira bloco de gelo.
- **Veredito:** ❌ subdimensionada. Só pra kitnet de 1 pessoa. Fora.

### Duplex top-mount (freezer EM CIMA — a clássica brasileira)
- **O que é:** freezer no topo, geladeira embaixo. O formato mais comum/barato do BR.
- **Prós:** **mais barata** da categoria grande (`$`), peça-padrão, frost free,
  ampla oferta de 350–450 L, fácil de achar em preto.
- **Contras:** o compartimento que você MAIS usa (geladeira) fica embaixo →
  agachar pra pegar a hortaliça do dia a dia. Freezer no topo = você abaixa menos
  pra congelado (que você abre menos). Ergonomia invertida.
- **Veredito:** ✅ válida e econômica. É o **plano B** se quiser cortar custo.

### Inverse / bottom-freezer (freezer EMBAIXO, gaveta) — **RECOMENDADA**
- **O que é:** geladeira em cima (porta na altura dos olhos), freezer em gaveta
  embaixo. Premium "discreto" do mercado BR.
- **Prós:** **ergonomia certa** — o que você usa todo dia (geladeira) na altura
  confortável; congelado em gaveta puxa fácil sem virar caverna. Visual mais
  "planejado"/europeu, linha boa em **preto fosco**. Frost free.
- **Contras:** **mais cara** que a top-mount (`$$`), oferta menor de modelos.
- **Veredito:** ✅✅ **a escolha** pro perfil. Ergonomia + estética premium discreta
  casa exatamente com a cozinha planejada escura.

### French door (2 portas em cima + gaveta-freezer)
- **O que é:** geladeira de duas folhas no topo, freezer-gaveta embaixo. As folhas
  estreitas abrem em meio-arco — bom pra corredor apertado.
- **Prós:** **portas estreitas** = abrem em pouco espaço (ótimo em cozinha linear
  estreita); cara de cozinha de revista; cabe travessa larga; linhas em black inox.
- **Contras:** **larga** (normalmente 70–91 cm de corpo, 450–600 L) → quer nicho
  ≥ 80 cm. Em 60–75 cm de nicho **não cabe**. Mais cara (`$$$`).
- **Veredito:** ⚠️ linda e ergonômica, mas **estoura o nicho** de 70–75 cm da
  torre linear da planta_74. Só entraria se o nicho fosse pra ≥ 80 cm — o que
  rouba bancada numa cozinha já compacta. Reservar pra cozinha em L/U futura.

### Side-by-side (geladeira | freezer lado a lado, 2 portas verticais)
- **O que é:** metade geladeira, metade freezer, full-height, portas verticais.
- **Prós:** muito freezer, dispenser de gelo/água na porta, presença visual.
- **Contras:** **larga (85–95 cm)** e **funda (70–75 cm)** → exige nicho enorme;
  cada compartimento fica estreito (travessa não entra de frente); a mais cara
  (`$$$$`); o dispenser de água precisa de ponto hidráulico atrás.
- **Veredito:** ❌ superdimensionada e larga demais pra 2 pessoas em cozinha
  linear de 74 m². Estoura o nicho e a bancada. Fora.

---

## 2. Capacidade (litros) — quanto pra este perfil

**Perfil:** 2 moradores fixos, visitas eventuais (não recebe jantar de 10 toda
semana), uso moderado real (ovo, frango, bife, hambúrguer, fritura leve) →
**estoca proteína e congelado**, mas não é freezer de açougue.

| Cenário | Faixa | Comentário |
|---|---|---|
| Mínimo viável (2 pessoas, sem folga) | 300–350 L | Aperta na semana de compra grande; freezer pequeno encrenca com a carne. |
| **Recomendado (2 + visita + futuro)** | **400–460 L** | Folga real: bandeja de marmita, cerveja de visita, estoque de congelado. Largura de corpo ~60 cm → cabe no nicho linear. |
| Generoso (recebe muito / família futura) | 480–540 L | Já tende a French door/duplex largo → estoura o nicho de 75 cm. Só se virar cozinha L/U. |

**Trava física:** acima de ~460 L em formato compatível com nicho de 60 cm a
geladeira começa a **crescer em ALTURA** (até ~190 cm) ou em **PROFUNDIDADE**
(>70 cm) — não em largura. Como o `GEL_H` da torre é 180 cm, fique em modelos
**≤ 180 cm de altura de corpo** (ver §5). Por isso **400–460 L** é o ponto doce:
máxima capacidade que ainda cabe num corpo de 60 cm × ≤180 cm de altura.

**Recomendação concreta:** **~430 L (faixa 400–460), inverse/bottom-freezer,
corpo 60 cm largura × ≤180 cm altura.**

---

## 3. Acabamento — coerência com BLACK_WOOD_GOLD

O Felipe **não gosta de branco chapado** e a paleta é escura/moody. A geladeira é
uma superfície grande e vertical — ela define muito do "peso" visual da torre.
Três caminhos:

### (A) Preto fosco / Black Inox antidigital — **RECOMENDADO**
- **O que é:** porta em aço com acabamento preto fosco/grafite, tratamento
  anti-impressão digital (Brastemp Black Inox, Electrolux Black/IXBlack, linhas
  "dark" das marcas premium nacionais).
- **Prós:** casa **direto** com grafite fosco + madeira quente + pedra escura;
  o anti-digital resolve o problema #1 do inox (marca de dedo); **sem custo de
  marcenaria extra** (é a porta de fábrica). Leitura premium-moody honesta, não
  fake luxury.
- **Contras:** preto **MOSTRA poeira clara/respingo de água** mais que inox claro
  (mancha de cor oposta) — mas o perfil quer "manutenção viável", e passar pano
  numa porta lisa é trivial (≠ pó no piso). Oferta menor de modelos em preto que
  em inox/branco → escolher dentro do que existe em preto.
- **Manutenção:** pano úmido + microfibra seca; sem produto abrasivo (risca o
  fosco). Onde falha: respingo de molho seco vira marca visível no preto → limpar
  na hora.
- **Veredito:** ✅✅ o casamento mais limpo com a direção aprovada e o que dá menos
  trabalho de integração.

### (B) Inox dark / grafite escovado
- **O que é:** inox tradicional num tom mais escuro/grafite (não o inox prateado claro).
- **Prós:** clássico, durável, ampla oferta; tom escuro puxa pra paleta sem ser preto puro.
- **Contras:** **inox claro/escovado marca digital** e mancha de água com timbre —
  exatamente o que o anti-digital preto resolve. O inox **prateado claro brigaria**
  com a paleta escura (vira ponto frio/brilhante no meio da madeira quente).
- **Veredito:** ⚠️ aceitável SE for o grafite escovado escuro (não o inox prata).
  Plano B do acabamento.

### (C) Panel-ready (geladeira revestida na marcenaria — porta de madeira/laca)
- **O que é:** geladeira de embutir cujo painel frontal recebe a MESMA folha da
  marcenaria → some completamente na torre.
- **Prós:** integração total — a torre vira um pano contínuo de madeira/preto, sem
  "eletrodoméstico aparecendo". É o ápice do "loose_object → planned_niche_system".
- **Contras:** **a mais cara** — geladeira panel-ready/de embutir custa muito mais
  (`$$$$`) e a oferta no BR é restrita (poucos modelos, quase sempre importados);
  **+ custo de marcenaria** pro painel e dobradiça especial; capacidade tende a ser
  MENOR (corpo de embutir 54–56 cm interno) → conflita com a meta de 400–460 L.
- **Manutenção:** painel de madeira na porta da geladeira pega umidade/respingo de
  geladeira → cuidar do acabamento (verniz/laca resistente).
- **Veredito:** 🟡 sonho-alto VÁLIDO, mas **não para o orçamento/uso deste apê
  agora**. Anotar como "upgrade futuro se virar reforma cara". Para a entrega atual:
  **preto fosco (A)** dá 90% do efeito por uma fração do custo.

**Decisão de acabamento:** **(A) preto fosco / black inox antidigital.** Painel
frontal liso, **sem puxador tradicional** — preferir modelo com **pega embutida /
cava na lateral da porta** ou abertura por toque, coerente com a regra "sem
puxador" da marcenaria. RGB-alvo de material (render): porta preto-grafite fosco
`[34,34,36]`–`[40,40,42]` (mesmo registro do granito leathered escuro da paleta),
roughness alta, reflexo baixo (NÃO inox `[216,220,227]` brilhante — esse é claro
demais pra paleta escura; ver §6).

---

## 4. Recomendação consolidada (o que vai pro marceneiro / spec)

| Item | Valor |
|---|---|
| **Tipo** | Inverse / bottom-freezer (freezer-gaveta embaixo). Plano B: duplex top-mount. |
| **Capacidade** | 400–460 L (alvo ~430 L) |
| **Corpo (real)** | largura ~60 cm · profundidade ~66–70 cm · **altura ≤ 180 cm** |
| **Acabamento** | Preto fosco / black inox antidigital, porta lisa, pega embutida |
| **Posição** | Ponta da bancada linear (lado oposto à torre quente), em TORRE integrada |
| **Topo** | Armário até o teto POR CIMA (linha superior contínua com o aéreo) |

---

## 5. Dimensão do nicho / torre (cm) — número pro arquiteto

Geladeira freestanding de 400–460 L, corpo ~60 cm. Nicho = **corpo + respiro**.

```
NICHO DA GELADEIRA (na torre integrada)
┌─────────────── largura 75 cm ───────────────┐
│  3 cm │      corpo geladeira ~60 cm     │ 3 cm │   ← respiro lateral ≥3 cm/lado
│ respiro│                                │respiro│      (dobradiça precisa de folga p/ porta abrir 90°+)
├────────┴────────────────────────────────┴──────┤
│  ↑ ≥5 cm respiro superior (topo geladeira → fundo armário)  │
├──────────────────────────────────────────────────┤
│            ARMÁRIO ATÉ O TETO (por cima)          │
└──────────────────────────────────────────────────┘
  profundidade do nicho: 70 cm   (corpo 66 + ≥5 cm atrás p/ condensador)
  altura útil do corpo:  ≤ 180 cm
```

- **Largura do nicho:** **75 cm** (corpo 60 + 2×~3 cm respiro + folga de dobradiça).
  Mínimo absoluto 70 cm (aperta a abertura da porta); 75 cm é o conforto.
- **Profundidade do nicho:** **70 cm** (corpo até ~70 incluindo puxador/porta;
  + folga atrás pro condensador respirar). A geladeira **fica mais funda que a
  bancada de 60 cm** — por isso ela vive na TORRE/coluna, não embaixo da bancada
  (corpo de 66–70 cm não cabe sob tampo de 60). Encosta a frente alinhada com o
  rosto dos armários (geladeira sobressai ~6–10 cm da linha da bancada — normal e
  esperado em planejado).
- **Altura do corpo:** **≤ 180 cm**. Acima disso o armário superior some.
- **Respiro (CRÍTICO — onde falha se errar):**
  - Lateral: **≥ 3 cm cada lado** (a porta precisa abrir além de 90° pra puxar
    gaveta; encostada na parede a dobradiça trava e a gaveta interna não sai).
  - Topo: **≥ 5 cm** entre topo da geladeira e fundo do armário (condensador
    moderno dissipa calor pra cima/atrás; abafado → motor trabalha mais, consome
    mais, vida curta).
  - Fundo: **≥ 5 cm** atrás (mesma razão). Não vedar a coluna por trás.
  - **Anti-padrão:** marcenaria "justa milimétrica" na geladeira é defeito clássico
    de planejado — fica lindo no projeto, superaquece e estraga o motor na vida real.

---

## 6. Casa com a TORRE integrada atual da planta_74? (GEL_W 70 / GEL_D 66 / GEL_H 180)

Constantes hoje em `tools/kitchen_layout.py`:
`GEL_W, GEL_D, GEL_H = 0.70, 0.66, 1.80` (nicho da geladeira) + um armário
`aereo_fridge` que tampa do topo da geladeira (180 cm) até a linha do aéreo
(armário até o teto — ✅ já faz isso), corpo inset 1.4 cm (`inset_side=0.014`).

| Dimensão | Atual | Recomendado | Veredito |
|---|---|---|---|
| **Altura `GEL_H`** | 1.80 m | ≤ 1.80 m | ✅ **bate.** 180 cm é o teto certo pro corpo, com armário por cima até o forro. |
| **Profundidade `GEL_D`** | 0.66 m | 0.66–0.70 m | ✅ **bate** (no limite). 66 cm acomoda corpo + algum respiro atrás; se o modelo for 70 cm de corpo, subir pra 0.70. |
| **Largura `GEL_W`** | 0.70 m | **0.75 m** | ⚠️ **apertado.** 70 cm de nicho com corpo de ~60 cm dá só ~10 cm pra DOIS lados de respiro + folga de dobradiça (5 cm/lado bruto, menos a espessura do painel da torre). Funciona, mas **sem conforto de abertura de porta**. Hoje o código usa `inset_side=0.014` (1,4 cm/lado de respiro) → respiro REAL ~1,4 cm, **abaixo dos 3 cm recomendados**. |

**Ação recomendada (vira input pro `kitchen_layout.py`, NÃO editado aqui):**
- Subir **`GEL_W` de 0.70 → 0.75** (nicho 75 cm) para dar respiro lateral honesto
  (≥ 3 cm/lado) e folga de dobradiça. Em cozinha linear compacta, 5 cm extra de
  largura é aceitável se a bancada continua > 60 cm de área útil de trabalho.
- Manter **`GEL_H = 1.80`** e **`GEL_D = 0.66`** (subir pra 0.70 só se o modelo
  escolhido tiver corpo de 70 cm).
- Aumentar o respiro lateral modelado: hoje `inset_side=0.014` (1,4 cm). Com nicho
  de 75 cm e corpo de 60, dá pra modelar **inset_side ≈ 0.06–0.07** (≈ 6–7 cm/lado
  total no nicho de 75 → corpo ~61–63), refletindo o respiro real ≥ 3 cm/lado.
- **Cor do corpo (render):** hoje `RGB_GELADEIRA / "geladeira" = [216,220,227]`
  (inox claro reflexivo). Pra BLACK_WOOD_GOLD isso é **claro/frio demais** — vira
  o bloco brilhante que o briefing quer evitar. **Mudar pra preto-grafite fosco
  `[36,36,38]`** (registro do granito leathered escuro do `stone.md`), roughness
  alta, reflexo baixo. O reveal escuro freezer/fridge (`soculo`) e o puxador slim
  continuam coerentes; **mas** com "sem puxador tradicional" o ideal é trocar a
  barra longa (`panel(...puxador...)` da geladeira) por **cava/pega embutida** —
  marcar como follow-up de geometria (fora do escopo desta spec, que é só
  conhecimento).

**Resumo do "bate?":** altura e profundidade ✅; **largura precisa subir de 70 → 75
cm** e a **cor do corpo precisa ir de inox claro pra preto fosco** pra fechar com a
direção aprovada. A arquitetura da torre (geladeira embaixo + armário até o teto
por cima, linha superior contínua) já está correta.

---

## 7. Onde falha (checklist pro marceneiro não errar)

- ❌ Nicho justo sem respiro → motor superaquece, conta de luz sobe, vida curta.
  **Sempre ≥ 3 cm lateral, ≥ 5 cm topo/fundo.**
- ❌ Geladeira encostada na parede do lado da dobradiça → porta não abre 90°+ →
  gaveta interna/freezer não sai. Deixar o respiro do lado da abertura.
- ❌ Inox claro/brilhante na paleta escura → ponto frio que quebra o moody.
  Usar preto fosco antidigital.
- ❌ French door / side-by-side num nicho de 75 cm → não cabe. Manter inverse de
  corpo 60 cm.
- ❌ Panel-ready agora → custo + oferta restrita + capacidade menor. Adiar.
- ❌ Esquecer ponto elétrico dedicado atrás do nicho (tomada 10A/20A na altura
  certa, ~ meia altura, sem encostar no condensador). Geladeira NÃO compartilha
  circuito com cooktop/forno da torre quente.
- ⚠️ Confirmar largura de corpo do MODELO real escolhido antes de fechar o nicho —
  60 cm é a referência, mas alguns inverse vão a 63 cm.
