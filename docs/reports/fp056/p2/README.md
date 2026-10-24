# FP-056 P2 — região utilizável (contrato 1): infraestrutura, medida por cômodo e decisões (2026-10-24)

## O que entrou
- `tools/rooms/shared/placement_region.py`: `usable_placement_region(con, room_id)` devolve a laje do cômodo **menos** a
  massa de parede e de barreira. São as mesmas pegadas que o shell usa: paredes com as pontas estendidas e guarda-corpos com
  meia espessura. Não é recuo fixo. Pedaços descartados (lascas) vêm no relatório. Teste: nenhum cômodo tem área utilizável
  dentro de parede ou barreira.
- **Completude do programa** no gate de não regressão (`defect_baseline.regression(..., program, accepted_omissions)`):
  - um módulo que existia no apartamento original e sumiu reprova;
  - cômodo esvaziado nunca conta como "resolvido": os defeitos de peças que sumiram vão para `vanished_with_piece`;
  - omissão só passa com decisão registrada.

  Programa original por cômodo: `artifacts/review/fp056/p2/program_baseline.json`. `built_geometry.validate_room` agora
  devolve `modules`.

## Por que os planejadores ainda não usam a região (experimento medido, revertido)
Trocar o `cell` de `build_spatial_model` pela região utilizável em todos os cômodos de uma vez deu (gêmeo em caixas + gate
de circulação):
| Cômodo | Laje → utilizável | Efeito |
|---|---|---|
| SUÍTE 01 r000 | 15,90 → 14,83 m² | 3 defeitos resolvidos; **circulação passa a FAIL** |
| A.S. r001 | 15,41 → 14,15 m² | perde também **tanque e secadora** (circulação) |
| SALA r002 | 14,74 → 13,69 m² | sem mudança nos defeitos |
| SUÍTE 02 r003 | 7,98 → 7,33 m² | **NO_VALID_LAYOUT (cômodo vazio)**. O gate antigo contaria os 5 defeitos como "resolvidos", e esse furo foi fechado pela completude |
| COZINHA r004 | 5,29 → 4,88 m² | **build aborta** no gate da âncora da pia: a bancada sai 5,6 cm da parede oeste e invade a faixa da porta em 16 in² |
| BANHO 01 r005 | 3,20 → 2,77 m² | box e bancada resolvidos; **porta h_o002 passa a abrir 66°** |
| BANHO 02 r006 | 2,87 → 2,45 m² | box e bancada resolvidos; **porta h_o006 abre 2°** |
| LAVABO r007 | 1,85 → 1,55 m² | sem defeito novo |

Total: 22 defeitos sumiram, mas 5 deles por esvaziamento, além de 3 portas novas bloqueadas e circulação perdida. Além
disso, mudar `build_spatial_model` torna velho o fecho de **4 capacidades com prova L2** (`kitchen.layout.galley`,
`kitchen.cabinet.plain-fronts` ×2, `kitchen.cabinet.shaker-door`; R-18). Conclusão: **não** se troca globalmente. Cada
planejador adota a região quando a adaptação DELE produzir melhora estrita, isto é, sem defeito novo, sem perda de programa
não decidida e sem gate pior (FP-056 D-010).

## Decisões de projeto PENDENTES (Felipe) — registradas, não aplicadas
| ID | Cômodo | Conflito medido | Alternativas |
|---|---|---|---|
| K-1 | Cozinha | a galley (bancada 0,63 m) só cabe entre a parede oeste e a faixa da porta entrando 5,6 cm na parede; fora dela invade 16 in² da faixa | bancada mais rasa; outra faixa de porta; outro arranjo |
| AS-1 | A.S. | (P1) terraço social: churrasqueira 1,00 m × bancada gourmet; na região utilizável também tanque e secadora | priorizar quais peças; larguras menores |
| S2-1 | Suíte 02 | 7,33 m² utilizáveis: o programa atual não cabe (nenhum layout válido) | programa reduzido (sem escrivaninha/criado-mudo 2, ...) |
| S1-1 | Suíte 01 | a circulação reprova na região utilizável | reposicionar e reduzir, conferindo a decisão #381 (criado-mudo 1 in, sem cadeira) |
| B-1 | Banhos 01/02 | peças afastadas da parede invadem o giro da porta (66°, 2°) | posição/dimensão da louça; porta |

## Achado de integridade da evidência da FP-055 P4 (corrigido para a frente)
O `SHA256SUMS` de `artifacts/review/fp055/p4/` foi gerado sobre os bytes **capturados**, com CRLF (Ruby e Python no Windows).
O git normaliza para LF no commit (`core.autocrlf=true`). Conferido arquivo a arquivo:
- os originais em `runs/` batem com o `SHA256SUMS` byte a byte;
- o conteúdo deles é **idêntico** ao dos blobs commitados, a menos de CRLF → LF;
- as PNGs batem direto.

A evidência mergeada não foi reescrita. `artifacts/review/fp056/p2/fp055_p4_SHA256SUMS.git` traz o hash de cada blob
commitado, e `.gitattributes` passa a preservar os bytes de `artifacts/review/**/raw_evidence/**` (`-text`) para as
próximas capturas.

## Próximo
Independentes das decisões acima, seguem:
- contrato 2 (apoio físico) e contrato 3 (barreiras e porta) no validador e no gêmeo;
- adoção da região utilizável no LAVABO (sem efeito colateral medido) com prova;
- FP-055 P5 e P7.

## Correção da leitura da P1 (o relatório da P1 fica como está, é retrato datado)
A P1 registrou "5 de 5 defeitos da A.S. resolvidos". Com o gate de programa desta fase, a leitura correta é:
- **4 corrigidos por posição**: máquina de lavar, jardineira, armário e condensadora;
- **1 sumiu com a peça**: a bancada gourmet, omitida pela circulação junto com as banquetas;
- a perda de programa (`r001|PROGRAM|Bancada gourmet`, `r001|PROGRAM|Banqueta`) fica **reprovada** pelo gate até a decisão
  AS-1. Travado em `tests/test_fp056_p1_box_twin.py`.
