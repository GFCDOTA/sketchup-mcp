# FP-054-F1B — Folga funcional e alcance por peça (extensão da F1)

> Extensão formal da `FP-054-F1_geometry_correctness.md` (não é FP nova). Fecha a lacuna da F1: acesso funcional às peças,
> alcance a partir do portal (inclusive cômodo de portal único) e folga funcional. Responde "o que é válido?"; **não** move peça,
> não ranqueia, não escolhe layout, não implementa otimizador — isso é a F2.

## Já entregue na F1 (não reimplementado)
Circulação fail-closed (#384), papéis de móvel (#385), pré-voo de layout (#386, + parede/arco em #389), testes de propriedade
(#387), arco de porta para cadeiras (#392), Suíte 01 (#389).

## Arquitetura
```
política/conhecimento  core/functional_constraints.py  (THRESHOLDS com proveniência, 3 níveis, OBJECT_TYPES + contrato de face)
definição              FunctionalConstraint (reference_minimum <= project_target <= preferred)
medição                tools/validation/functional_clearance.py (face de uso, folga na face, alcance portal -> zona de uso)
avaliação/veredito     FunctionalEvaluation: INVALID | VALID_BELOW_TARGET | VALID | PREFERRED | BLOCKED_MISSING_INPUT | NOT_APPLICABLE
```
Proveniência: `NORMATIVE | TECHNICAL_REFERENCE | PROJECT_POLICY | COMFORT_GUIDE | HEURISTIC`. Nenhum valor é `NORMATIVE`
(fonte primária não conferida). Alvos de projeto propostos em 2026-10-23 estão `PENDING_FELIPE`.

## Regras (planta_74, REPORT_ONLY)
| Peça | Folga na face (mín / alvo / pref) | Alcance do portal (mín / alvo / pref) | Face de uso (contrato) |
|---|---|---|---|
| vaso | 0,60 / 0,60 / 0,80 m | 0,60 / 0,60 / 0,80 m | oposta à única parede de apoio |
| lavatório | 0,55 / 0,60 / 0,80 m | 0,60 / 0,60 / 0,80 m | oposta ao lado encostado mais longo |
| box | disco 0,60 / 0,60 / 0,80 m na abertura | 0,60 / 0,60 / 0,80 m | único lado livre |
| bancada da cozinha | 0,90 / 0,90 / 1,00 m | 0,90 / 0,90 / 1,00 m | oposta ao lado encostado mais longo |

Fontes e força de cada uma: ver `core/functional_constraints.py` (campo `source` de cada nível) e a proposta de 2026-10-23.
Face não resolvível pelo contrato, portal ausente ou geometria faltando → `BLOCKED_MISSING_INPUT` (nunca palpite).

## Gate
`REPORT_ONLY`: layout existente com `INVALID` não quebra o CI. O CI reprova só registro inconsistente, proveniência ausente,
unidade inválida, `NORMATIVE` sem fonte primária, saída não determinística (`tests/test_fp054_f1b_functional_clearance.py`).

## Contrato para a F2
Restrição hard (`reference_minimum`), alvo, preferido, valor medido, veredito, código do motivo e geometria testemunha. O solver
consome; não redefine limiar, não relaxa hard, não ignora `INVALID`, não converte `BLOCKED_MISSING_INPUT` em aprovado.

## Limitações declaradas
- Face de uso derivada por contrato porque nenhum builder declara `use_face`; declarar no builder é item da F2/F4 (mexe no
  snapshot e em prova L2).
- Abertura do box = meio do lado livre (`HEURISTIC`); o builder não grava onde fica a porta de vidro.
- Heurísticas declaradas no relatório: zona de uso 0,30 m, "encostado" ≤ 6 in, encaixe do portal 0,30 m.
