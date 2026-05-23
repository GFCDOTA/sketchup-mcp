# Consolidation cycle hygiene audit — 2026-05-23

> Cycle sob CLAUDE.md §15 + user-mandated consolidation request.
> **Audit-only**: 0 deleções tracked. 1 doc novo (este). Catálogo de
> candidatos REVIEW_REQUIRED.
>
> Continuação dos audits anteriores:
> - PR #73 (Cycle 1, 2026-05-06)
> - `docs/diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md` (Cycle 2)
> - `docs/ops/repo_hygiene_audit_2026-05-10.md` (Cycle 3)
> - `docs/_archive/2026-05-cleanup/` (PRs #133/#134, 2026-05-15)
>
> Esses três audits convergiram em "preservar root-level .py
> (proto_*, analyze_overpoly, render_*)" — gatilho para cleanup é
> raster retirement, ainda não disparado. **Não re-auditados neste
> cycle.**

---

## Escopo deste audit

Só o que **mudou ou foi adicionado desde 2026-05-10**:

1. Tracked files novos / modificados nesta sessão
2. Untracked files em `tools/` aparecidos entre cycles
3. Artefatos locais (gitignored) em `runs/quadrado_demo/`
4. Eventual drift de docs vs realidade pós-PR #142

---

## 1. Tracked files novos / modificados nesta sessão (2026-05-23)

| File | Mudança | Status |
|---|---|---|
| `docs/learning/lessons_learned.md` | +LL-013 +LL-014 | ✅ canonical |
| `docs/learning/failure_patterns.md` | +FP-016 +FP-017 +FP-018 +FP-019 | ✅ canonical |
| `.ai_bridge/CURRENT_STATE.md` | rewrite (#121 → #142 + active rules) | ✅ canonical |
| `.ai_bridge/HANDOFF.md` | +session 2026-05-23 entry | ✅ canonical |
| `docs/diagnostics/2026-05-23_consolidation_hygiene_audit.md` | new (this doc) | ✅ canonical |

Todas alterações são pure docs / state snapshots, não tocam pipeline.

---

## 2. Untracked files em `tools/` (REVIEW_REQUIRED)

`git status` mostra 4 untracked:

```
?? tools/build_room_ring_skp.py
?? tools/build_room_ring_skp.rb
?? tools/dump_skp_groups.py
?? tools/dump_skp_groups.rb
```

### Inspeção rápida

- `tools/build_room_ring_skp.{py,rb}` — gera um SKP ring a partir de
  consensus simples (precursor do `plan_shell`). Já existem em
  `runs/quadrado_demo/quadrado_ring_inner_clear_with_floor.skp`
  produzidos por essa ferramenta. Função possivelmente coberta pelo
  `plan_shell` atual.
- `tools/dump_skp_groups.{py,rb}` — utilitário de dump da estrutura
  de grupos de um SKP. Função adjacente a `inspect_walls_report.rb`
  (já tracked).

### Classificação

- **STATUS:** REVIEW_REQUIRED. Não promover nem arquivar sem decisão.
- **Risk:** se arquivar, perde POC ring builder histórico. Se commitar
  sem testes, viola CLAUDE.md §1 (Hard Safety Rules).
- **Próximo passo:** investigar origem (qual sessão criou? qual o
  status no `plan_shell`?) antes de promover ou arquivar. Adicionado
  como item P1 em `.ai_bridge/CURRENT_STATE.md` § "Next-session queue".

---

## 3. Artefatos locais em `runs/quadrado_demo/` (gitignored)

Todos os arquivos abaixo são gitignored (`/runs/` no .gitignore root)
— não pollui git. Mas é boa higiene local manter o dir compreensível.

### Canonical (KEEP)

| File | Purpose |
|---|---|
| `quadrado.skp` | Micro-fixture canônico (32 KB, 34 entities raw, abre limpo) |
| `quadrado_with_window.skp` | POC de in-place window edit (38.8 KB, 19 faces, 8/8 invariants PASS) |
| `quadrado_with_window.skp.metadata.json` | Sidecar metadata |
| `quadrado_with_window_render.png` | SU `write_image` 1600×1200 do POC |
| `invariants_report.md` | Report 8/8 PASS, evidência da etapa 3 |
| `consensus.json` | Consensus do quadrado canônico |
| `_add_window.rb` | Implementação Ruby do POC (push/pull + intersect_with) |
| `_inspect_skp.rb` | Inspector genérico via autorun mechanism |
| `_invariants.py` | Harness Python que gera o invariants_report |
| `_render_view.{py,rb}` | SU screenshot harness |
| `_run_add_window.py` | Launcher do `_add_window.rb` via autorun |

### Runtime markers (REGENERABLE — safe to clean locally)

| File | Why regenerable |
|---|---|
| `_add_window_done.txt` | done marker, regen on next run |
| `_add_window_log.txt` | run log, regen on next run |
| `_inspect_skp_done.txt` | done marker |
| `_render_done.txt` | done marker |
| `quadrado_topology.txt` | inspector output, regen on next invariants run |
| `quadrado_with_window_topology.txt` | inspector output, regen |
| `quadrado_with_window.skb` | 0-byte SU backup leftover |

**Decisão:** não deletar agora (gitignored, não atrapalha). Se quiser
limpar localmente: `rm runs/quadrado_demo/_*_done.txt
runs/quadrado_demo/*_log.txt runs/quadrado_demo/*_topology.txt
runs/quadrado_demo/*.skb`.

### Wrong-path artifacts (KEEP as evidence)

| File | Why |
|---|---|
| `consensus_with_window.json` | Consensus derivado que foi a abordagem incorreta (FP-017 evidence). Preservar enquanto LL-013 está fresco. |
| `_inspect_orig.rb` + `_inspect_orig_done.txt` + `_orig_topology.txt` + `_run_inspect_orig.py` | Sub-stage de descoberta da topologia; útil pra documentar o caminho. |

---

## 4. runs/ dirs candidatos (review-only; gitignored, sem ação)

Tamanhos de pastas em `runs/`:

| Dir | Size | Last evidence of use |
|---|---|---|
| `_milestone_skp_planta74_2026_05_09/` | 3.5M | Milestone marker, 2026-05-09 |
| `_test_vector_regression/` | small | Regression dir, status unknown |
| `audit/` | 2.4M | Ativo (referenced in HANDOFF) |
| `cycle11c/` | 131K | Cycle 11c history |
| `feature_room_context_2026_05_06/` | 1.2M | Dated 2026-05-06 |
| `floor_r001_split_before_after/` | 1.5M | Specific debug session |
| `planta_74_clean_debug/` | 601K | Debug snapshot |
| `planta_74_plan_shell/` | 1.7M | **CANONICAL** (active SKP target) |
| `planta_74_plan_shell_layers/` | 2.6M | Active variant |
| `planta_74_plan_shell_smoke/` | 842K | Active smoke output |
| `png_history/` | 7.2M | Active (per memory `reference_png_history_protocol.md`) |
| `post_rectify_v2/` | 221K | Historical |
| `postfix_2026-04-29/` | 3.5M | Historical (2026-04-29) |
| `preflight_apto74_2026_05_10/` | 2.5M | Recent preflight |
| `quadrado_demo/` | 229K | **CANONICAL micro-fixture** |
| `retangulo_3x5_demo/` | 352K | Earlier shape demo |
| `skp_current_20260504T215920Z/` | 814K | Timestamped current marker |
| `smoke/` | 12M | **CANONICAL** smoke gate output |
| `spec_harness_demo/` | 12K | Spec-driven harness demo |
| `v1_pipeline_after/` | 886K | Historical pipeline state |
| `vector/` | 20M | **CANONICAL** vector pipeline runs |

**Decisão:** sem ação. Todos gitignored. PRs #133/#134 já fizeram
deep clean (2026-05-15) — re-fazer agora seria hygiene-in-loop
contra `feedback_no_hygiene_loop_sem_trigger.md`.

**Trigger pra próximo audit destes:** ou (a) raster retirement, ou
(b) plan_shell becomes the only path, ou (c) explicit user request.

---

## 5. Drift checks pós-PR #142

| Doc | Estado pré-sessão | Ação |
|---|---|---|
| `.ai_bridge/CURRENT_STATE.md` | Frozen em PR #121 (2026-05-13) | ✅ refreshed pra #142 |
| `.ai_bridge/HANDOFF.md` | Última seção em 2026-05-13 | ✅ +session 2026-05-23 |
| `.ai_bridge/TODO_NEXT.md` | Top item ainda válido (Slice 6a) | ⚠️ verificar se outros itens cycle 6+7 ainda batem com pós-#142 |
| `CLAUDE.md` | Última update 2026-05-14 | ⚠️ canonical artifact rule não documentada lá (vive em user MEMORY) |
| `docs/learning/decision_log.md` | Não verificado | TODO próximo cycle |
| `docs/learning/validation_matrix.md` | Não verificado | TODO próximo cycle |

---

## Decisões deste audit

- **Manter root-level `proto_*.py`, `analyze_overpoly.py`,
  `render_*.py` (raiz), `crop_legend.py`, `peek_pdf.py`,
  `preprocess_walls.py`, `make_test_pdf.py`** — preservados por
  política dos 3 audits anteriores; gatilho pra cleanup é raster
  retirement, não disparado.
- **Não tocar `tools/build_room_ring_skp.{py,rb}` nem
  `tools/dump_skp_groups.{py,rb}`** — REVIEW_REQUIRED até descobrir
  origem e função no `plan_shell` atual.
- **Não tocar runs/** — gitignored + PR #133/#134 já fizeram deep
  clean. Re-cleanup violaria `feedback_no_hygiene_loop_sem_trigger`.
- **Commit deste audit** + lessons + state docs como uma única
  alteração de docs (`chore(docs): consolidation cycle 2026-05-23
  — canonical artifact rule + state refresh + audit`).
- **Não aplicar limpeza local em `runs/quadrado_demo/`** sem
  pedido explícito do user — POC artifacts são úteis pra etapa 4–5
  da regra canônica.

---

## Próximos triggers que liberariam mais cleanup

1. Raster retirement (plan_shell promoted to sole exporter) → muitos
   root-level `proto_*.py` + `render_*.py` viram archive
2. PROMPT-RENAN.md / PROMPT-FELIPE.md superseded → archive
3. Etapa 5 do quadrado POC aplicada e regression test estável →
   POC helpers em `runs/quadrado_demo/_*.{py,rb}` viram canonical
   tools em `tools/` ou archive
4. ADR-005 (spec-driven) promoted from Phase 2 (observational) to
   Phase 3 (blocking) → ADR-001 status pode mudar
