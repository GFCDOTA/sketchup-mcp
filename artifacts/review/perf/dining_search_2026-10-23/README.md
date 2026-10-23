# Busca da mesa de jantar da sala — antes × depois (2026-10-23)

**Pedido do Felipe:** "testa a busca da sala com poda do gate de circulação, mas me mostre antes/depois do layout para eu aprovar."

**Diagnóstico (gate real em toda a grade):** 28 posições candidatas; 2 passam no gate mas o tampo invade o arco da porta
`h_o000`; o resto reprova quase sempre por **corredor** (83 de 95 chamadas). Por isso a poda exata pelas checagens de
cadeira economizaria só ~10% e foi descartada. O custo estava no **refinamento** (deslize de 0,5″ em anéis ao redor das
duas âncoras): ele começava pela âncora (185, 662), que já estava no limite do corredor (0,81 m para 0,80 m), e
nenhum deslize ao redor dela passa — 58 chamadas perdidas antes de ir à âncora (185, 668), com 8 cm de folga.

**Mudança (estratégia):** refinar primeiro ao redor da âncora com **maior folga de corredor** (`corridor_slack_m` do resultado
do próprio gate; empate = ordem da grade). Deslizar a mesa para sair do arco consome corredor; quem já está no limite não
sobrevive ao deslize.

| | Antes | Depois |
|---|---|---|
| chamadas do gate na busca | 95 (28 grade + 67 refino) | **37** (28 + 9) |
| posição escolhida (centro do tampo, pol.) | (190,5; 668,5) | **(190,5; 668,5)** |
| snapshot da sala / apartamento | `03140fb8…` / `c2a57f92…` | **idênticos** |
| mobiliar o apartamento (fria / quente) | 2,06 s / 1,50 s | **1,20 s / 0,95 s** |

`sala_antes_depois.png`: planta da sala antes e depois (idênticas) e zoom do refinamento — círculos vermelhos = 67 posições
testadas antes; X azul = 9 testadas depois; estrela = posição escolhida (a mesma). Na planta_74 a nova ordem cai no mesmo
lugar; em outra planta ela **pode** escolher outra posição válida (passa no gate e não toca o arco) — por isso o veredito
é do Felipe. Trava: `tests/test_layout_search_pruning.py` (≤ 40 chamadas, PASS no gate, otimizador v3).
