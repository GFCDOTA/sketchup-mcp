# FP-056 R3 — alternativas restantes medidas (cozinha, tapete do Banho 01, papeleira do Banho 02) — 2026-11-02

Evidência para a #502 (critério 1) e a decisão #495. Complementa, sem reescrever, `artifacts/review/fp056/p7/README.md`
(que ainda lista estes pares como "não verificado").

- **Commit sob prova:** `b556ca9f` (`origin/develop`); nenhum código de produção alterado.
- **O que é:** cada alternativa aplicada **em memória** às caixas do `collect_boxes` da planta_74 e medida com o gêmeo em caixas
  (`box_geometry.validate_boxes` × baseline FP-055 P4, `defect_baseline.regression`) e o pré-voo inteiro
  (`layout_preflight.preflight` com o gêmeo). Nível **L1**.
- **O que NÃO é:** nada foi aplicado ao gerador, ao consensus, às fixtures nem a `.skp`; sem SketchUp; sem veredito visual
  (aparência `PENDING_HUMAN`). Não escolhe alternativa: a decisão é da #495.
- **Reprodução:** `PT_TO_M=0.0259 PYTHONPATH=. python artifacts/review/fp056/p7_r3_remaining/measure_r3_remaining.py
  artifacts/review/fp056/p7_r3_remaining/r3_remaining_alternatives.json` (resultado completo nesse JSON).

## Cozinha — backsplash × vidro do cooktop (4,6 cm) e × cuba (4,6 cm)
| Alternativa | Par resolvido | Defeito novo/pior | Pré-voo | Observação |
|---|---|---|---|---|
| (a) deslocar cooktop + cuba 4,6 cm para fora da parede | ambos | 0 | PASS | a cuba vai de 1,2 para ~3,0 pol da parede oeste: continua dentro de `TOUCH_TOL_IN = 6.0` (`tools/rooms/kitchen/anchor_rules.py:12`), âncora hidráulica preservada |
| (b) backsplash começa no topo do vidro/borda da cuba (z0 90,5 cm) | **não** | 0 | PASS | sobra 1,4 cm (anéis/bocas acima do vidro) e 0,1 cm (torneira) |
| (c) recortar vidro do cooktop e cuba pela face do backsplash | ambos | 0 | PASS | muda a dimensão das peças (cooktop/cuba 4,6 cm mais rasos), não só a posição |

**Custo L2 / R-18 (todas as alternativas):** as caixas da cozinha nascem em `tools.rooms.kitchen.layout.build_boxes`, símbolo
provado de `kitchen.layout.galley` (`L2_PASS`, evidência `artifacts/review/l2_fp042_20261019/README.md`, 76 peças). Aplicar
qualquer uma muda o digest: revogar `kitchen.layout.galley` no mesmo commit, refazer o L2 no SketchUp 26.0.429 num commit limpo
e restaurar com os digests novos (skill `capability-l2-proof`).

## Banho 01 — tapete × vaso (16,4 cm)
| Alternativa | Resolvido | Defeito novo/pior | Pré-voo | Observação |
|---|---|---|---|---|
| (a) encolher o tapete até a borda do vaso | sim | 0 | PASS | 0,400 → 0,318 m² (perde 20%) |
| (b) tirar o tapete | sim | 0 | PASS | o Banho 01 fica sem tapete |
Deslocar não resolve (verificação anterior: nenhum deslocamento até 40 cm, comentário de 2026-10-24 na #502).

## Banho 02 — papeleira × gabinete (9,4 cm)
| Alternativa | Resolvido | Defeito novo/pior | Pré-voo | Observação |
|---|---|---|---|---|
| (a) papeleira acima do tampo (z0 105,7 cm) | sim | **piora** `Enxoval+Espelho` | **FAIL** | inviável |
| (b) deslocar **60 cm ao longo da parede** (menor passo de 5 cm que resolve) | sim | 0 | PASS | continua na parede `m017`, sem vão sobreposto; fica ~68 cm da borda do vaso — alcance a partir do vaso **não medido** (sem limiar com fonte) |
| (c) tirar a papeleira | sim | 0 | PASS | o Banho 02 fica sem papeleira |
Deslocamento perpendicular à parede foi descartado de propósito: a peça sairia da parede e ficaria flutuando, e nenhum gate
atual vê isso.

## Resumo para a #495
Com a cama 3,1 cm (suítes, já medida em `p7/`), **todos** os 9 pares de R3 têm pelo menos uma alternativa que resolve sem defeito
novo/pior e com pré-voo PASS no gêmeo. Escolhas pendentes do proprietário: cozinha (a) ou (c) — ambas com custo L2/R-18;
Banho 01 tapete (a) ou (b); Banho 02 papeleira (b) ou (c).

## Como validar olhando (pranchas)
`board_r004.png` (cozinha), `board_r005.png` (Banho 01) e `board_r006.png` (Banho 02), geradas por `render_r3_boards.py` com as
mesmas mutações e caixas da medição. Em cada prancha: planta vista de cima com o PDF por baixo, uma coluna por alternativa,
as duas peças do par em azul/laranja e a **sobreposição em planta em vermelho**. Coluna sem vermelho = par resolvido em planta;
alternativa que só muda a altura vem marcada (o vermelho em planta continua, a separação é vertical). Gêmeo em caixas (L1),
nada aplicado; aparência `PENDING_HUMAN`.
