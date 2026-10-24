# FP-056 — alternativas das decisões verificadas pelo gerador e pelo gêmeo (2026-10-25)

Evidência para as Issues de decisão (#484, #486, #442, #446). **Nada foi aplicado ao gerador, ao consensus ou ao `.skp`**: cada
alternativa foi medida em memória com os mesmos gates do CI (pré-voo, gêmeo em caixas contra o baseline FP-055 P4, solver F2).
Gêmeo em caixas = L1; a prova no SketchUp real de qualquer alternativa escolhida é refeita depois (P6). Aparência: `PENDING_HUMAN`.

## #484 — traços sem fonte `sb000`–`sb007` (`stroke_alternatives.json`, `stroke_outlines.png`)
| Alternativa | Medido |
|---|---|
| (c) manter (atual) | 390 caixas; 29 defeitos físicos do baseline; pré-voo PASS; A.S. sem bancada gourmet/banqueta |
| (b) ignorar os traços sem fonte | laje +0,2 a +2,0 m² por cômodo; **376 caixas** (−14); Banho 02 perde o Box e ganha uma Ducha; **18 defeitos novos e 10 piores** no gêmeo; **pré-voo FAIL em 5 cômodos** (circulação da Suíte 01; colisão em A.S., Sala, Banho 02, Lavabo); banhos continuam INFEASIBLE no F2 |
| (a) declarar com fonte e construir como massa | por construção o `cell` e o layout **não mudam** (os planejadores já os evitam); o shell passa a construir 8 massas (aparência) e `fixtures/planta_74` muda: exige confirmação do que cada contorno é |
Leitura: a alternativa (b) coloca mobília onde há contorno de alvenaria/prumada do PDF; (a) é a única que remove a incoerência
(laje recortada por algo que não é construído) sem mover o programa.

## #486 — porta × tapete (R5) com o gêmeo (leaf = faixa de Z da folha no modelo)
| Alternativa | h_o003 (Suíte 01) | h_o004 (Suíte 02) | Efeito |
|---|---|---|---|
| atual | 49° | 16° | — |
| (a) folga inferior da folha 1,5 cm | 49° | 16° | insuficiente (tapete de 2,0 cm) |
| (a) folga inferior ≥ 2,05 cm | **90°** | **90°** | 0 defeito novo; muda a geometria de todas as folhas (valor da folga: do Felipe) |
| (b) recortar o tapete pelo giro **real** da folha | **90°** | **90°** | 0 defeito novo; perde 0,052 m² (0,7%) e 0,256 m² (3,7%) de tapete |
Achado técnico: o polígono de giro do pré-voo (`door_swings_pt`) é menor que a varredura real da folha (0,398 × 0,427 m²) e o pré-voo
trata topo ≤ 2 cm como "caminhável": ele não vê esse conflito (Issue técnica aberta).

## #442 — AS-1 (A.S.) com o próprio planejador
| Alternativa | Medido |
|---|---|
| atual (churrasqueira 1,00 m) | bancada gourmet, cuba, mesa externa e banquetas omitidas; 390 caixas |
| churrasqueira 0,85 m (ou 0,70 se não couber) | bancada gourmet, cuba e banquetas voltam; mesa externa e secadora seguem omitidas; **pré-voo PASS**; 0 defeito novo/pior; programa completo no baseline; 393 caixas |
| churrasqueira só 0,70 ou 0,60 m | **não** devolve a bancada (primeiro encaixe do planejador) |
A verificação achou um defeito do planejador (a Jardineira caía na mureta com a variante); corrigido na PR #499 sem mudar o layout atual.

## #446 — R6 (banhos/lavabo) com o solver F2
No grau de liberdade declarado, `r005`, `r006` e `r007` seguem **INFEASIBLE** com e sem os traços sem fonte (vão do box, alcance do
chuveiro/lavatório, frente do vaso). A decisão não depende de #484. As alternativas (vão do box, louça, parede) ainda **não** foram
verificadas pelo solver: Issue técnica aberta antes de pedir a decisão.

## #495 — R3 (interpenetrações) com o pré-voo e o gêmeo
| Alternativa | Medido |
|---|---|
| deslocar a **cama 3,1 cm** para longe do painel (Suítes 01 e 02) | `Cama+Painel cabeceira` some nas duas suítes; pré-voo PASS; 0 defeito novo/pior. Move 3,1 cm um móvel da Suíte 01 aprovada (#381): precisa do OK do Felipe |
| banhos (papeleira × gabinete 8,9/9,4 cm; gancho × espelho 3,1 cm; tapete × vaso 16,4 cm) e cozinha (backsplash × vidro do cooktop/cuba 4,6 cm) | **ainda não verificado** (a cozinha tem prova L2: R-18) — Issue técnica aberta |
