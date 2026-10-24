# Handoff — FP-057 (orquestração autônoma do backlog) e Quality Guardian — 2026-10-24

Retrato datado; estado vivo: GitHub Project #1 + `python -m tools.validation.autonomous_status`. Base: `develop@464700e`.

## 1. O que está em `develop` e funciona
- **FP-057 P0–P7**: descoberta/elegibilidade (`backlog_discovery`, `dependency_graph`), scheduler com claim e lease
  (`task_scheduler`, `execution_state` em `<git common dir>/runs/governance/execution_state.json`), intake de defeitos e análise de
  impacto, revisão independente **verificável** (`review_verification`), reconciliação do board (`backlog_reconcile`), prova de recuperação
  (`recovery_proof`, Issue sintética #529) e relatório (`autonomous_status`, `docs/reports/fp057/status/`).
- **Quality Guardian**: `backlog_gate`, `issue_integrity_gate`, `spec_integrity_gate`, `pr_policy_gate` (agora também `PR_BASELINE_WEAKENED`),
  `quality_geometry_gate`, `consumption_baseline`, `protection_check`.
- Qualificação SketchUp 26.0.429 real (2026-10-24): `artifacts/review/fp055/p7/qualification_2026-10-24/`.
- FP-055 P5 parcial: `tools/rooms/recipe_resolution.py`. R4 `RoomBrain`; R5: guarda-roupa, criado-mudo, poltrona e cama no Spec (golden byte a byte).
- R6: alternativas verificadas pelo solver: `artifacts/review/fp056/p8_r6_alternatives/` (resumo na #446).

## 2. O que NÃO funciona ainda (e por quê) — leia antes de confiar nos checks
1. **#533 (P0): os checks `qg:*` passavam em falso.** `gate | tee` sem `pipefail` devolvia o status do `tee`. Correção no **PR 534**
   (`defaults.run.shell: bash`), que toca `.github/workflows/` e **aguarda revisão independente**. Até o merge, não confie em `qg: *` vermelho/verde: rode os
   gates localmente (`python -m tools.validation.<gate>`).
2. **Revisão independente (#524)**: `docs/governance/review_policy.json: reviewers` está vazio (uma só conta GitHub). Nenhuma Issue P0/`gpt-review-required` chega a Done e os PRs **534, 535, 539** ficam abertos de propósito.
   O PR 531 (já mergeado) tocou `pr_policy_gate.py` sem a label: pede revisão retroativa (comentário na #533).
3. **Project**: sem `BACKLOG_PROJECT_TOKEN` (#508) o workflow não escreve no board; localmente `backlog_reconcile --apply` (token do `gh`) resolve. Campo "Estado da prova" do Project não é movido pelo reconcile (`pj.setf(prova=...)`).
4. **MCP `sketchup`**: checkout levado a `develop` por ff-only; o **processo** do servidor está velho (`process.stale`). Reconectar o servidor no app (ver `docs/engineering/mcp_runtime_restart.md`); só então a #457 (smoke `su_*` real) é executável.
5. **Workflows `schedule`/`issues`** só rodam no branch padrão (`main`): inertes até promover develop → main (#507, decisão do proprietário).

## 3. Como retomar
```bash
export PY=E:/Claude/apps/sketchup-mcp/.venv/Scripts/python.exe   # na worktree: PYTHONPATH=.
$PY -m tools.validation.backlog_gate                 # esperado: 0 divergências
$PY -m tools.validation.backlog_reconcile            # plano; --apply escreve no Project
$PY -m tools.validation.task_scheduler next          # próxima elegível (claims ativos respeitados)
$PY -m tools.validation.autonomous_status
```
`gh`: `"/c/Program Files/GitHub CLI/gh.exe"`, `unset GH_TOKEN`, `--repo GFCDOTA/sketchup-mcp`. Merge só com os 8 checks verdes no head exato: `gh pr merge N --merge --match-head-commit SHA`.

## 4. Pendências dependentes do proprietário (nada disso foi aplicado)
Configurar revisor independente (#524) · reconectar servidor MCP · decisões #446 (R6, com alternativas medidas), #484, #486, #495, #497, #442, #447–#452 ·
`BACKLOG_PROJECT_TOKEN` (#508) · promoção develop → main (#507) · veredito visual (sempre `PENDING_HUMAN`).

## 5. Armadilhas desta sessão (já custaram tempo)
- Heredoc do Bash corrompe `\n`/`\b`: edições por script Python em arquivo ou Edit/Write.
- Windows Python não enxerga `/tmp` do Git Bash como esperado: use caminhos do repo (`runs/`) para arquivos lidos por Python.
- Teste de contenção de lock: `locked()` precisava tolerar o dono apagar o arquivo entre `open` e `stat` (corrigido, PR 528).
- Ao criar `inventário`: `python -m tools.navigation.register_evidence <arquivos>` (para `artifacts/review/**`); para código/teste, entradas no `fp042_inventory.v1.json` seguem o dono do caminho (`tools/rooms/*.py` → `room_module_governance`).
- Rodar o solver F2 leva 2–10 min por cômodo; use `run_in_background` e outra worktree para não trocar de branch sob um processo vivo.
