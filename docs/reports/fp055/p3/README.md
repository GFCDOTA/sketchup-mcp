# FP-055 P2+P3 — contratos e orquestrador inteligente (2026-10-23)

## P2 — contratos (`core/pipeline_contracts.py`, domínio puro)
- `GenerationRequest`: escrita em `artifacts/`/`fixtures/` só com `allow_official_write`.
- `RoomContext`: polígono em in, unidade fixa.
- `SpecialistPlan`: sem política do solver = erro.
- `LayoutProposal`: `FEASIBLE` com violação rígida = erro; `buildable_as_valid` só se for `FEASIBLE`.
- `ValidationReport`: estados `PASS/FAIL/BLOCKED/NOT_APPLICABLE/NOT_EXECUTED`.
- `BuildResult`: objeto não construído sem motivo = erro.
- `CapabilityLedger`: estados em ordem. `CONSUMED`, `REFLECTED_IN_MODEL` e `VALIDATED` exigem evidência do efeito.

Produtor → consumidor, e o teste de cada um:
- request → `run`;
- especialista → `plan_room`;
- `plan_room` → solver (`build_problem(policy=...)`);
- solver → proposta (`LayoutProposal.boxes` = caixas que o builder deve construir, P4).

Testes em `tests/test_fp055_p2_p3_pipeline.py`.

## P3 — `tools/orchestration/intelligent_pipeline.py`
Etapas: identidade de runtime (P1) → revisão da fonte (sha256 do consensus) → caixas de base do builder de cada cômodo →
interfaces F1C → por cômodo:
1. Perfil do especialista: schema e o builder precisa estar na **allowlist**.
2. `solver_policy` do especialista entra no problema (âncoras e graus de liberdade).
3. Receitas: `SELECTED`.
4. Solver F2 com ordem lexicográfica: a 1ª alternativa vira a proposta.

Depois: `ValidationReport` e manifesto com o ledger. Cômodo sem política fica `NOT_INTEGRATED`, explícito. `valid` só é `true` se
**todo** cômodo pedido for `FEASIBLE`.

**Gate P3 (fixture sintética, `test_specialist_constraint_changes_the_proposal_with_trace`):** com a política do banheiro o vaso
desliza e a proposta fica `FEASIBLE`. Com uma política de teste de vaso fixo, a proposta fica `INFEASIBLE` (`ORIGINAL`), e o
`policy_version` da proposta e a trilha do ledger mostram a política. Outros testes negativos:
- builder fora da allowlist: `BLOCKED`;
- interface semântica ausente: `INVALID_INPUT` (o contrato do solver recusa antes de enumerar) e o ledger fica em `INVOKED`, não
  `CONSUMED`;
- runtime velho: `BLOCKED_RUNTIME`;
- consensus com hash diferente: `BLOCKED_SOURCE_REVISION`.

Smoke na planta real (`--rooms r004,r000 --allow-dev`, checkout sujo marcado `DEV_OVERRIDE`): cozinha `FEASIBLE`
(`ORIGINAL`). Suíte 01 `NOT_INTEGRATED`: o run é `NOT VALID`, como deve ser.

## O que ainda NÃO é
- Nenhum SketchUp: o perfil `INTELLIGENT_BUILD` e a comparação proposta × construído ficam para a P4.
- Receitas não viram operação (P5).
- Quarto, sala e serviço sem política de solver (P6).
- O caminho legado (`furnish_apartment.main`, `su_furnish`) continua igual: o novo roda ao lado (Strangler Fig).
