# FP-054-F1C — Semantic Functional Interfaces, Source Provenance & Visual Evidence

> Extensão curta da F1 (depois da F1B, #395). **Não libera a F2.** Os `INVALID` da F1B/F1C são *findings provisórios do
> modelo*, não defeitos de layout comprovados. Nada é movido nem corrigido aqui.

## 1. Interfaces funcionais explícitas
`core/functional_constraints.FunctionalInterface` (`use_face` | `work_face` | `shower_entry`), com segmento, normal, **base**
(`SEMANTIC_BUILDER` | `SEMANTIC_PDF_ANCHOR` | `SEMANTIC_DECLARED` | `HEURISTIC_GEOMETRY`) e fonte.
- Banheiro: o brain exporta `functional_interfaces` (`tools/rooms/bathroom/layout.py`): face oposta à parede de apoio que o
  posicionamento escolheu; **entrada do box = vão livre da porta de correr** (frente − comprimento da folha), via `_box_front`,
  fonte única do desenho e da interface. Nenhuma caixa muda.
- Cozinha: `tools/rooms/kitchen/functional_interfaces.py` — face de trabalho oposta à parede da pia (âncora hidráulica do PDF,
  `anchor_rules.validate`). `build_boxes` (prova L2) intocado.
- Fallback geométrico da F1B: só em `REPORT_ONLY`, marcado `HEURISTIC_GEOMETRY`; nunca inventa largura de vão do box.
  Em `SOLVER`, sem interface semântica → `BLOCKED_MISSING_INPUT` (`semantic_<interface>`).
- Interface que não cai na borda da peça → `BLOCKED_MISSING_INPUT` (`interface_geometry`).

## 2. Fontes no modelo de autoridade do #394
Cada nível de limiar tem `sources` com `source_tier`, `source_type`, `source_ref`, `source_version_or_date`,
`exact_claim_supported` (texto conferido na página em 2026-10-23), `applicability`, `limitations`. Regras do registro:
`NORMATIVE` proibido; `COMFORT_GUIDE` só com fonte C/D; `TECHNICAL_REFERENCE` exige A/B/C; `PROJECT_POLICY`/`HEURISTIC` são
tier E. Correções em relação à F1B: o 60 cm do vaso **não** está na página do Planner 5D antes citada (está no Auditório Ibirapuera
e no artigo de circulação do Planner 5D); o "disco de 0,60 m" do box (NBR 9050 citada por terceiros, página com erro 502) saiu —
o box usa o que a fonte conferida sustenta: profundidade livre na frente da entrada e largura do vão.

## 3. Evidência visual
`artifacts/review/fp054/f1c/` — board + overlays da cozinha, Banho 01, Banho 02 e lavabo (objeto, interface, trecho usável,
zona de uso, portal, região alcançável, gargalo, limiares, veredito). Gerados por `tools/validation/functional_clearance_board.py`
a partir do relatório; nenhuma geometria nova é inventada no desenho.

## Comparação F1B × F1C
`docs/reports/fp054/f1c/f1b_vs_f1c.json` (+ tabela em `functional_clearance.md`): todos os 20 resultados da F1B mapeados, com
explicação para cada divergência. Resumo e leitura em `artifacts/review/fp054/f1c/README.md`.

## Parada
Parar aqui para revisão visual da board. Sem F2, sem mover móvel, sem corrigir findings.
