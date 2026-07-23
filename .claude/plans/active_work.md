# Active work — sketchup-mcp

Branch em curso, objetivo, escopo, validação.

> **Atualizar a cada session start / branch switch.** Se este
> arquivo estiver stale, qualquer agente deve reconciliar antes
> de operar.

> **Snapshot:** 2026-07-23 (handoff). Branch ativa:
> `fix/planta74-furnished-fidelity` @ `a35ece6` (== `origin/develop`, local-only,
> sem commit próprio). ⚠️ **3 fixes de furnish NÃO commitados** na working tree
> (tapete clipado ao cell · guard wet-room · piso neutro FURNISH_NEUTRAL_FLOOR)
> — resposta ao **9× WORSE** da campanha de baseline. Suíte verde COM os fixes:
> **1381 passed, 9 skipped** (2026-07-23). `feat/fp035-retrieval-eval` @ `205c200`
> pushada SEM PR (2 commits: golden-set/eval + RRF). Verdicts/propostas do loop
> ainda untracked. Detalhe em `HANDOFF.md`; plano de ataque em `KICKOFF.md`.

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
- `feat/fp035-retrieval-eval` — pushada, falta PR → develop (landar, não deixar órfã).
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
