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

| PR | Branch | O quê | Estado |
|---|---|---|---|
| #247 | `feat/apartamento-mobiliado-completo` | brain do cômodo SERVICE | aguarda VISUAL_REVIEW do Felipe |
| #245 | `fix/baseline-test-failures` | 19 falhas de baseline (ago/12) | stale — CI já verde; reconciliar ou fechar |
| — | `chore/refresh-memory-state` | este refresh de docs | draft → `develop` |

## Comandos de validação

```bash
python -m pytest tests/ -q -m "not planta74_scale"            # 1470 passed, 9 skipped
PT_TO_M=0.0259 python -m pytest tests/ -q -m planta74_scale   # 71 passed, 1 skipped
git diff --quiet origin/main origin/develop && echo "main == develop (árvore)"
```

## Aguardando

- VISUAL_REVIEW do #247 (Felipe).
- Decisão sobre #245 e sobre as branches `backup/stash-0..4`.
