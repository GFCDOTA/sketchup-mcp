# Batch Analysis 001 — pack de 17 referências do Felipe (dark + wood premium)

> 17 imagens curadas (Downloads.rar). Agrupadas por LINGUAGEM (não 17 análises soltas). Imagens
> NÃO commitadas (copyright) — ficam locais em `.claude/scratch/ref_unpack/`; aqui fica só a
> GRAMÁTICA extraída. Regra: referência=linguagem, PDF=posição, gates=verdade, Felipe=PASS.

## Veredito macro
**As 17 são unânimes na mesma direção: preto/grafite fosco + madeira natural quente + pedra com
veio + LED quente + handle-less + moody premium.** Isto não é "achar um tema" — é **CONFIRMAÇÃO
forte** de que o `BLACK_WOOD_GOLD` / `dark_walnut` é o caminho certo do Felipe (todo o curado dele
é essa língua). Sinal de alta confiança.

## Gramática recorrente (o que REPETE = restrição forte)
1. **Marcenaria preto/grafite fosco** — em 17/17.
2. **Madeira natural quente** (nogueira/freijó) como protagonista ou acento quente — 17/17.
3. **Handle-less** (gola/cava + reveal preto entre módulos) — quase todas.
4. **LED quente** (sob aéreo, em prateleira, dentro de cristaleira, em nicho) — quase todas.
5. **Pedra com veio** no backsplash/tampo — várias; cores: **verde** (ref 07), dark/grafite, gold.
6. **Cristaleira/vidro com LED + interior de madeira** (refs 04, 06, 10) — assinatura "wow" recorrente.
7. **Torre quente** (coluna de fornos/micro pretos embutidos) — ref 06 e outras.
8. **Nichos abertos iluminados** (com critério) — refs 07, 06.

## Mapa contra o que já temos
| elemento recorrente | já temos? | ação |
|---|---|---|
| preto fosco + madeira + LED | ✅ tema `black_wood_gold` / `dark_walnut` | CONFIRMA (alta confiança) |
| handle-less / shadow gap | ✅ card `shadow_gap_reveal` | confirma |
| cristaleira vidro + LED | ✅ card/token `reflecta_led_cabinet` | **referência forte — vale prototipar** |
| torre quente fornos | ✅ card/token `hot_tower` | confirma |
| LED sob aéreo/prateleira | ✅ `under_cabinet_led` | confirma |
| pedra veio **dourado/dark** | ✅ `stone_gold.png` | confirma |
| pedra veio **VERDE** (verde alpi/mármore verde) | ❌ NOVO | **adicionar variante de pedra** |

## What to COPY (linguagem)
A paleta inteira do `black_wood_gold` está validada pelo pack. Os elementos-assinatura a destacar:
**cristaleira de vidro com LED + interior de madeira** (1–2 módulos, não parede inteira) e **pedra
de veio mais presente** (verde OU dourado).

## What to ADAPT
- **Pedra:** o Felipe gosta de veio "mais forte" — testar uma variante **verde** (ref 07) além da
  dourada, com a ressalva de manutenção (mármore verde mancha; quartzito/porcelanato verde é mais seguro).
- **Cristaleira:** aplicar como **1–2 módulos de destaque** (respeita `reflecta_control_gate`), não a
  parede de vidro inteira das refs (06/10 são showroom).

## What to REJECT (POSIÇÃO é do PDF)
- **Ilha** (refs 02, 06, 13, 15) — a planta_74 é linear, sem ilha. NÃO copiar.
- **Layout L/U** e paredes das fotos — vêm do PDF, não da imagem.
- **Parede inteira de cristaleira** (06/10) — vira showroom + marca dedo + caro (Felipe já vetou "reflecta em tudo").

## 4 gates (pack)
| gate | veredito |
|---|---|
| theme_fit | **PASS** (a língua é compacto-compatível; só rejeitar ilha/parede de vidro) |
| ergonomics | n/a (sem cotas; geometria é do PDF) |
| maintenance | **WARN** (mármore verde mancha; reflecta marca dedo; pedra brilhante e cuba preta = cuidado) |
| buildability | **PASS** (tudo marcenaria padrão; cristaleira e torre quente executáveis) |

## Próximo experimento recomendado
O pack **endossa o `black_wood_gold` como a direção principal**. 2 enriquecimentos concretos pra
prototipar na planta_74 (skin/pele, geometria congelada):
1. **Variante de pedra VERDE** do black_wood_gold (gerar `stone_green.png` veio verde + um tema/skin).
2. **Cristaleira de vidro com LED + interior de madeira** como 1 módulo de destaque (token
   `reflecta_champagne_led_cabinet` já existe — falta o protótipo renderizado).
Felipe escolhe qual atacar primeiro.
