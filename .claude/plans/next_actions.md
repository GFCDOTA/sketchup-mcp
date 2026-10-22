# Next actions — sketchup-mcp

Fila curta (máx. 5). A fila completa e o estado de cada microfase moram em
`docs/specs/construction_core_microphases.md` §4 — esta lista é só o topo dela.

> **Snapshot:** 2026-10-22.

1. **T0.1 — R-18 transitivo.** `closure_digests` na evidência L2 (fecho `tools.rooms`/`core` calculado no commit da prova);
   gate do catálogo acusa fecho velho. Sem isso, detalhe novo num helper (`build_parts`) mantém `L2_PASS` falso.
2. **T0.2 — scratch do `cabinet.sketchup.inspect` em `runs/`** (teste vermelho com caminho protegido + L2 de regressão).
3. **T0.3 — FP-051 P1** `plan_furniture_goal()` puro, com `BLOCKED_TARGET_UNDEFINED` (FP-052) como dependência de produto.
4. **T0.5 — placement FP-050 como gate obrigatório** nos dois fluxos da cozinha, refazendo o L2 de ambos.
5. **Com o Felipe:** veredito L3 da Shaker (#356) e revisão do trecho do tampo (07:09–08:53) → abre K1.

## Regra de fila

Concluir um item → o próximo só se tiver valor claro de produto (componente mais fiel/mais detalhado, prova honesta,
gate falhando, PR aberta). Não inventar trabalho cosmético. Ver `memory/operational_rules.md`.
