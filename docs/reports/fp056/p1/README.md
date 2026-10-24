# FP-056 P1 — erro de unidade da A.S. (RC-B) + circulação respeitada na origem (2026-10-24)

## Correção
`tools/rooms/service/layout.py`:
- `_cell_m` e `_circ_m` convertem o `cell` (pontos do PDF) com `× PT_TO_M`. Antes era `× 0,0254` (como se fosse polegada),
  e a zona da A.S. saía 1,9% menor.
- Os limites de zona (`_AS_MAX_X_M`, `_TEC_MIN_X_M`, `_AS_MIN_Y_M`), que tinham sido lidos no referencial errado, foram
  reescalados pelo mesmo fator. Ficam no **mesmo lugar** em relação ao polígono, e o zoneamento validado pelos seeds do PDF
  não muda.
- **Circulação na origem:** cada peça de piso só entra se não fizer o `circulation_gate` do cômodo passar de PASS para FAIL.
  O gate e o limiar são os mesmos que o furnish/preflight já usam. A peça tenta as larguras do próprio programa e, se nenhuma
  serve, é omitida com o motivo em `out["dropped"]`. Banquetas e mesa seguem a mesma regra.

## Por que a circulação entrou junto
Com a escala certa, a churrasqueira de 1,00 m estreitava a passagem secundária do terraço para **0,79 m** (alvo 0,80). O
layout antigo só "passava" porque o erro de escala empurrava peças para fora do cômodo. Corrigir a escala sem respeitar a
circulação trocaria um defeito por outro.

## Resultado (gêmeo em caixas contra o baseline da FP-055 P4)
- **Resolvidos 5 de 5** defeitos da A.S. do baseline (máquina de lavar 21 cm, bancada gourmet 20 cm, jardineira 15,6 cm,
  armário 3,3 cm, condensadora 2,9 cm); sem defeito novo nem pior. A.S. sem nenhum achado no gêmeo.
- Circulação da A.S.: PASS (passagem secundária 0,85 m).
- Os outros 7 cômodos estão idênticos (`fp044_baseline`: só `CAIXAS_MUDARAM: A.S.`). Snapshot do apartamento
  `5426c0087bdfcdc6` (394 peças) → `a4fa928927d11a0f` (**390** peças). Baseline FP-044 novo em
  `artifacts/review/fp056/p1/fp044_baseline.json`; os anteriores ficam como retrato histórico.

## Gêmeo em caixas (`tools/validation/box_geometry.py`)
Valida uma proposta **antes** do SketchUp com o mesmo validador do construído (v2). Fidelidade medida: nos 7 cômodos não
tocados reproduz as 29 chaves do baseline construído a no máximo 0,08 mm. O único desvio é declarado:
`r004|CONTAINMENT|backsplash` aparece no gêmeo com 0,6 mm (ε = 0,5 mm), enquanto o construído mediu 0,52 mm na parede, ou
seja, dentro do ruído de arredondamento da exportação. Teste: `tests/test_fp056_p1_box_twin.py`. **Não substitui o L2.**

## Decisão de projeto PENDENTE (Felipe) — registrada, não aplicada
O programa do terraço social (notas do PDF: churrasqueira + coifa, bancada gourmet + cuba) **não cabe inteiro** com a
circulação mínima. Pela ordem do programa atual, a churrasqueira (1,00 m) entra e a **bancada gourmet + cuba e a mesa externa
saem**. Alternativas, a decidir:
- **(a)** manter assim (churrasqueira inteira, sem bancada);
- **(b)** churrasqueira mais estreita (0,85 ou 0,70 m, larguras já previstas no programa), para tentar a bancada (a medir);
- **(c)** outra distribuição do terraço.

Enquanto não houver decisão, vale (a), que é o comportamento determinístico atual, e nada é escondido: as omissões aparecem
como TRADE-OFF no log e em `out["dropped"]`.

## Provas
- `tests/test_fp056_p0_root_causes.py::test_service_planner_cell_is_in_the_plants_metres`: era `xfail(strict)`, agora
  **passa**.
- Suítes completas verdes; os pinos de snapshot foram atualizados com o motivo (`test_fp044_baseline`, `test_fp047_diff`,
  `test_fp054_f1c_semantic_interfaces`, `test_fp055_p0_pipeline_audit`).
- `service.layout.boxes` é `L1_PASS`, sem prova L2 a revogar. A prova no SketchUp real desta mudança entra na geração
  completa da FP-056 P6.
