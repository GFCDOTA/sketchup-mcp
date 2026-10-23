# Next actions — sketchup-mcp

> Status após PRs #371–#374 em 2026-10-22. Fila autoritativa: docs/specs/construction_core_microphases.md.
> CI Linux verde não substitui L2 SketchUp Windows nem revisão humana L3.

> **2026-10-23 — FP-054 tem precedência** (`docs/specs/FP-054_spatial_core_reliability_program.md`, recebida como FP-045 MASTER):
> F0 baseline → F1 corretude geométrica → F2 solver → F3 modularização/DSA → F4 SketchUp real → F5 rollout.
> **Congelado até a F5 liberar:** expansão de tutoriais/RAG (item 3 abaixo) — nada é apagado, só não avança.
> Os itens 1, 2 e 4 entram como insumo da F1–F4 quando a fase pedir.
> **Estado 2026-10-23:** F0 (#383) e F1-01..04 (#384–#387) mergeadas; `su_furnish` do apartamento recusa até a decisão da
> Suíte 01 (#381). Detalhe e próximo comando: `docs/handoffs/2026-10-23_fp054_f0_f1_handoff.md`.

1. **T0.2 restante:** integrar tools.sketchup.inspect_workspace.plan_inspect_workspace (#373) em cabinet.sketchup.inspect;
   refazer L2 Windows de todas as capacidades afetadas pelo símbolo/fecho R-18. PREP L1 pronta, integração NÃO feita.
2. **T0.5 restante:** ligar gate de placement FP-050 a cabinet_flow e shaker_flow sem bypass;
   usar teste da Golden Demo mesa/cadeira/corredor (#374), e refazer L2 Windows lisa/Shaker. Gate ainda NÃO conectado.
3. **K1/K2/K4:** revisar tutoriais em segmento exato, alvo FP-052 e ficha da cuba antes de aprender recorte/tampo/gaveta;
   nenhuma geometry proxy, sem declarar demo técnica aprovada.
4. **B1 e consumidores:** aplicar shared_transform.v1 (+Y↔−Y) (#372) em micro-fixture antes do guarda-roupa real.
5. **Com usuário:** L3 Shaker (#356), decisões do alvo kitchen_base_001, D-007/D-009 e CLIs apenas documentadas.

## Concluído e não refazer

- **T0.1** (#363): evidência transitiva.
- **T0.3** (#371): plan_furniture_goal() consultivo, DAG/gap/alvo fail-closed; sem execução.
- **T0.4** (#372): transformações compartilhadas e testes de propriedades, L1.
- **T0.2 prep** (#373): scratch seguro somente planejamento, ainda sem alteração de inspector.
- **T0.5 demo** (#374): corredor sintético com envelope da cadeira, somente oráculo L1.

Regra: microfases, testes, provas vigentes e encerrar todo PR aberto; jamais promover L1 como L2/L3.
