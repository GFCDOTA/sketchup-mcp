# Active work — sketchup-mcp

Branch em curso, objetivo, escopo, validação.

> **Atualizar a cada session start / branch switch.** Se este
> arquivo estiver stale, qualquer agente deve reconciliar antes
> de operar.

> **Snapshot:** 2026-10-18.

## Contexto da sessão (2026-10-18)

Sessão remota (sem SketchUp) de **reconciliação**: estudo dos repos
`sketchup-mcp` + `harness-app`, release `develop -> main` e refresh dos docs
de memória (este branch `chore/refresh-memory-state`). Nenhuma superfície de
fidelidade do `.skp` tocada.

## Feito nesta sessão

- **Release `develop -> main`** (`09d9321`, merge commit no padrão
  `chore(release): sincroniza develop -> main`) — `main` estava 258 commits
  atrás; árvores agora idênticas.
- **Suíte verificada em venv limpo:** 1470 passed / 9 skipped (default) +
  71 passed / 1 skipped (`planta74_scale`).
- **Docs de memória reconciliados:** `current_state.md`, `active_work.md`,
  `next_actions.md` (estavam em jun/jul).

## Branches / PRs em voo

Nenhum PR aberto depois do Gate A (2026-10-18): #247, #248, #249 e #250
mergeados; #245 fechado como superado (os 2 bugs reais foram no #250).

## Comandos de validação

```bash
python -m pytest tests/ -q -m "not planta74_scale"            # 1521 passed, 9 skipped
PT_TO_M=0.0259 python -m pytest tests/ -q -m planta74_scale   # 74 passed
git diff --quiet origin/main origin/develop && echo "main == develop (árvore)"
```

## Aguardando

- **VISUAL_REVIEW** (Felipe) da próxima regeneração do furnish: BANHO 01/02
  ficam sem `kb_lixeira` (#250).
- **Prova num SketchUp real** das tools `su_*` (#249, checklist no PR) —
  até lá `proof_state = UNVERIFIED_ON_SKETCHUP`.
- **Gate B do FP-041** (implementação do SketchUp Tooling Specialist) — só com
  autorização explícita do Felipe.
- Decisão sobre as branches `backup/stash-0..4`.
