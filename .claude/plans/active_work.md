# Active work — sketchup-mcp

Branch em curso, objetivo, escopo, validação.

> **Atualizar a cada session start / branch switch.** Se este
> arquivo estiver stale, qualquer agente deve reconciliar antes
> de operar.

> **Snapshot:** 2026-07-11.

## Estado do repo

- `develop` = linha viva; tudo mergeado e pushado, CI verde, zero
  branches órfãs (limpeza de branches noc-nf feita em 2026-07-10).
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

- Nada em voo além da manutenção. Fila real em `next_actions.md`.

## Validação (comandos atuais)

```bash
.venv/Scripts/python.exe -m pytest tests/ -q        # ~1319 passed
.venv/Scripts/python.exe -m tools.door_swing_audit   # PASS 7/7
git rev-parse origin/develop                          # == develop local
```

## Aguardando

- VISUAL_REVIEW humano (Felipe) do swing-fix — evidência em
  `artifacts/review/planta_74/visual_regression_20260711T041950Z/`.
