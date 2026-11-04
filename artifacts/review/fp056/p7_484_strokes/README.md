# FP-056 #484 — o que é cada traço sem fonte `sb000`–`sb007` (2026-11-02)

Evidência para a decisão da Issue #484. Fecha a lacuna da P7 (`artifacts/review/fp056/p7/`): lá a alternativa (a) "declarar
com fonte e construir como massa" pedia ao Felipe para dizer o que é cada contorno, mas `stroke_outlines.png` não dava ID aos
retângulos fechados e não mostrava o PDF. Esta pasta dá um ID a cada traço e a cada contorno fechado, mede cada um e põe o PDF
original por baixo. **Nada foi aplicado** ao consensus, ao shell, ao gerador ou ao `.skp`. Aparência: `PENDING_HUMAN`.

- Commit sob prova: `develop@b556ca9` (merge da PR #577). Sem SketchUp (só leitura do consensus e do PDF; nenhum PID aberto).
- Consensus `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json` e PDF `projects/planta_74/source/planta_74.pdf`:
  SHA-256 conferido antes e depois pelo script (valores em `strokes.json`), sem alteração.
- PDF lido com `pypdfium2` 4.30.0 (já está no `uv.lock`); laje/`cell` com `compute_room_floors` (o mesmo do shell e dos planejadores).

## Arquivos
| Arquivo | O que é |
|---|---|
| `strokes_overview.png` | planta inteira com o PDF por baixo e os 8 traços por cima, **na orientação do PDF** |
| `strokes_board.png` | um recorte do PDF por traço (8 painéis), com o traço, os contornos fechados `Cnn` e a laje perdida |
| `contours_zoom.png` | zoom em cada contorno fechado `C01`–`C09` sobre o PDF, com a classificação **proposta** |
| `strokes.json` | medidas por traço e por contorno + objeto vetorial do PDF que originou cada traço + proposta do agente |
| `probe_strokes.py` | o script que gera tudo acima |

## Achados medidos (fato)
1. **A figura da P7 está espelhada na vertical.** O consensus usa pt nativos do PDF (y para cima); `stroke_outlines.png`
   desenhou com o eixo y invertido, então A.S. aparece em cima e Cozinha embaixo, o contrário do PDF. As figuras desta pasta
   usam a orientação do PDF.
2. **Cada traço é um caminho vetorial do PDF com contorno e sem preenchimento** (fill mode 0, traço preto de largura mínima). Os traços
   vêm em **pares** com o mesmo bbox (±0,8 pt): `sb000+sb001`, `sb002+sb003`, `sb005+sb006`; `sb004` e `sb007` não têm par.
   Em cada par, um anel (`sb001`, `sb003`, `sb006`) fecha **0,000 m² fora das paredes do consensus**: contorna só a massa de
   parede que o consensus já tem. O outro (`sb000`, `sb002`, `sb005`, `sb007`) contorna a mesma parede **e** fecha os
   retângulos `C01`–`C09`.
3. **9 contornos fechados** (`C01`–`C09`), todos colados na face de uma parede do consensus e todos desenhados no PDF com
   **hachura diagonal na borda e um X no meio** (contagem de segmentos inclinados em `strokes.json` → `pdf_inside`). Na legenda
   do PDF, a hachura diagonal é "DRYWALL OU PLACA CIMENTÍCIA"; a moldura cinza (164) do `C05` é "PAREDE NÃO ESTRUTURAL". O X
   não está na legenda.
4. **De onde vem a laje perdida (6,632 m² ao todo, igual à #484):** só **2,113 m²** estão dentro dos 9 contornos fechados;
   **4,519 m²** são a faixa que o shell cria ao engrossar um traço que está **em cima da face da parede**: meia espessura
   (2,7 pt ≈ 7 cm) para dentro do cômodo ao longo de todo o contorno, mais o recuo da laje.
5. `sb004` é a linha externa do peitoril H=1,10M do terraço (já declarado com fonte como `h_sb000`); efeito na laje 0,016 m².
6. `C04` (A.S., x 1,41–1,70 m, y 11,94–12,64 m) fica ao lado do símbolo da churrasqueira no PDF. A churrasqueira do planejador
   (#488, x 3,32–3,94 m) está a ~1,6 m dele: este achado não sustenta o argumento "encostada na prumada da coifa" da #484.

## Contornos fechados (ID, medida, proposta)
Coordenadas em m = pt × 0,0259 (origem do PDF, y para cima). "Laje" = laje/`cell` que falta dentro do contorno.

| ID | Cômodo | Traços | x (m) | y (m) | Dim. (m) | Laje (m²) | Paredes coladas | Proposta do agente (não é fato) |
|---|---|---|---|---|---|---|---|---|
| C01 | Lavabo | sb000(+sb001) | 8,31–8,57 | 16,33–17,55 | 0,26 × 1,22 | 0,314 | m009 m010 m016 | shaft/prumada (média) |
| C02 | Banho 01 | sb000(+sb001) | 13,82–14,20 | 13,52–14,43 | 0,38 × 0,91 | 0,342 | m005 m019 | shaft/prumada (média) |
| C03 | A.S. | sb002(+sb003) | 1,41–1,75 | 14,05–14,96 | 0,33 × 0,91 | 0,303 | m006 m012 | shaft/prumada (média) |
| C04 | A.S./terraço | sb002(+sb003) | 1,41–1,70 | 11,94–12,64 | 0,28 × 0,70 | 0,199 | m012 | shaft/prumada (média) |
| C05 | A.S./terraço | sb002(+sb003) | 1,41–2,14 | 10,55–11,27 | 0,72 × 0,72 | 0,524 | m001 m012 | shaft/prumada (média) |
| C06 | A.S. (junto ao terraço técnico) | sb005(+sb006) | 5,72–6,00 | 12,95–13,18 | 0,28 × 0,22 | 0,062 | m004 m014 | desconhecido (baixa) |
| C07 | Suíte 02 | sb005(+sb006) | 6,14–6,40 | 11,91–12,07 | 0,25 × 0,16 | 0,042 | m002 m014 | desconhecido (baixa) |
| C08 | Suíte 01 | sb007 | 10,06–10,23 | 13,52–13,68 | 0,16 × 0,16 | 0,027 | m005 m017 | desconhecido (baixa) |
| C09 | Banho 02 | sb007 | 9,59–9,92 | 12,61–13,56 | 0,33 × 0,95 | 0,299 | m003 m005 m017 | shaft/prumada (média) |

Motivo da proposta "shaft/prumada": retângulo fechado por hachura de drywall/placa cimentícia com X interno, colado na parede e,
em 5 dos 9 casos (C01–C04, C09), numa área molhada ou ao lado de churrasqueira/tanque. Essa é a convenção usual de shaft em planta de vendas, mas
o PDF não escreve "shaft" nem "prumada". `C06`–`C08` têm o mesmo desenho, mas são pequenos demais (≤ 0,28 m) para afirmar;
pilar é improvável (as notas do PDF dizem que o sistema é alvenaria estrutural), mas não fica descartado.

## Por traço
| Traço | Onde | Dim. bbox (m) | Comprimento (m) | Laje devolvida se o par sair (m²) | Proposta do agente |
|---|---|---|---|---|---|
| sb000 | bloco Lavabo/Suíte 01/Banho 01 (+ parede norte da Sala) | 10,02 × 4,34 | 34,1 | Suíte 01 0,691; Sala 0,386; Banho 01 0,624; Lavabo 0,721 | contorno de alvenaria + C01, C02 |
| sb001 | idem (par) | 9,99 × 4,31 | 38,7 | (idem, par) | contorno de alvenaria (0 m² fora da parede) |
| sb002 | bloco oeste Cozinha/A.S. (face interna) | 2,17 × 7,76 | 15,5 | A.S. 1,565; Sala 0,223; Cozinha 0,257 | contorno de alvenaria + C03, C04, C05 |
| sb003 | idem (par) | 2,15 × 7,74 | 23,2 | (idem, par) | contorno de alvenaria (0 m² fora da parede) |
| sb004 | borda externa do terraço | 5,55 × 1,41 | 7,0 | A.S. 0,016 | linha externa do peitoril H=1,10 (= `h_sb000`) |
| sb005 | bloco Suíte 02 oeste/norte | 2,20 × 3,54 | 13,1 | A.S. 0,393; Sala 0,317; Suíte 02 0,475 | contorno de alvenaria + C06, C07 |
| sb006 | idem (par) | 2,15 × 3,51 | 12,9 | (idem, par) | contorno de alvenaria (0 m² fora da parede) |
| sb007 | bloco Banho 02 leste | 2,00 × 2,90 | 10,8 | Suíte 01 0,303; Banho 02 0,637; Sala 0,016; Suíte 02 0,016 | contorno de alvenaria + C08, C09 |

## O que isso muda na leitura das alternativas da #484 (sem decidir)
- Construir os 8 traços "como massa" (alternativa (a) como estava escrita) também construiria uma casca de ~7 cm por dentro de
  todas as paredes que eles contornam: são 4,5 m² dos 6,6 m² perdidos, sem nada correspondente no PDF além da própria parede.
- O que o PDF desenha de fato além das paredes são os 9 retângulos `C01`–`C09` (2,1 m²). Uma variante de (a) seria declarar
  só esses retângulos com fonte e deixar de usar os traços de contorno no envelope. **Não foi medida com os gates** (pré-voo,
  gêmeo, F2): ela muda o `cell` de todos os cômodos, como a (b). Isso é para uma próxima rodada, se o Felipe quiser.

## O que NÃO é
- Não é decisão nem aplicação: a classificação é **proposta do agente** (`proposed_by` em `strokes.json`) para o Felipe
  confirmar ou corrigir, contorno a contorno.
- Não é L2: nada foi aberto no SketchUp. Não muda `fixtures/`, o PDF, o shell nem o `.skp`.
- Não refaz as medidas de alternativas da P7 (390/376 caixas, defeitos, pré-voo): continuam valendo como retrato daquela data.

## Reprodução
```bash
python -m uv sync --locked --extra dev
PT_TO_M=0.0259 PYTHONPATH=. PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe artifacts/review/fp056/p7_484_strokes/probe_strokes.py artifacts/review/fp056/p7_484_strokes
```
Sem argumento, a saída vai para `runs/fp056/p7_484_strokes/`.
