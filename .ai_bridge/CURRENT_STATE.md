# Current State — 2026-05-08 14:30 UTC

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** this PR (`docs/ai-bridge-refresh-post-wave-2026-05-08`)
- **develop @** `07fd499` (clean, in sync with origin)
- **Active CI:** `ci.yml`, `skp_fidelity_gate.yml`, `rubocop.yml`,
  `quality_gates.yml`. Last 4 runs on develop = all green.
- **Open PRs:** ZERO 🎉
- **Local branches alive:** `dashboard/architecture-sre-radar`,
  `dashboard/project-roadmap`, `feature/smoke-promotes-inspector-v2-gate`
  (all out-of-scope of recent waves; `smoke-promotes-inspector-v2-gate`
  is RED-blocked Stage 1.6, no PR opened)

## Last objective (just completed)

**Operational autonomy protocol installed** + `.ai_bridge` refresh.
Memory file added: `feedback_autonomia_operacional_protocolo.md`
(loop GREEN/YELLOW/RED + ChatGPT bridge consult-direct +
auto-merge clean+green + don't ask per-PR).

The 9-PR queue from yesterday is fully merged (Wave A → E + adendos).
See `HANDOFF.md` for the per-PR table with merge SHAs.

## Three trincos status (atualizado)

- ✅ **PDF → SKP determinístico** — pipeline 5-stage stable, smoke
  green, CI green
- ✅ **Incerteza auditável** — coherence_audit + plan truth gate +
  micro truth gate (4 rooms now via Cycle 7)
- ✅ **Verdade externa mínima** — Ground Truth v1 + Fidelity Engine
  v1 (whole-plant) shipped (#58). Currently advisory-mode CI step
  surfaces 3 known FP-012 hard_fails but doesn't block develop.

## Active tools

| Tool | Status |
|---|---|
| `tools/coherence_audit.py` | ✓ stable, schema 1.0 |
| `tools/micro_truth_gate.py` | ✓ stable, schema 1.0 |
| `tools/skp_inspection_report.py` | ✓ stable, schema 1.0 |
| `tools/classify_openings_by_room_context.py` | ✓ stable + Stage 1 contract |
| `tools/inspect_walls_report.rb` | ✓ v2 schema (PR #49) + Lint clean (PR #55) |
| `tools/fidelity/compare_generated_to_expected.py` | ✓ NEW — schema 1.0, 21 unit tests |
| `tools/fidelity/synth_from_expected.py` | ✓ NEW — round-trip helper, 4 guard tests |
| `tools/rooms_from_seeds.py` | ✓ stable + opt-in `--use-concave-hull` (FP-012 spike, default OFF) |
| `tests/test_planta_74_truth_gate.py` | ✓ 15 assertions locked |
| `scripts/smoke/smoke_skp_export.py` | ✓ A-G + H |

## Tests

Re-validated 2026-05-08 14:30 UTC on `develop` (sha `07fd499`):

- Plan Truth Gate: **15/15 PASS**
- Micro Truth Gate: **20/20 PASS** (4 rooms scoring 1.0)
- Coherence Audit: **21/21 PASS**
- Concave-hull spike unit tests: **4/4 PASS**
- Fidelity Engine: **21/21 PASS**
- Fidelity round-trip: **4/4 PASS**
- **Total: 85/85 PASS** in ~3s

## Next ROIs

| Item | Color | Notes |
|---|---|---|
| Refresh `.ai_bridge/*` (this PR) | 🟢 GREEN | factual update |
| **Cycle 8b — promote concave-hull default + recalibrar baselines** | 🟡 YELLOW | needs ratio decision (0.30 / 0.55); will consult LLM local; clears the 3 advisory-mode FP-012 hard_fails |
| Multi-PDF corpus | 🔴 RED | needs Felipe to provide additional PDFs |
| Cycle 6 (Stage 1.6) — autorun inspector wiring | 🔴 RED | Stage 1.6 explicitly held |
| `feature/smoke-promotes-inspector-v2-gate` orphan | 🔴 RED | Stage 1.6 |

## Operational protocol

`feedback_autonomia_operacional_protocolo.md` é a regra ativa:
- GREEN: executar sem pedir
- YELLOW: executar com validação reforçada
- RED: parar e reportar
- ChatGPT bridge / Ollama local: consultar direto, sem virar
  Felipe roteador
- PR CLEAN + verde + escopo esperado → mergear sem pedir
