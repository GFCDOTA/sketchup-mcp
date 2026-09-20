# Active work — sketchup-mcp

Branch em curso, objetivo, escopo, validação.

> **Atualizar a cada session start / branch switch.** Se este
> arquivo estiver stale, qualquer agente deve reconciliar antes
> de operar.

> **Snapshot:** 2026-08-27 (handoff — AI Pipeline Inspector, Fases 1-3).
> Branch ativa: **`feat/ai-pipeline-inspector-observability`** @ `1f0d677`,
> **8 commits à frente de `develop`**, 1 commit à frente do próprio remoto
> (o `1f0d677` ainda NÃO foi pushado). **Nenhuma PR aberta** — decisão pendente
> do Felipe: landar agora ou seguir pra Fase 4 e landar tudo junto.
> Entregue: `core/observability/` (9 módulos stdlib, DESLIGADO por padrão) +
> `tools/trace_view.py` (CLI de leitura de trace) + ~250 testes novos.
> Suíte: **1470 passed / 71 planta74_scale**, ruff limpo, working tree limpa.
> Nada de geometria/fidelidade/aparência foi tocado — a instrumentação é
> aditiva e não muda execução (provado: bundles byte-idênticos ligado×desligado).
> Próximo: **Fase 4** (transporte SSE em `ops/estudio-front/server.py`).
> Detalhe completo em `HANDOFF.md` (topo, reescrito 2026-08-27) — ler antes de operar.
>
> **Snapshot anterior:** 2026-08-09 (handoff, fim de sessão — troca de computador).
> Branch ativa: **`develop`** @ `4a70232`, sincronizada com `origin/develop`
> (pushado). Hoje mergeou `feat/estudio-banheiro` (101 commits: skill+agent
> `interior-project-audit`, fix de escala 1.36x, fix de teto/parede do banho,
> BOM real, painel `ops/estudio-front` em React) + `fix/planta74-furnished-fidelity`
> (32 commits) direto em develop. Suíte: **1262 passed, 19 failed
> (pré-existentes, mesmas de sempre), 6 skipped**. `feat/mobiliar-bedroom-layout`
> (57 commits, só no GitHub, scale-leak/WARN conhecido) e as 6
> `chore/noc-nf-*` (sistema NOC removido) **deliberadamente NÃO mergeadas**.
> 65 PNGs scratch untracked em `kitchen_angles/` + 1 stash meu de hoje + 4
> stashes de outras sessões, todos preservados sem mexer. Detalhe completo em
> `HANDOFF.md` (reescrito 2026-08-09) — ler antes de operar.

## Estado do repo

- `develop` = linha viva; tudo mergeado e pushado, CI verde, zero
  branches órfãs (limpeza de branches noc-nf feita em 2026-07-10).
- 2026-07-12: **campanha de baseline visual** — `planta_74` mobiliada renderizada
  em 3 perfis (`warm_compact`, `dark_walnut`, `black_wood_gold`) × L0/L1/L2 e
  publicada pro score do GPT/Felipe; `fix(curation)` `bc46b62` nota item
  humano-julgado sem review anterior. Único verdict gravado:
  `warm_compact__L0` = **WORSE**; demais pendentes.
- Programas landados desde o snapshot anterior (2026-06-06):
  FP-032..040 (olho /ask-vision com painel de 3 juízes, correction
  loop, placar, materiais/gates, watchdog v3), FP-035 (RAG: retrieve
  + DesignSpecBundle + taste write-back, Qdrant+Ollama), pipeline
  semi-autônomo (carteiro auto-decider + galeria + curadoria em lote
  + write-back), semantic_zones (room fidelity resolvida),
  sofa_class_gate (Fase 0 do furniture-class wiring).
- 2026-07-11: **fix vf_004** — swing/dobradiça das 7 portas medidos
  do arco do PDF (`tools/door_swing_audit.py`), fixture emendada com
  provenance, `build_door_leaf` respeita `swing_side`; painel votou
  IMPROVED. Higiene geral executada (archives em
  `docs/archive/2026-07-11/`, ~116M de lixo removido).

## Em curso

- `fix/planta74-furnished-fidelity` — 3 fixes de furnish prontos na working
  tree, falta commit → veredito visual → PR (ver `KICKOFF.md`).
- ✅ 2026-07-23: **FP-035 LANDADO em develop** (fusão RRF + fix write-back recall
  + card 🧠 Memória vetorial no :8782); tree principal atualizado (`dd9112e`),
  suíte 1410/0/5 c/ infra viva, Qdrant rebuild (218 chunks). Resta o flip
  `RAG_BACKEND=embed` do gerador (visual-gated) + Felipe revisar golden-set DRAFT.
- Fila seguinte em `next_actions.md`.

## Validação (comandos atuais)

```bash
.venv/Scripts/python.exe -m pytest tests/ -q        # ~1319 passed
.venv/Scripts/python.exe -m tools.door_swing_audit   # PASS 7/7
git rev-parse origin/develop                          # == develop local
```

## Aguardando

- VISUAL_REVIEW humano (Felipe) do swing-fix — evidência em
  `artifacts/review/planta_74/visual_regression_20260711T041950Z/`.
- Notas visuais (Felipe/GPT) dos 8 baselines restantes da campanha 2026-07-12
  (só `warm_compact__L0` = WORSE gravado).
- Decisão sobre a working tree suja: commitar verdicts/propostas/`.skp` regerado
  OU deixar o loop autônomo consumir.
