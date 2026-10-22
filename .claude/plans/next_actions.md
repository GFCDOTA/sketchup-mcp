# Next actions — sketchup-mcp

Fila curta (máx. 5). A fila completa e o estado de cada microfase moram em
`docs/specs/construction_core_microphases.md` §4 (trilhas T/K/B/L/W/S/C) e §4.1 (trilha R: SOLID, patterns, desempenho).

> **Snapshot:** 2026-10-22 (fim da sessão de reorganização, PRs #360–#369).

1. **R3 = T0.2 — `scratch_dir` único para os inspects** (gabinete e Shaker) e fim do scratch ao lado de `.skp` protegido;
   refaz o L2 de `shared.cabinet.parametric` e `kitchen.cabinet.plain-fronts` (skill `capability-l2-proof`).
2. **T0.3 — FP-051 P1** `plan_furniture_goal()` puro, reportando `BLOCKED_TARGET_UNDEFINED` (FP-052) como dependência.
3. **T0.5 — placement FP-050 como gate obrigatório** nos dois fluxos da cozinha, refazendo o L2 de ambos.
4. **R4/R5** — `RoomBrain` (Protocol) no registro de brains; medida embutida → spec, começando pelo guarda-roupa.
5. **Com o Felipe:** veredito L3 da Shaker (#356), revisão do trecho do tampo (07:09–08:53), decisão sobre as 6 CLIs só
   documentadas (`docs/reports/file_audit/README.md`) e D-009 (`ops/`).

## Regra de fila

Concluir um item → o próximo só se tiver valor claro de produto (componente mais fiel/mais detalhado, prova honesta,
gate falhando, PR aberta). Não inventar trabalho cosmético. Ver `memory/operational_rules.md`.
