# Active work — sketchup-mcp

Branch em curso, objetivo, escopo, validação.

> **Atualizar a cada session start / branch switch.** Se este
> arquivo estiver stale, qualquer agente deve reconciliar antes
> de operar.

## Branch atual

`feat/fp-030-visual-oracle-gate`

- Base: `origin/develop` em `510140d` (post-merge PR #196 "SKP Proof-of-Progress Gate")
- Criada em: 2026-05-28 (sessão noturna autônoma)

## Objetivo

Implementar o MVP do **Visual Oracle Gate (FP-030)** com:
1. Spec `docs/specs/FP-030_visual_oracle_gate.md`
2. Skill `.claude/skills/skp-visual-self-correction/`
3. Manifest de exemplos visuais
4. Schema `visual_findings.v1`
5. Script MVP `tools/run_skp_visual_review.py` (não placeholder — heurísticas reais)
6. Execução real na `planta_74`
7. `.skp` + renders + findings + summary em `artifacts/review/planta_74/visual_loop_current/final/`
8. Test contract em `tests/test_visual_oracle_contract.py`

Princípio: "No SKP, no progress. No visual proof, no progress.
The user is not the visual regression detector."

## Escopo permitido

- Criar `docs/specs/FP-030_visual_oracle_gate.md`
- Criar skill `.claude/skills/skp-visual-self-correction/SKILL.md`
- Criar `fixtures/visual_oracle_examples/` (19 examples: 3 good_real + 1 good_synthetic + 7 bad_real + 8 bad_synthetic)
- Criar `schemas/visual_findings.schema.json`
- Criar `tools/prompts/visual_oracle_reviewer.md`
- Implementar `tools/run_skp_visual_review.py` (heurísticas: gates_self_check, window count match, floating door, orphan glass, bad window aperture, floor leak)
- Criar `tests/test_visual_oracle_contract.py` (16 tests)
- Atualizar `.claude/CLAUDE.md` + README + index pra mencionar a nova skill
- Rodar visual review **real** na `planta_74` → produz `artifacts/review/planta_74/visual_loop_current/final/` com 6 arquivos
- Promover qualitative axes via inline Claude review

## Fora de escopo (follow-ups)

- `tools/check_skp_proof_of_progress.py` (CI gate) — categoria 5 pendente
- Auto-fix loop entre attempts — MVP só inspeciona e reporta
- Side-by-side composite generator
- Vision API integration
- Wider negative class coverage (misplaced_soft_barrier, etc.) — heurísticas posicionais

## Comandos de validação

```bash
# Suite verde
.venv/Scripts/python.exe -m pytest tests/ -q
# Esperado: ≥105 passed (89 baseline + 16 contract test) + 5 skipped

# Bootloader @imports resolvem
cat .claude/CLAUDE.md CLAUDE.md | grep -oE '@\.claude/[a-zA-Z_/-]+\.md' \
  | sed 's/@//' | sort -u \
  | while read f; do test -f "$f" && echo OK $f || echo MISS $f; done
# Esperado: todos OK

# Rerun do visual review (idempotente, com --force-skp)
.venv/Scripts/python.exe -m tools.run_skp_visual_review \
  --fixture planta_74 \
  --out artifacts/review/planta_74/visual_loop_current \
  --max-attempts 3
# Esperado: verdict=WARN, 0 findings, artefatos em final/
```

## Status

**Concluído** (sessão autônoma 2026-05-28):
- Spec, skill, manifest, schema, prompt, tool, test — todos criados
- Visual review rodou na planta_74 com sucesso (verdict=WARN documentado)
- Claude inline review promoveu qualitative axes (global_visual + scale_rotation) pra PASS
- regression_summary.md preenchido com evidência específica por axis
- `tools/run_skp_visual_review.py` bug fixes aplicados (`relative_to` safe, `--force-skp` sempre, mapping `model_*.png`)

**Aguardando**:
- User wake up + review do PR #198 (Visual Oracle Gate)
- User decide se mergea OU se quer ajustes
- User decide se autoriza item #2 da fila (`tools/check_skp_proof_of_progress.py`)

## PRs abertas pelo user (estado quando o user dormiu)

- **#197** (refine Constitution #8 friction-tax review) — pre-merge ajustes pra #196 que mergeou enquanto rodava. **Aguardando review.**
- **#198** (FP-030 Visual Oracle Gate, este PR) — **aguardando review** após dogfooding.
