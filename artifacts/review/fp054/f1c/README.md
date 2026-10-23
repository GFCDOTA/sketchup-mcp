# FP-054 F1C — board de revisão: interfaces semânticas, fontes e evidência visual (planta_74, REPORT_ONLY)

> Para revisão visual externa. Findings **provisórios do modelo** (não defeitos de layout comprovados). Nada foi movido,
> corrigido nem promovido; nenhuma caixa nem `.skp` mudou (snapshot da planta `5426c008…`, 394 peças).

| Arquivo | Conteúdo |
|---|---|
| `functional_review_board.png` | os 4 cômodos + todos os resultados + legenda |
| `kitchen_overlay.png` | cozinha `r004` — face de trabalho da bancada (âncora hidráulica do PDF) |
| `bathroom_01_overlay.png` | Banho 01 `r005` — vaso, lavatório, entrada do box |
| `bathroom_02_overlay.png` | Banho 02 `r006` — vaso, lavatório, entrada do box |
| `lavatory_overlay.png` | lavabo `r007` — vaso e lavatório (o nome do arquivo segue o pedido; o cômodo é o lavabo) |

Reprodução:
`PT_TO_M=0.0259 python -m tools.validation.functional_clearance --report docs/reports/fp054/f1c --compare docs/reports/fp054/f1b/functional_clearance.json`
e `PT_TO_M=0.0259 python -m tools.validation.functional_clearance_board docs/reports/fp054/f1c/functional_clearance.json artifacts/review/fp054/f1c`.

Legenda: linha grossa colorida = interface (face de uso / face de trabalho / **entrada** do box); amarela = trecho usável;
seta = normal; tracejado hachurado = zona de uso (0,30 m); azul pontilhado = região alcançável na largura medida; X vermelho =
gargalo (onde a passagem rompe com +2 cm; "na entrada" = a própria porta do cômodo); estrela = portal; `[a/b/c]` = mínimo de
referência / alvo do projeto (`PENDING_FELIPE`) / preferido, em m.

## Resultado F1C (23 avaliações; 20 interfaces semânticas, 0 heurísticas)
INVALID 8 · VALID 5 · PREFERRED 7 · BLOCKED_MISSING_INPUT 0 · NOT_APPLICABLE 3. Modo `SOLVER` dá o mesmo resultado (nenhuma
interface inferida).

## F1B heurística × F1C semântica (20 resultados da F1B + 3 regras novas)
11 iguais, 9 divergências — todas explicadas:

| Cômodo / peça / regra | F1B → F1C | Por quê |
|---|---|---|
| Banho 01 · Box · entrada (frente) | INVALID 0,53 → **PREFERRED 1,68** | a F1B media um disco no MEIO do lado livre; a entrada real (vão da porta de correr) fica no canto oeste, livre até o fundo do cômodo; regra trocada (disco com citação NBR não conferida → profundidade na frente da entrada, fonte D conferida) |
| Banho 01 · Box · alcance | VALID 0,65 → VALID 0,63 | interface mudou de lugar (0,62 m) |
| Banho 01 · Vaso · frente | VALID 0,664 → 0,675 | mesma face; segmento do builder difere 1,3 cm do lado heurístico |
| Banho 02 · Box · entrada (frente) | INVALID 0,56 → **INVALID 0,00** | a frente do box que o builder escolheu (vidro + folha) está **encostada na parede oeste**: a entrada dá para a parede |
| Banho 02 · Box · alcance | INVALID 0,50 → **INVALID 0,00** | mesma causa: zona de uso inexistente |
| Lavabo · Vaso · frente | INVALID 0,044 → 0,032 | mesma face; segmento do builder difere 2,0 cm |
| Banho 01 · Box · largura do vão | — → **INVALID 0,33** | regra nova: vão livre da porta de correr = frente 1,02 − folha 0,61 = 0,41 m nominal, 0,33 m livres (ponta no revestimento) |
| Banho 02 · Box · largura do vão | — → **INVALID 0,00** | regra nova: entrada contra a parede |
| Lavabo · Box · largura do vão | — → N/A | lavabo sem box |

Mudanças só de proveniência (sem mudar veredito): alcance do lavatório e do box passam a `HEURISTIC` (não há fonte externa
para eles); box deixa de ser `TECHNICAL_REFERENCE` (a citação da NBR 9050 não foi conferida).

## Os 8 INVALID da F1C (provisórios — para revisão, não correção)
1. Banho 01 — largura do vão do box 0,33 m (porta de correr com folha maior que o fixo).
2. Banho 02 — entrada do box voltada para a parede (frente 0, vão 0, alcance 0): provável erro do builder na escolha do lado.
3. Banho 02 — frente do vaso 0,52 m.
4. Lavabo — frente da bancada 0,04 m e frente do vaso 0,03 m: vaso de frente para a bancada a ~4 cm; zona de uso do vaso
   inalcançável.

## O que NÃO é
Não é veredito visual (aguarda o Felipe), não é decisão de layout, não aprova alvos (`PENDING_FELIPE`), não libera a F2.
Limitação: o alcance usa a zona de 0,30 m junto à interface (`HEURISTIC`).
