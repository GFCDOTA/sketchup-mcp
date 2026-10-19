# Active work — sketchup-mcp

Branch em curso, objetivo, escopo, validação.

## Continuação FP-041 / PR #252 — 2026-10-18

Autorização do Felipe nesta sessão: "pode dar continuidade", após a proposta
de integrar as receitas ao especialista e preparar micro-fixture consultiva.
Branch: `feature/fp041-sketchup-video-knowledge`, base remota conferida
`919fd9dc3dcd7f64cd49d9faf2fc4f3ed1a84b61` (PR aberto em draft para `develop`).

- Adicionado `sketchup-tooling-specialist` somente leitura, conectado ao mapa
  do orquestrador e ao catálogo de oito receitas.
- `tools.sketchup.knowledge`: CLI read-only de consulta e plano sintético de
  gabinete (uma porta, três frentes de gaveta). Cálculos L1 e proveniência;
  nunca autoriza execução nem importa jobs/MCP/Ruby.
- Caso de teste em `tests/data/sketchup_knowledge/`, sem mudar `fixtures/`,
  builders, materializadores, `.skp` ou arquitetura.
- Escopo/aceite: `docs/specs/FP-041_video_knowledge_consultation.md`.
- Pendente: MVP geral FP-041 (ledger, OperationPlan e avaliação de competência),
  materialização paramétrica de componentes e prova no SketchUp real.
  L2 `PENDING_SKETCHUP`, L3 `PENDING_HUMAN`; não declarar melhoria do apartamento.
- Continuação mantém PR em draft e não faz merge.
- Validação local: 25 testes focados; suíte padrão 1536 passed / 19 skipped,
  escala planta_74 74 passed; ruff dos arquivos Python novos, dois gates
  determinísticos e smoke/stdio MCP passaram. Skips incluem Ruby ausente,
  Qdrant/Ollama offline e artefatos não gerados; não são prova L2.

O snapshot abaixo é histórico da sessão de reconciliação, anterior ao PR #252.

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
