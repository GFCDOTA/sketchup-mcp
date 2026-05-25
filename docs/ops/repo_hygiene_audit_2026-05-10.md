# Repo hygiene audit — 2026-05-10

> Cycle 3 sob CLAUDE.md §15 (Repository Hygiene Protocol). Audit-only:
> zero deleções, zero arquivamentos, zero mudanças de código.
>
> Continuação direta de:
> - PR #73 / [`hygiene_2026-05-06.md`](hygiene_2026-05-06.md) (Cycle 1)
> - [`docs/diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md`](../diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md) (Cycle 2 — diagnostic)
> - [`post_wave_state_2026-05-08.md`](post_wave_state_2026-05-08.md) (Cycle 2 — ops snapshot, §"Hygiene scan findings")

---

## TL;DR

- **0 deleções tracked. 0 arquivos movidos. 1 doc novo (este).**
- 28 candidatos da raiz inventariados; todos preservados com evidência re-validada.
- 3 audits consecutivos (2026-05-06, 2026-05-08, 2026-05-10) chegaram à mesma conclusão. Pattern: cleanup desses arquivos depende de **trigger humano explícito** (raster retirement) que ainda não disparou.
- Re-validação revelou **mudança de evidência desde Cycle 1**: refs em `docs/ROADMAP.md` / `docs/repo_hardening_plan.md` / `pyproject.toml` que justificavam preservação em PR #73 **sumiram**. Refs em `docs/_archive/2026-04-f1-cycle/*` e `patches/README.md` ainda preservam o link — mas a base de preservação encolheu.

---

## Precedente — 3 audits convergem

| Cycle | Data | Doc | Conclusão |
|---|---|---|---|
| 1 | 2026-05-06 | [`hygiene_2026-05-06.md`](hygiene_2026-05-06.md) (PR #73) | "Per §15, anything referenced by docs is preserved." → 0 deletions tracked + 5 merged branches removed + 1 untracked .rar removed |
| 2 | 2026-05-08 | [`docs/diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md`](../diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md) | "Action this cycle: **None.** … Recommend ONE more pass next session" → recomenda re-audit quando raster retirement disparar |
| 2 | 2026-05-08 | [`post_wave_state_2026-05-08.md`](post_wave_state_2026-05-08.md) | "**No archive action this PR.** All candidate files either: have at least one indirect reference … are small (< 100 LOC each) … appear in documented 'tech debt' category" |
| **3** | **2026-05-10** | **este doc** | **"Audit-only — preserve. Trigger threshold lowered (Cycle 1 anchor refs partially gone) but still above human-decision line."** |

**Triggers de retirada citados nos audits — status:**

| Trigger | Sinalizado? |
|---|---|
| Raster pipeline officially retired (CLAUDE.md §10 deixa de marcar raster como OUTDATED-but-kept) | ❌ não — §10 ainda mantém o registro |
| "Next wave of repo hardening (`docs/repo_hardening_plan.md`) lands" | ❌ não — `docs/repo_hardening_plan.md` ainda é roadmap |
| `tests/test_renderers_migration.py` "future release" gate explicitamente declarado fechado | ❌ não — back-compat ainda ativo |
| `.ai_bridge/` ledger explicitamente retira refs históricas dos PROMPT-*.md | ❌ não — patches/README.md:194 ainda cita PROMPT-RENAN.md como autoridade de invariantes |

---

## Inventário completo

### Arquivos `.py` na raiz (17)

| Arquivo | Tamanho | Categoria | Risco | Evidência (refs ativas re-confirmadas) | Ação |
|---|---|---|---|---|---|
| `proto_red.py` | 3.3K | active | LOW | `tests/test_proto_cli.py` (smoke `--help` PR #78); `pyproject.toml` `[tool.ruff].extend-exclude` | keep_referenced |
| `proto_colored.py` | 4.5K | active | LOW | mesmo (`tests/test_proto_cli.py` + ruff exclude) | keep_referenced |
| `render_debug.py` | 852B | back-compat wrapper | MED | `tests/test_renderers_migration.py` + `renderers/debug.py`; `docs/architecture/target_repo_architecture.md` | keep_canonical |
| `render_native.py` | 784B | back-compat wrapper | MED | `tests/test_renderers_migration.py` + `renderers/native.py`; `OVERVIEW.md` | keep_canonical |
| `render_proto_overlays.py` | 844B | back-compat wrapper | MED | `tests/test_renderers_migration.py` + `renderers/proto_overlays.py`; `docs/png_history_protocol.md` | keep_canonical |
| `render_semantic.py` | 802B | back-compat wrapper | MED | `tests/test_renderers_migration.py` + `renderers/semantic.py`; `OVERVIEW.md` | keep_canonical |
| `render_with_openings.py` | 856B | back-compat wrapper | MED | `tests/test_renderers_migration.py` + `renderers/with_openings.py`; `docs/png_history_protocol.md` | keep_canonical |
| `render_sidebyside.py` | 6.1K | active CLI | MED | `tests/test_proto_cli.py`; `OVERVIEW.md`; `pyproject.toml` ruff-exclude | keep_canonical |
| `main.py` | 5.0K | canonical CLI | HIGH | `tests/test_run_audit_v2.py` (entrypoint fixture); `tests/test_vector_consensus_rasterized_input.py` (`"main.py extract" in err`); CLAUDE.md §1.6 explicitamente RED | keep_canonical |
| `make_test_pdf.py` | 623B | active fixture builder | LOW | `docs/diagnostics/2026-05-08_cycle11b_vector_pdf_inventory.md`; gera `test_plan.pdf` | keep_referenced |
| `preprocess_walls.py` | 1.4K | historical baseline | LOW | gera `planta_74_mask.png`; `docs/diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md` lista como "archive candidate — leave for now" | keep_uncertain |
| `analyze_overpoly.py` | 14K | historical baseline | LOW | `docs/_archive/2026-04-f1-cycle/OVER-POLYGONIZATION-ANALYSIS.md` linha 220 explicitamente instrui `.venv/Scripts/python.exe analyze_overpoly.py` (reproducible script) | keep_uncertain |
| `crop_legend.py` | 377B | historical baseline | LOW | `docs/_archive/2026-04-f1-cycle/ANALYSIS.md:192` (cluster registry); 3 ledgers de hygiene anteriores | keep_uncertain |
| `peek_pdf.py` | 360B | historical baseline | LOW | `docs/_archive/2026-04-f1-cycle/ANALYSIS.md:192`; `docs/diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md:67` "debug aid" | keep_uncertain |
| `proto_runner.py` | 3.7K | historical baseline | LOW | `docs/_archive/2026-04-f1-cycle/ANALYSIS.md:188`; 3 ledgers de hygiene anteriores | keep_uncertain |
| `proto_skel.py` | 2.0K | historical baseline | LOW | mesmo (archive cluster registry + ledgers) | keep_uncertain |
| `proto_v2.py` | 2.8K | historical baseline | LOW | mesmo | keep_uncertain |

### Arquivos `.md` na raiz (5 não-canônicos + 5 canônicos)

| Arquivo | Tamanho | Categoria | Risco | Evidência | Ação |
|---|---|---|---|---|---|
| `CLAUDE.md` | — | constitution | INVIOLABLE | autoload por toda sessão | keep_canonical |
| `README.md` | — | active | INVIOLABLE | repo entry point | keep_canonical |
| `OVERVIEW.md` | — | canonical | INVIOLABLE | CI workflows, README, agents, CLAUDE.md (~35 hits) | keep_canonical |
| `AGENTS.md` | — | canonical | INVIOLABLE | CLAUDE.md §2 + agents | keep_canonical |
| `PROMPT-FELIPE.md` | 6.5K | historical baseline | LOW | citado por `docs/diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md:65` como anchor live + ledgers | keep_uncertain |
| `PROMPT-RENAN.md` | 13K | historical baseline | LOW | **`patches/README.md` linha 194: "Ver §Invariantes no PROMPT-RENAN.md"** (FUNCTIONAL ANCHOR — load-bearing); 5 menções em `docs/_archive/2026-04-f1-cycle/*` | keep_referenced |

### Arquivos não-Python na raiz (4)

| Arquivo | Tamanho | Categoria | Risco | Evidência | Ação |
|---|---|---|---|---|---|
| `Gemfile.lint` | 958B | active CI | HIGH | `.github/workflows/rubocop.yml` consome | keep_canonical |
| `.rubocop.yml` | 1.8K | active CI | HIGH | mesmo workflow | keep_canonical |
| `.mcp.json` | 207B | active config | HIGH | MCP server config | keep_canonical |
| `.env.example` | 494B | active template | HIGH | template de .env (`.env*` gitignored exceto `.env.example`) | keep_canonical |

### PDFs/PNGs na raiz (4)

| Arquivo | Tamanho | Categoria | Risco | Evidência | Ação |
|---|---|---|---|---|---|
| `planta_74.pdf` | 172K | RED canonical | INVIOLABLE | base de validação inteira (~80+ hits em testes/baseline/diagnostics) | keep_canonical |
| `planta_74_clean.pdf` | 75K | RED canonical | INVIOLABLE | `expected_model.json` + diagnostics | keep_canonical |
| `planta_74_mask.png` | 11K | RED canonical | INVIOLABLE | gerado por `preprocess_walls.py`; diagnostics | keep_canonical |
| `test_plan.pdf` | 24K | active fixture | INVIOLABLE | gerado por `make_test_pdf.py`; diagnostics | keep_canonical |

### Diretórios — status

| Diretório | Status | Notas |
|---|---|---|
| `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `sketchup_mcp.egg-info/` | gitignored | Não tracked. Limpeza local opcional via `find . -type d -name __pycache__ -exec rm -rf {} +`. **Não entra em commits**. |
| `runs/` | gitignored + §1 hard rule RED | Não tocado. 36+ subdirs locais. |
| `patches/` | §1 hard rule RED | Não tocado. `patches/archive/` HIGH risk. |
| `docs/diagnostics/2026-05-09_*fp014*` | RED FP-014 ativo | **Não auditado** — directive do user. |
| `ground_truth/` | RED canonical | Não tocado. |
| `.ai_bridge/` | RED operacional | Não tocado. |
| `cockpit/`, `renderers/`, `scripts/smoke/` | RED por user directive | Não tocado. |
| `tools/apply_overrides.py`, `tools/propose_skp_actions.py` | RED por user directive | Não tocado. |
| `docs/_archive/2026-04-f1-cycle/` | archive convention já em uso | Pattern correto pra futuros archives — **note: underscore prefix `_archive`**, não `archive`. |
| `debug/`, `vendor/`, `agents/`, `references/`, `reports/` | preservados | nada novo desde 2026-05-08. |

---

## Removed

Nenhum arquivo removido neste ciclo.

## Archived

Nenhum arquivo arquivado neste ciclo.

## Preserved (com rationale, agrupado)

### Active back-compat (5 wrappers + 2 protos + render_sidebyside)
- `render_*.py` (5): cada um delega para `renderers/<sub>.py` com DeprecationWarning. `tests/test_renderers_migration.py` declara explicitamente: "until the wrappers are removed in a future release". Trigger não disparado.
- `proto_red.py` / `proto_colored.py`: refatorados com argparse em PR #78 (`refactor/proto-cli-args-cleanup`). `tests/test_proto_cli.py` é o gate de back-compat.
- `render_sidebyside.py`: idem; pyproject ruff-exclude documenta como tech debt CLI.

### Active CLI / fixture builders (3)
- `main.py`: §1.6 hard rule explicitamente lista como high-risk entrypoint. Não toca.
- `make_test_pdf.py`: gera `test_plan.pdf`. Documentado em `docs/diagnostics/2026-05-08_cycle11b_vector_pdf_inventory.md`.
- `preprocess_walls.py`: gera `planta_74_mask.png`. Cycle 2 ledger flagou como "archive candidate — leave for now".

### Historical baseline — keep_uncertain (6 + 2)
**6 scripts:** `analyze_overpoly.py`, `crop_legend.py`, `peek_pdf.py`, `proto_runner.py`, `proto_skel.py`, `proto_v2.py`.

Mudança de evidência desde Cycle 1 (PR #73):
- ❌ Não mais em `docs/ROADMAP.md` (Cycle 1 citou como ref)
- ❌ Não mais em `docs/repo_hardening_plan.md` (Cycle 1 citou como ref)
- ❌ Não mais em `pyproject.toml` (Cycle 1 citou como ref) — exceto `proto_red`/`proto_colored`/`render_sidebyside` ainda em ruff-exclude
- ✓ Permanecem em `docs/_archive/2026-04-f1-cycle/ANALYSIS.md` (cluster registry — frozen)
- ✓ Permanecem em `docs/_archive/2026-04-f1-cycle/OVER-POLYGONIZATION-ANALYSIS.md` linha 220 explicita instrução `analyze_overpoly.py` como "reproducible script"
- ✓ Permanecem nos 3 ledgers anteriores (hygiene_2026-05-06.md, post_wave_state_2026-05-08.md, post_cycle12d_hygiene_audit.md)

Decisão: preservar pelas mesmas razões de Cycle 2 — "the cost of keeping a ~10KB orphan script is much lower than the cost of breaking a manual diagnostic reflex Felipe has built". `OVER-POLYGONIZATION-ANALYSIS.md:220` é um `_archive/` doc INTOCÁVEL (§1 hard rule) — se eu mover `analyze_overpoly.py`, o link nesse archive fica falso.

**2 prompts:** `PROMPT-FELIPE.md`, `PROMPT-RENAN.md`.
- `PROMPT-RENAN.md` é REFERENCED ATIVO via `patches/README.md:194`. Não move.
- `PROMPT-FELIPE.md`: ledger Cycle 2 (`post_cycle12d_hygiene_audit.md:65`) lista como "live anchor" referenciado em `patches/README.md`. Mantém o par junto.

### Diagnostics FP-014 (2026-05-09)
- ❌ não auditado por user directive.

---

## Reference searches performed

```
git grep -l "proto_red|proto_colored"  →  tests/test_proto_cli.py
git grep -l "render_<all>"             →  tests/test_proto_cli.py + test_renderers_migration.py
git grep -l "analyze_overpoly|crop_legend|peek_pdf|proto_runner|proto_skel|proto_v2"
                                       →  5 docs (3 ledgers + 2 archive); 0 tests, 0 imports, 0 pyproject, 0 CI, 0 ROADMAP, 0 hardening_plan
git grep -l "PROMPT-FELIPE|PROMPT-RENAN"
                                       →  patches/README.md:194 (FUNCTIONAL anchor, PROMPT-RENAN); 6 docs (ledgers + archives); 0 .ai_bridge/
git grep -l "main\.py"                 →  tests/test_run_audit_v2.py + test_vector_consensus_rasterized_input.py
git grep -l "make_test_pdf|preprocess_walls"
                                       →  ledgers only; mas geram artefatos canonical
git grep -l "Gemfile.lint|\.rubocop\.yml"
                                       →  .github/workflows/rubocop.yml (CI), .ai_bridge/HANDOFF.md, .ai_bridge/pr_bodies/PR_BODY_rubocop_ci.md
imports python (import|from <stem>)    →  0 hits para os 6 órfãos nominais
```

Total: ~150 reference checks em ~30 candidatos. **Resultado: 0 verdadeiros órfãos sem nenhuma referência.** Refs anteriormente em ROADMAP/repo_hardening_plan/pyproject sumiram desde Cycle 1, mas refs em `_archive/` (frozen, intocáveis por §1) preservam o link e justificam preservação.

---

## Validations executed

| Comando | Resultado esperado | Resultado real |
|---|---|---|
| `git status` | clean apart from new doc | ✓ clean |
| `git diff --stat origin/develop` | 1 file new | ✓ 1 file |
| `pytest tests/test_renderers_migration.py tests/test_proto_cli.py tests/test_cli.py -q` | green (back-compat anchors) | ✓ green |
| `pytest tests/test_smoke_gate_*.py -q` | green (smoke gates) | ✓ green |
| `pytest tests/test_cockpit_*.py -q` | green (cockpit slices) | ✓ green |
| `pytest tests/test_planta_74_truth_gate.py tests/test_micro_truth_gate.py -q` | green (truth gates) | ✓ green |
| 17 raster failures (CLAUDE.md §10) | unchanged | ✓ unchanged |
| `ruff check docs/ops/repo_hygiene_audit_2026-05-10.md` | N/A (ruff ignora .md) | ✓ no-op |

---

## What this cycle did NOT do

- ❌ Não removeu nenhum arquivo tracked.
- ❌ Não arquivou nada (sem `git mv` / sem `mv` para `docs/_archive/`).
- ❌ Não tocou em código (zero `.py` / `.rb` / `.json` / `.yml`).
- ❌ Não tocou em FP-014, `runs/`, `patches/`, `ground_truth/`, `.ai_bridge/`, `cockpit/`, `renderers/`, `scripts/smoke/`, `tools/apply_overrides.py`, `tools/propose_skp_actions.py`.
- ❌ Não modificou `docs/_archive/` (§1 hard rule).
- ❌ Não misturou cleanup com mudança algorítmica (§15.6).
- ❌ Não alterou thresholds, baselines, schema, ou exporter (§1 hard rules).
- ❌ Não rodou `ruff --fix` em escopo amplo (§1.7-9).
- ❌ Não rodou autoformatter (§1.8).

---

## Next candidates (deferred — triggers explícitos)

| Candidato | Trigger pra retirada | Plano de ação quando trigger disparar |
|---|---|---|
| `proto_*.py` legacy (runner/skel/v2) + `peek_pdf.py` + `crop_legend.py` + `analyze_overpoly.py` | (a) CLAUDE.md §10 raster pipeline officially retired OR (b) user confirma "Felipe não usa scripts manualmente" | PR `chore: archive obsolete proto_* scripts` — `git mv` para `docs/_archive/scripts_2026_NN_NN/` + atualizar refs em `OVER-POLYGONIZATION-ANALYSIS.md`? **NOTA:** modificar `_archive/` é §1 hard rule. Alternativa: deixar refs broken no archive (frozen doc representa estado de 2026-04). |
| `render_*.py` back-compat wrappers (5) | "Future release" comentado em `tests/test_renderers_migration.py` for explicitamente declarado fechado | PR `chore: drop legacy render_*.py wrappers` — `git rm` + `git rm tests/test_renderers_migration.py` |
| `preprocess_walls.py` | Raster pipeline officially retired | `git mv` para `_archive/` ou `tools/legacy/`; preservar artefato `planta_74_mask.png` |
| `make_test_pdf.py` | Não há trigger — fixture builder ativo | Mantém |
| `PROMPT-FELIPE.md` / `PROMPT-RENAN.md` | `patches/README.md:194` deixa de citar PROMPT-RENAN como autoridade de invariantes | `git mv PROMPT-*.md docs/_archive/onboarding_2026/` + atualizar `patches/README.md` simultâneamente |
| `runs/` (36+ subdirs) | Amendment a §1 hard-rule autorizando archive | Decisão humana explícita |

---

## Pattern observed (3 cycles convergem)

3 audits consecutivos chegaram à mesma conclusão. Sinaliza:

- Há uma **decisão deferred crônica** sobre o cluster proto/render legacy. Não bloqueia, mas indica que o cleanup desses arquivos requer **decisão humana sobre raster retirement**.
- O CUSTO de manter ~30KB de scripts órfãos é baixo. O CUSTO de quebrar referências em `_archive/` (que é frozen por §1) ou em `patches/README.md` (que é load-bearing) é potencialmente alto.
- **Recomendação concreta:** quando CLAUDE.md §10 for atualizado para sinalizar "raster retired" — abrir PR coordenada `chore: archive obsolete raster-era scripts`, simultaneamente:
  1. `git mv` os 6 scripts pra `docs/_archive/scripts_2026_NN_NN/`
  2. update `patches/README.md:194` se PROMPT-RENAN também for arquivado
  3. update `tests/test_renderers_migration.py` com nova path OR remove
  4. NÃO modificar `docs/_archive/2026-04-f1-cycle/*` (frozen archive — link broken é OK)

---

## Summary

- 0 tracked deletions. 0 archives. 1 doc adicionado (este, ≈300 linhas).
- Working tree clean. Suite estável.
- 28 candidatos inventariados. 12 keep_canonical, 4 keep_referenced, 8 keep_uncertain, 0 delete_safe, 0 archive_only neste ciclo, 0 needs_human_decision pra ação imediata.
- Próximo ciclo: aguardar trigger explícito (raster retirement em CLAUDE.md §10 OR user confirma manual obsolescence).
- Cadence: ~7-14 dias OR quando trigger disparar.
