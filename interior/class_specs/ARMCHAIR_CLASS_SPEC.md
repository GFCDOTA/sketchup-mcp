# POLTRONA (armchair) — DesignIntentSpec da CLASSE procedural

> Cycle 001 (2026-06-12) — 2a classe do programa arquiteto-de-classe, replicando o
> template do sofá (PASS em 3 ciclos). Executável: `tools/armchair_class.py`.
> Geometria: REUSA `sofa_builder.build_sofa(seats=1)` — herda a gramática congelada
> do sofá (sapata/cap/taper, rake, bevel, overhang, recess). A classe é a TEORIA.

## Missão

Gerar qualquer poltrona de estar residencial plausível (club → standard → lounge)
por derivação, com a identidade que a separa de "sofá de 1 lugar".

## O que NÃO é sofá de 1 lugar (o DNA da classe)

1. **Braço presente:** `arm_span_ratio = 2·arm/width ∈ [0.22, 0.50]` (sofá: ~0.12–0.25).
   Braço fino de sofá numa peça solo = "1 lugar magro".
2. **Footprint quase-quadrado:** `width/depth ∈ [0.80, 1.30]` (sofá: 2.5:1+).
3. **Encosto sobe claramente acima do braço:** `height − arm_height ≥ 0.16` —
   senão os 3 planos colapsam em bloco.
4. **Teto de largura 1.05m** — acima é poltrona-e-meia (classe futura, não knob).
   Consequência matemática: `arm_width ≤ 0.26` (span≤0.50 com W≤1.05 não fecha
   acima disso — tensão real da teoria, resolvida no cycle 001).

## Faixas duras (m/graus)

seat_height 0.36–0.47 · seat_depth útil 0.48–0.60 · depth total 0.72–1.05 ·
height total 0.72–1.18 · arm_width 0.10–0.26 · rake 5–28° · almofada 0.10–0.22 ·
seat_width útil 0.45–0.65 · width 0.68–1.05 · pés 0.10–0.22 OU saia/plinto 0–0.08
(faixa própria, mais larga que a do sofá — club de saia é canônico).

## Relações

braço apoia antebraço: `arm−seat ∈ [0.14, 0.30]` · costas: `height−seat ∈ [0.38, 0.80]`
· coerência de profundidade · **recline pede profundidade**: cada ~5° de rake acima
de 12 soma ~0.05m de depth (lounge reclinada rasa joga o usuário pra fora).

## Arquétipos

| | club | standard | lounge |
|---|---|---|---|
| leitura | bloco aconchegante controlado | equilibrada, pernas à vista | recostar: baixa, funda, encosto alto |
| braço | 0.26 gordo + sapata (relief) | 0.18 + cap proud | 0.13 fino |
| rake | 9° | 13° | 22° |
| encosto acima assento | 0.46 | 0.53 | 0.66 |
| base default | plinth/saia | legs 0.14 | legs 0.16 + overhang |

## Anti-patterns (sabotagens provadas no gate)

braço de sofá (fino) · fresta (braços engolem) · footprint de mini-sofá ·
bloco (encosto na altura do braço) · lounge rasa reclinada · banqueta alta ·
pernas-palito sob corpo maciço de club (warning de linguagem).

## Lição de teoria do cycle 001

`seat_util/width` e `arm_span_ratio` são a MESMA régua (soma 1) — duas constraints
redundantes com números diferentes = gate inconsistente. Uma régua por eixo.
