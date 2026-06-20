# SOFA — DesignIntentSpec da CLASSE procedural

> FASE 1 do programa "arquiteto de classe" (2026-06-12). Este documento define a
> TEORIA da classe sofá; a versão executável vive em `tools/sofa_class.py`
> (faixas, relações, derivação e gate de proporção). Regra do programa: melhoria
> sobe pra spec/constraints/gerador/gate — nunca remendo de exemplar.
> Os 4 ciclos GPT do exemplar (WARN→PASS limpo, verdicts SOFA-STRAIGHT-3SEAT_*)
> são a BASE EMPÍRICA; a tabela ergonômica abaixo é a BASE DE REFERÊNCIA real.

## Missão da classe

Gerar QUALQUER sofá residencial plausível (2–4 lugares, formal→lounge, plinto ou
pés, com/sem chaise) a partir de poucos parâmetros de intenção, com TODAS as
proporções garantidas por constraints — de modo que nenhuma combinação válida de
parâmetros produza aberração, e variações leiam como a MESMA família.

## Partes (anatomia)

| parte | obrigatória | notas |
|---|---|---|
| base/plinto | sim | sustenta a massa; recuo frontal tira o monolito |
| assento (N almofadas ou bench) | sim | N = seats; vinco 4–20mm entre almofadas |
| encosto (N almofadas) | sim | rake obrigatório (>=8°); começa ~3cm abaixo do topo do assento |
| braços (2) | sim* | *armless é variante futura explícita, não default |
| pés OU plinto-ao-chão | sim | escolha binária de estilo (meio-termo = anti-pattern) |
| chaise | opcional | left/right; herda alturas do corpo |

## Parâmetros de classe (faixas duras — fora disso é ERRO de classe)

Dimensões ligadas ao CORPO HUMANO — **fixas entre 2/3/4 lugares**:

| parâmetro | mín | típico | máx | unidade |
|---|---|---|---|---|
| seat_height | 0.38 | 0.43 | 0.48 | m |
| seat_depth (útil) | 0.50 | 0.56 | 0.68 | m |
| depth (total) | 0.80 | 0.92 | 1.05 | m |
| height (total) | 0.68 | 0.82 | 0.98 | m |
| arm_height − seat_height | 0.12 | 0.18 | 0.27 | m |
| arm_width (cada) | 0.10 | 0.18 | 0.42 | m |
| backrest_rake | 8 | 14 | 22 | graus |
| cushion_thickness | 0.10 | 0.16 | 0.24 | m |
| foot_height (pés expostos) | 0.06 | 0.12 | 0.22 | m |
| foot_height (plinto) | 0.00 | 0.02 | 0.04 | m |
| cushion_gap | 0.004 | 0.012 | 0.020 | m |
| largura útil POR assento | 0.52 | 0.60 | 0.75 | m |

**Escala**: só a LARGURA cresce com N. `width = N·per_seat + 2·arm_width`.
Profundidade/alturas NÃO escalam (erro clássico = inflar em cubo).

## Relações (constraints relacionais — o coração da classe)

1. `height/seat_height ∈ [1.7, 2.1]` — encosto sobe acima do assento quase o que
   o assento sobe do chão.
2. `(height − seat_height) ∈ [0.32, 0.55]` — suporte de costas efetivo.
3. `(arm_height − seat_height) / (height − seat_height) ∈ [0.30, 0.60]` — braço
   ABAIXO da metade do encosto; braço ≈ topo do encosto = silhueta caixa.
4. `2·arm_width / width ≤ 0.35` — braços não engolem o assento.
5. `seat_depth / seat_height ∈ [1.10, 1.55]` — assento mais fundo que alto.
6. `seat_depth + back_thickness ≤ depth` — coerência de profundidade.
7. `cushion_thickness < seat_height − foot_height` — almofada cabe na base.
8. `width/height`: formal 2.0–2.5, lounge 2.6–3.2 (proporção de silhueta).
9. `foot_height ∉ (0.04, 0.06)` — meio-termo pé-atarracado = "sofá quebrado".

## Arquétipos (presets de intenção — eixo formal↔lounge)

| | formal | standard | lounge |
|---|---|---|---|
| seat_height | 0.45 | 0.43 | 0.40 |
| seat_depth | 0.52 | 0.56 | 0.62 |
| height | 0.90 | 0.84 | 0.74 |
| backrest_rake | 10° | 14° | 18° |
| arm acima do assento | 0.24 | 0.18 | 0.14 |
| cushion_thickness | 0.13 | 0.16 | 0.20 |
| per_seat | 0.56 | 0.60 | 0.66 |

## Anti-regressão (PASS dos cycles 1–4 — nunca violar nos defaults)

`backrest_rake ≥ 8°` · `cushion_bevel ≥ 0.03` · `arm_width ≤ 0.22 no default` ·
`cushion_thickness ≥ 0.16 no standard` · `back_thickness ≥ 0.19` · partes
obrigatórias {base, seat_cushion, back_cushion, arm, foot} · vinco visível.

## Regras de linguagem (cycle 002 — veredito SOFA-CLASS_cycle001)

1. **Compensação de massa do braço (anti-bunker):** `arm_width ≥ 0.22` EXIGE
   `arm_relief ≥ 0.04` — o braço "flutua" sobre sapata recuada (luz por baixo).
   Constraint executável no gate; o derive aplica automático no chunky.
2. **Gramática de chaise integrada:** a chaise é EXTENSÃO do seat deck, nunca
   módulo colado — (a) braço do lado da chaise acompanha SÓ o corpo (frente da
   chaise aberta, sem muralha); (b) o vinco da chaise ALINHA com `seat_front`
   do corpo (deck contínuo em L); (c) a base da chaise herda o `base_recess`.
3. **Arquétipo muda LINGUAGEM, não só medida:** formal = `arm_cap` (tampo proud)
   + pés mais altos (0.14) + chanfro crisp (0.03); lounge = `seat_overhang`
   (almofada projeta sobre a base = sombra horizontal) + plinto mais recuado
   (0.10) + chanfro macio (0.05) + pés baixos (0.10); standard = neutro.

## Heurísticas de boa forma

- Pés visíveis (≥0.10) = leve/flutuante; plinto ao chão = ancorado. Escolher UM.
- Braço, assento e encosto compartilham linguagem de chanfro (bevel coerente).
- Almofada de assento ≥ almofada de encosto em espessura (leitura lounge).
- Vinco entre almofadas é JUNTA (4–20mm), nunca vão.

## Anti-patterns (o gate de classe reprova)

bloco-caixa (braço ≈ topo do encosto + sem bevel + plinto duro) · banco-de-igreja
(rake≈0 + assento raso + almofada fina) · marshmallow (almofada >0.24 + braços
>20% da largura cada) · perna-de-palito (vão >0.20 sob massa pesada) · dentes
faltando (gap >0.03) · gaveta (depth > largura por assento) · cubo-gigante
(escalar profundidade/altura junto com largura).

## Fora do escopo DESTA classe (variantes futuras explícitas)

armless / modular seccional / reclinável / high-back (>1.0m) / tufted
(primitiva existe no worktree sofa-skill — absorver quando a fase de detalhe abrir).
