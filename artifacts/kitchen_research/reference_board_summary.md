# Reference Board Summary — Cozinha Planejada PREMIUM (compacta, linear)

> ARTEFATO DE PESQUISA (spec, não código). Mina a GRAMÁTICA visual de "planejado
> caro" pra cozinha compacta da planta_74 (room **r004**, galley LINEAR na parede
> OESTE). NÃO é cópia de imagem: extrai LINGUAGEM (paleta/solução/proporção).
>
> **Regra máxima:** referência manda na LINGUAGEM · PDF manda na POSIÇÃO (pia/parede/
> porta FIXAS, layout LINEAR — não vira U/L) · gates mandam na SEGURANÇA · Felipe dá o
> PASS final. O flat (massa/material básico) NÃO mostra veio de pedra / reflexo de inox /
> brilho de LED — isso é leitura de V-Ray, não de gate de forma.
>
> Contexto físico real (grounded, PT_TO_M=0.0259): r004 = **1.82 m × 2.94 m = 5.29 m²**.
> Parede OESTE (anchor da pia) = run útil de bancada ~2.6 m. É uma cozinha APERTADA —
> a gramática tem que ler caro num corredor estreito, sem virar canto.

---

## 1. Paleta em CAMADAS (a alma do "planejado caro")

O salto de "armário de cozinha" pra "planejado premium" é a **estratificação tonal**:
6 camadas com papéis distintos, contraste BAIXO entre vizinhas (nada de branco-puro
contra preto). Quente em todo lugar; o único frio é o eletro (inox/cooktop).

| Camada | Papel | Linguagem da referência | RGB-alvo (flat) | `_KC` key hoje | Status |
|---|---|---|---|---|---|
| **INFERIOR (base)** | gabinetes do chão, gaveteiro, porta | carvalho/freijó natural MÉDIO, veio aparente, mate | `[171,140,100]` corpo · `[176,145,104]` porta/gaveta | `corpo`/`porta`/`gaveta` | ✅ bate |
| **SUPERIOR (aéreo)** | armário de parede, carcaça+porta | off-white QUENTE / fendi (NÃO branco puro 255) | `[224,215,199]` corpo · `[228,220,204]` porta | `corpo_sup`/`porta_sup` | ✅ bate |
| **TORRE / FILLER** | coluna da geladeira (filler + armário flush) | MESMO fendi do aéreo → coluna lê COESA, não 3 caixas soltas | `[224,215,199]` | `filler` | ✅ bate (continuidade tonal) |
| **PEDRA (tampo+backsplash)** | superfície protagonista | pedra clara quente, VEIO cinza/bege sutil, tampo FINO | `[222,219,212]` | `tampo`/`backsplash` | ✅ bate · veio = V-Ray |
| **DETALHE (grafite)** | sóculo, grelha da coifa, puxador slim, gola, reveals | grafite SÓ em linhas finas e no rodapé (acento, não massa) | `[40,41,45]` sóculo · `[44,45,50]` puxador · `[44,44,48]` gola | `soculo`/`puxador`/`torneira`/`gola` | ✅ bate |
| **LED (luz)** | fita sob o aéreo, lavando o backsplash | branco QUENTE 3000K (255,250,232), não branco-azulado | `[255,250,232]` | `led` | ✅ bate (cor); brilho real = V-Ray |

Acentos pontuais (fora da estratificação principal):
- **Nicho de madeira** (fundo+prateleira no aéreo): madeira mais ESCURA que a base —
  `niche_wood [162,130,90]` — pra quebrar o blocão off-white. ✅ presente.
- **Inox** (cuba/geladeira): único tom FRIO, reflexivo. Geladeira `[216,220,227]`
  (claro, menos "bloco cinza"); bojo da cuba ESCURO `cuba [92,96,103]` pra ler
  profundidade no flat. ✅ presente.
- **Cooktop preto** `vidro [22,22,26]`: vidro fino quase flush. ✅ presente.

**Regras de paleta (o que faz parecer caro):**
1. **Contraste baixo entre camadas adjacentes** — base quente ↔ aéreo fendi ↔ pedra
   clara são todos no mesmo "lado quente". O ÚNICO contraste forte é grafite (fino) e
   inox (pontual). Branco-puro 255 contra preto chapado = lê "barato/genérico".
2. **Quente em tudo** — nenhuma camada cai pro cinza-azulado, exceto o eletro frio
   (que ganha justamente por ser a exceção).
3. **Continuidade tonal vertical na torre** — geladeira+filler+armário-flush no MESMO
   fendi = coluna única. Cor diferente por peça = lê montagem de caixas.

---

## 2. Soluções RECORRENTES de "planejado" (o vocabulário do premium)

Padrões que aparecem repetidamente no board e SEPARAM planejado de modulado-de-loja.
Princípio-mãe: **`loose_object → planned_niche_system`** (nada solto; tudo embutido,
flush, com junta intencional).

1. **Torre de eletro integrada (coluna full-height).** Geladeira não é caixa solta —
   vira COLUNA: filler lateral + armário superior flush no topo, alinhado à linha do
   aéreo. Topo da torre = topo do aéreo (linha superior contínua). ✅ `aereo_fridge` +
   `filler` (até `aereo_top`).
2. **Aéreo FLUSH / handle-less.** Portas maiores (menos divisões), sem puxador saliente
   — abertura por gola/cava discreta (sombra fina recuada no rodapé da porta). Premium =
   menos linhas, módulos maiores. ✅ `gola` + `nmod = W/0.60`.
3. **Backsplash PROTAGONISTA.** Tampo "sobe" como backsplash contínuo (mesma pedra) até
   a base do aéreo — pedra é a superfície-herói, não azulejo. Tampo FINO (3 cm) reforça
   o look caro. ✅ `backsplash` (tampo subindo, thick 0.04) + `TAMPO_THK=0.03`.
4. **Nicho de assinatura (madeira).** 1 bay ABERTA no aéreo, fundo+prateleira em madeira,
   quebrando o off-white — ponto focal "respirável". ✅ 1 niche bay quando `nmod>=3`.
5. **Juntas planejadas (shadow gaps / reveals).** Reveal de 1.8–2.2 cm entre módulos
   (`M(0.018)`–`M(0.022)`), reveal escuro na divisão freezer/geladeira, valance grafite
   recuada sob o aéreo. A JUNTA intencional é o que grita "marcenaria sob medida". ✅
   presente em base (0.018), aéreo (0.022).
6. **Gaveteiro real.** 1º módulo da base = 3 gavetas com barra de puxar, não só portas
   — lê marcenaria funcional. ✅ `i==0 → 3 gavetas`.
7. **Cuba funda + gooseneck.** Bojo fundo (20 cm) escuro, borda flush no tampo, torneira
   gooseneck slim grafite. ✅ `pia` (bojo 0.20, gooseneck).
8. **Cooktop embutido + coifa slim integrada.** Cooktop preto fino quase flush no tampo;
   coifa = caixa SLIM off-white sob o aéreo (integra, não bloco preto solto) com grelha
   escura embaixo. ✅ `cooktop` + `coifa` (h<=0.20, off-white).
9. **Sóculo recuado (toe-kick) grafite.** Recuo 8–12 cm, grafite — "flutua" a base e
   esconde o pé. ✅ `TOE_KICK=0.12`, sóculo recuado 8 cm na geometria.
10. **LED quente sob o aéreo.** Fita 3000K lavando o backsplash — o que dá o "glow" de
    revista (só aparece de fato em V-Ray). ✅ `led` panel.

---

## 3. Proporções-alvo (medidas que o gate kitchen_ergonomics PINA)

Faixas ergonômicas que o premium respeita (board confirma; gate audita). Já TODAS PASS
no estado atual — esta tabela é o contrato pra não regredir.

| Métrica | Faixa-alvo (cm) | Valor atual (constante) | Leitura premium |
|---|---|---|---|
| Altura da bancada | 85–92 | 90 (`COUNTER_H`) | padrão; sink rim flush igual |
| Sóculo (toe-kick) | 10–15 | 12 (`TOE_KICK`) | recuo que "flutua" a base |
| Profundidade base | 55–60 | 60 (`COUNTER_DEPTH`) | bancada cheia |
| Profundidade aéreo | 30–35 | 33 (`AEREO_DEPTH`) | aéreo mais raso que base (regra premium) |
| Clearance bancada→aéreo | 50–60 | 60 (`AEREO_Z0 - COUNTER_H`) | respiro alto = arejado/caro |
| Clearance cooktop→coifa | 45–65 | ~46 (under-cabinet) | coifa slim integrada |
| Largura torre geladeira | 55–75 | 70 (`GEL_W`) | coluna ~60-70 |
| Respiro lateral geladeira | 2–6 | nicho−corpo (inset) | embute sem prensar |
| Módulo base (porta/gaveta) | 35–65 | `W/0.50` ≈ 50 | módulos maiores = menos linhas |
| Módulo aéreo | 35–65 | `W/0.60` ≈ 60 | portas MAIORES no aéreo (premium) |
| Filler | 15–18 | 16 | painel-gable que fecha o gap diagonal |

**Proporções de LINGUAGEM (além do gate), o que lê "caro" na silhueta:**
- **Tampo FINO** (3 cm) sobre base robusta — linha horizontal delgada = sofisticação.
  Tampo grosso (>4 cm) lê pesado/datado.
- **Aéreo mais raso que a base** (33 vs 60 cm) — escalonamento que abre o corredor
  estreito e deixa luz descer no backsplash.
- **Portas/módulos GRANDES** — menos divisões verticais = menos "linhas de caixa".
  Aéreo em ~60 cm, base em ~50 cm. Premium foge do modulado de 40 cm picotado.
- **Reveals 1.5–2.0 cm** consistentes — shadow gaps regulares dão ritmo de marcenaria.
- **Linha superior CONTÍNUA** — topo do aéreo = topo da torre da geladeira. O olho lê
  uma faixa horizontal única, não dentes.
- **1 ponto focal só** (o nicho de madeira). Premium compacto é DISCIPLINADO: pouca
  decoração na bancada (tábua + 1 vasinho), nada de bagunça.

---

## 4. Veredito de cobertura (gramática vs. construído hoje)

A cozinha r004 atual JÁ implementa **toda a gramática catalogada acima** — paleta em 6
camadas, 10 soluções recorrentes, 11 proporções dentro da faixa (gates PASS). O delta
entre o flat e a "foto de revista" é de **MATERIAL/LUZ (V-Ray)**, não de forma:

- **veio da pedra** no tampo/backsplash → mapa procedural V-Ray (não muda geometria);
- **reflexo do inox** na geladeira/cuba → BRDF metálico V-Ray;
- **glow do LED 3000K** lavando o backsplash → emissivo + GI no V-Ray.

Portanto, em FORMA, a gramática está consolidada e congelável. O próximo ROI é
**material/render**, não geometria. Onde a forma ainda pode subir 1 degrau (candidatos
de baixo risco, sem virar layout):
- **Espelhar reveal do tampo no backsplash** (mesma junta fina onde a pedra "dobra") —
  reforça a leitura de pedra contínua única.
- **Puxador/gola ainda mais discreto no aéreo** (já handle-less; verificar que a gola
  não some no flat sem virar puxador-barra).
- **Coerência do nicho** — garantir que o nicho de madeira cai num bay CENTRAL/visível
  (não na ponta atrás da torre), pra valer como ponto focal.

Esses são SUGESTÕES de spec; a aplicação é serial pelo orquestrador (este artefato NÃO
edita `kitchen_layout.py` nem `.skp`).

---

## 5. Fontes da gramática

- **REFERENCE_PACK do Felipe (2026-06-19)** — inferiores carvalho/freijó; superiores
  off-white quente/fendi; torre mesmo fendi; pedra clara com veio sutil + tampo fino;
  grafite só em sóculo/coifa/linhas; LED 3000K; gola/cava; nicho de madeira; portas
  maiores; shadow gaps 1–2 cm.
- **Ergonomia** — `references/design_rules/furniture_rule_cards.json` → `KITCHEN_COUNTER_BASIC`
  (bancada 0.90/0.60, aéreo 0.35@1.40, torre 0.65); `PANEL_THICKNESS_MDF` 0.018.
- **Gate de medidas** — `tools/kitchen_ergonomics.py` (`ERGO` dict, 12 faixas, todas PASS).
- **Geometria real** — `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`
  → r004 = 1.82×2.94 m, parede OESTE (anchor da pia, FIXA no PDF).
- **Estado construído** — `tools/kitchen_layout.py` (`_KC` paleta, `_kmod` geometria
  detalhada, `build_boxes` layout galley).
