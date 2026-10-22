# Active work — sketchup-mcp

> **Snapshot:** 2026-10-22. Atualizar a cada início de sessão / troca de branch. O histórico anterior está no git
> (`git log -p -- .claude/plans/active_work.md`) e nos handoffs datados de `docs/handoffs/`.

## Sessão 2026-10-21/22 (Claude Code, worktree `E:/Claude/worktrees/w-prov`)

- **Entregue:** FP-046 P3–P5 (Shaker L2 + promoção, #352–#354), pacote L3 (#356), FP-051 spec + P0 (#357),
  correção do escopo da `human_review` com L2 refeito (#358).
- **Em PR:** instruções do agente (#360: CLAUDE.md enxuto com imports consertados, `.claude/rules/`, 21 skills, skill
  `capability-l2-proof`, `register_evidence`); handoff geral + mapa de microfases + trava de medida embutida.
- **Próximo:** microfase T0.1 (R-18 transitivo) — ver `next_actions.md`.

## Aguardando o Felipe

- Veredito L3 da porta Shaker (#356).
- Revisão de trechos de vídeo (tampo, caixa de gaveta) e curadoria do alvo `kitchen_base_001` (FP-052 T2).
- D-007 (SUITE 02) e D-001..D-005, D-008/D-009.

## Comandos de validação

```bash
python -m pytest tests -q -m "not planta74_scale"
PT_TO_M=0.0259 python -m pytest tests -q -m planta74_scale
python -m tools.rooms.capability_catalog
python -m tools.navigation.builder_detail_audit
```
