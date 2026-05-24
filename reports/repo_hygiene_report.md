# Repo Hygiene Report — 2026-05-24

> **Status:** Active (per-cycle inventory; supersedes
> `docs/ops/repo_hygiene_audit_2026-05-10.md` only as the latest
> snapshot — both are kept).
> **Type:** Inventory + classification of every tracked `.md` and
> root-level `.py` per `docs/REPO_HYGIENE.md` §1 five-category scheme.
> **Branch:** `chore/repo-governance-anti-forgetting` (from
> `origin/develop @ 14212ea`).
> **Companion docs:** [`../docs/REPO_HYGIENE.md`](../docs/REPO_HYGIENE.md)
> (policy), [`../docs/PROJECT_STATE.md`](../docs/PROJECT_STATE.md)
> (state snapshot).

This report is **audit-only** for this cycle. Zero files removed,
zero archived, zero source code touched (per user's scope choice on
this run). It exists to:

1. Give any new agent/human a one-page map of every `.md` in the
   repo, classified into the five
   [`REPO_HYGIENE.md`](../docs/REPO_HYGIENE.md) categories.
2. Document the references that keep each file alive (so a future
   archive/delete pass has the evidence it needs).
3. Flag the trigger conditions under which a hygiene cycle 4 would
   become useful.

---

## TL;DR

| Bucket | Count |
|---|---|
| Total `.md` files (tracked, non-vendor) | 125 |
| Canonical | 16 |
| Active | 73 |
| Archived (`docs/_archive/`) | 17 |
| Generated / report-style | 13 |
| Delete candidates | 0 |
| Status: header coverage on canonical-required docs | 5/5 |

- **Hard FAILs in `project_state_check.py`:** 0
- **Soft WARNs** (items on `feature/window-aperture-semantics` not yet
  on develop): 9 (4 tests + 2 fixtures + 3 reference assets)

No files moved or deleted in this report. See §6 for the trigger
conditions under which a follow-up cycle would.

---

## 1. Root-level files

### Root `.md` (6)

| File | Category | Status | Why keep / Evidence |
|---|---|---|---|
| `CLAUDE.md` | Canonical | Inviolable | Operational constitution; autoloaded every session. |
| `README.md` | Canonical | Inviolable | Repo entry point; cross-linked from `OVERVIEW.md`, `CLAUDE.md`, CI. |
| `OVERVIEW.md` | Canonical | Inviolable | Onboarding + architecture map; ~35 cross-references. |
| `AGENTS.md` | Canonical | Inviolable | Pipeline invariants source; CLAUDE.md §2 cites. |
| `PROMPT-FELIPE.md` | Active | Historical anchor (load-bearing) | Cited by `docs/diagnostics/2026-05-08_post_cycle12d_hygiene_audit.md:65`; ledger reference. |
| `PROMPT-RENAN.md` | Active | Historical anchor (load-bearing) | `patches/README.md:194` cites `§Invariantes no PROMPT-RENAN.md` as functional anchor. 5 mentions in `docs/_archive/2026-04-f1-cycle/*`. |

### Root `.py` (17) — from 2026-05-10 audit, re-validated 2026-05-24

| File | Category | Evidence | Action |
|---|---|---|---|
| `main.py` | Canonical CLI | CLAUDE.md §1.6 RED + `tests/test_run_audit_v2.py` + `tests/test_vector_consensus_rasterized_input.py` | keep |
| `proto_red.py` | Active | `tests/test_proto_cli.py` smoke; `pyproject.toml` ruff-exclude | keep |
| `proto_colored.py` | Active | same | keep |
| `render_debug.py` | Active (back-compat wrapper) | `tests/test_renderers_migration.py` + `renderers/debug.py`; `docs/architecture/target_repo_architecture.md` | keep |
| `render_native.py` | Active (back-compat wrapper) | same pattern; `OVERVIEW.md` ref | keep |
| `render_proto_overlays.py` | Active (back-compat wrapper) | `tests/test_renderers_migration.py` + `docs/png_history_protocol.md` | keep |
| `render_semantic.py` | Active (back-compat wrapper) | same; `OVERVIEW.md` | keep |
| `render_with_openings.py` | Active (back-compat wrapper) | same; `docs/png_history_protocol.md` | keep |
| `render_sidebyside.py` | Active CLI | `tests/test_proto_cli.py`; `OVERVIEW.md` | keep |
| `make_test_pdf.py` | Active fixture builder | `docs/diagnostics/2026-05-08_cycle11b_vector_pdf_inventory.md`; generates `test_plan.pdf` | keep |
| `preprocess_walls.py` | Historical baseline | Generates `planta_74_mask.png`; flagged "archive candidate — leave for now" in prior audits | keep (uncertain) |
| `analyze_overpoly.py` | Historical baseline | `docs/_archive/2026-04-f1-cycle/OVER-POLYGONIZATION-ANALYSIS.md:220` explicit reproducible-script instruction | keep |
| `crop_legend.py` | Historical baseline | `docs/_archive/2026-04-f1-cycle/ANALYSIS.md:192` cluster registry; 3 prior ledgers preserve | keep (uncertain) |
| `peek_pdf.py` | Historical baseline | `docs/_archive/2026-04-f1-cycle/ANALYSIS.md:192`; "debug aid" in prior audits | keep (uncertain) |
| `proto_runner.py` | Historical baseline | `docs/_archive/2026-04-f1-cycle/ANALYSIS.md:188`; 3 prior ledgers | keep (uncertain) |
| `proto_skel.py` | Historical baseline | same cluster registry | keep (uncertain) |
| `proto_v2.py` | Historical baseline | same | keep (uncertain) |

### Root other files (8)

| File | Category | Evidence |
|---|---|---|
| `Gemfile.lint` | Canonical CI | `.github/workflows/rubocop.yml` consumes |
| `.rubocop.yml` | Canonical CI | same |
| `.mcp.json` | Canonical config | MCP server config |
| `.env.example` | Canonical config template | `.env*` gitignored except this |
| `.gitignore` | Canonical config | repo-wide |
| `pyproject.toml` | Canonical config | Python package definition; all CI workflows |
| `requirements.txt` | Active | duplicate of `pyproject.toml` for non-editable installs |
| `planta_74.pdf` / `planta_74_clean.pdf` / `planta_74_mask.png` / `test_plan.pdf` | Canonical baseline data | RED canonical; ~80+ references across tests/baselines/diagnostics |

---

## 2. Canonical docs (16)

These are the load-bearing "single source of truth" docs. Removing
any one would break the project (or an explicit cross-reference would
404). All carry `Status: Canonical` (the ones new in this cycle do
explicitly; the older ones implicitly by virtue of `CLAUDE.md` §1 and
references throughout).

| Path | Role |
|---|---|
| `CLAUDE.md` | Operational constitution. |
| `README.md` | Repo entry point. |
| `OVERVIEW.md` | Architecture + onboarding. |
| `AGENTS.md` | Pipeline invariants. |
| `docs/PROJECT_STATE.md` ⭐ NEW | Single source of truth on current state. |
| `docs/HANDOFF.md` ⭐ NEW | Stable canonical onboarding. |
| `docs/REPO_HYGIENE.md` ⭐ NEW | Five-category file scheme + status policy. |
| `docs/GATES.md` ⭐ NEW | Validation gates catalogue. |
| `docs/ANTI_FORGETTING.md` ⭐ NEW | 10 permanent rules with reasoning. |
| `docs/git_workflow.md` | Git flow detail referenced by CLAUDE.md §0. |
| `docs/adr/README.md` | ADR index + template. |
| `docs/adr/ADR-001-validation-cockpit-mutation-surface.md` | Cockpit mutation contract. |
| `docs/adr/ADR-002-room-polygon-overrides.md` | room_polygon_override schema. |
| `docs/adr/ADR-003-plan-shell-exporter.md` | plan-shell exporter contract. |
| `docs/adr/ADR-004-mutation-and-regression-testing-policy.md` | Mutation testing policy. |
| `docs/SCHEMA-V2.md` | Observed model schema 2.x. |
| `docs/specs/quadrado_demo_spec.md` | Quadrado canonical spec. |

Note: `docs/adr/ADR-007-window-aperture-3d-carve.md` exists ONLY on
`feature/window-aperture-semantics` and is not yet on develop. When
that branch merges, this file should be added to the table above.

---

## 3. Active docs (73)

Working surface that is referenced by canonical docs, code, tests, or
CI. Subdivided by area.

### Operational scaffolding (10 — `.ai_bridge/`)

`.ai_bridge/CURRENT_STATE.md`, `HANDOFF.md`, `TODO_NEXT.md`,
`PROJECT_CONTEXT.md`, `DECISIONS.md`, `LESSONS.md`, `GPT_REQUESTS.md`,
`GPT_RESPONSES.md`, `QUESTIONS_FOR_NEXT_AGENT.md`, `README.md`.

Per-session bridge between agents. `CURRENT_STATE.md` is overwrite,
`HANDOFF.md` is append-on-top. Refreshed this cycle with the
2026-05-24 entry.

### Agent specs (15)

- `.claude/agents/*.md` (9): coordinator, ci-guardian, docs-maintainer,
  geometry-specialist, openings-specialist, performance-specialist,
  repo-auditor, sketchup-specialist, validator-specialist.
- `docs/agents/*.md` (9): full specifications mirrored to docs.
- `agents/auditor/README.md` + `agents/auditor/PROMPT.md`: legacy
  auditor entry — referenced by CLAUDE.md §7.

### Slash commands (6 — `.claude/commands/`)

`afk-maintain.md`, `improve-agents.md`, `perf-baseline.md`,
`prepare-pr.md`, `repo-audit.md`, `validate-skp.md`.

### Learning logs (9 — `docs/learning/`)

- `lessons_learned.md` (LL-NNN positive rules)
- `failure_patterns.md` (FP-NNN anti-patterns)
- `decision_log.md` (DL-NNN architectural decisions)
- `validation_matrix.md`
- `prompt_improvements.md` + `prompt_quality_rubric.md`
- `agent_improvements.md`
- `human_openings_truth_protocol.md`
- `v5_opening_kind_enrichment.md`
- `planta_74_clean_compatibility.md` (per-PDF compatibility note)

### Performance docs (5 — `docs/performance/`)

`cache_design.md`, `cache_keys.md`, `cache_rollout_plan.md`,
`current_perf_baseline.md`, `skip_unchanged_skp.md`. Referenced by
CLAUDE.md §3 (skip-unchanged) + `operational_roadmap.md`.

### Protocols (2 — `docs/protocols/`)

`human_soft_barriers_protocol.md`, `visual_fidelity_gate_protocol.md`.

### Validation (4 — `docs/validation/`)

`sketchup_2026_validation.md`, `sketchup_smoke_workflow.md`,
`skp_fidelity_2026-05-04.md`, `window_detector.md`.

### Tour (3 — `docs/tour/`)

`matterport_capture_failure_74m2.md`,
`matterport_photo_inventory_74m2.md`,
`matterport_visual_findings_74m2.md`.

### Diagnostics (6 — `docs/diagnostics/`)

Per-incident evidence. Each file is tied to an FP or a specific
investigation:

- `2026-05-09_skp_visual_failure_fp014.md`
- `2026-05-09_skp_visual_failure_fp014_gpt_validation.md`
- `2026-05-11_wall_audit/planta_74_audit.md`
- `2026-05-11_wall_candidates_audit.md`
- `2026-05-23_failure_pattern_id_audit.md`
- `2026-05-23_stack_integrity_report.md`

### Top-level docs (10)

`docs/SCHEMA-COHERENCE-REPORT.md`, `docs/SOLUTION.md`,
`docs/architecture/target_repo_architecture.md`,
`docs/ground_truth_references.md`, `docs/ground_truth_v1.md`,
`docs/grounding/constants_provenance.md`,
`docs/operational_roadmap.md`, `docs/ops/repo_hygiene_audit_2026-05-10.md`,
`docs/png_history_protocol.md`, `docs/validation_cockpit.md`,
`docs/validator_protocol.md`.

### Sub-area READMEs (6)

`patches/README.md`, `patches/archive/README.md`,
`scripts/benchmark/README.md`, `scripts/oracle/README.md`,
`tools/dashboard/README.md`, `fixtures/planta_74/README.md`.

### Companion to canonical workflows (3 — `fixtures/planta_74/`)

`HUMAN_WALLS_README.md` — companion to human-openings + human-walls
protocols. Active.

---

## 4. Archived docs (17 — `docs/_archive/`)

The archive convention uses underscore-prefix (`_archive`) so it
sorts to the top of any directory listing. Two cycle folders:

### `docs/_archive/2026-04-f1-cycle/` (15)

`ANALYSIS-OVERVIEW.md`, `ANALYSIS.md`, `CAUSA-RAIZ.md`,
`CROSS-PDF-VALIDATION.md`, `DOCS-CONSOLIDATION-TODO.md`,
`OPENINGS-EXPLOSION-AUDIT.md`, `OPENINGS-REFINEMENT.md`,
`ORPHAN-RESIDUAL-AUDIT.md`, `OVER-POLYGONIZATION-ANALYSIS.md`,
`PROMPT-NEXT-CLAUDE.md`, `README.md`, `SOLUTION-FINAL.md`,
`SVG-INGEST-INTEGRATION.md`, `SVG-MAIN-PLAN-ISOLATION.md`,
`VALIDATION-F1-REPORT.md`.

All explicitly referenced by `docs/_archive/2026-04-f1-cycle/README.md`
as the index. Several scripts (`analyze_overpoly.py`, `crop_legend.py`,
`peek_pdf.py`, `proto_*.py`) document themselves as belonging to this
cycle's investigations.

### `docs/_archive/2026-05-cleanup/` (2)

- `operator_acknowledgment_2026-05-13.md` — explicitly superseded by
  `docs/protocols/visual_fidelity_gate_protocol.md` (CLAUDE.md §10
  cites the supersession).
- `ROADMAP.md` — historical roadmap; current pendencies are in
  `.ai_bridge/TODO_NEXT.md`.

---

## 5. Generated / report-style docs (13)

These are outputs of pipelines or curated reports. They are
canonical artefacts (tracked), but the underlying data is
reproducible from canonical inputs.

| File | Producer / source | Reproducibility |
|---|---|---|
| `docs/diagnostics/2026-05-09_skp_visual_failure_fp014_*.md` (2) | Manual diagnostic of FP-014 | Tied to FP-014 evidence; preserve. |
| `docs/ops/repo_hygiene_audit_2026-05-10.md` | Manual audit | Per-cycle snapshot; superseded only as "latest" by this report. |
| `reports/perf_baseline.example.json` | `scripts/benchmark/bench_pipeline.py` | Re-runnable. |
| `fixtures/planta_74/SKP_FINAL_REPORT.md` | Manual report | Tied to commit `7fbd531`. |
| `fixtures/planta_74/door_glyph_summary.md` | `tools/detect_door_glyphs.py` + `tools/render_door_glyph_overlay.py` | Reproducible. |
| `fixtures/planta_74/notes_after_human_walls.md` | `tools/apply_human_walls.py` | Reproducible. |
| `fixtures/planta_74/skp_final_notes.md` | `tools/skp_from_consensus.py` | Reproducible. |
| `fixtures/planta_74/visual_evidence/mismatches_list.md` | `tools/produce_visual_evidence.py` | Reproducible. |
| `runs/png_history/manifest.jsonl` | `tools/png_history.py` | Gitignored; reproducible. |

---

## 6. Delete candidates

**None this cycle.** Per `docs/ops/repo_hygiene_audit_2026-05-10.md`
§"Triggers" + `docs/REPO_HYGIENE.md` §3, no candidate has hit the
"zero references" threshold. The user's 2026-05-24 prompt is the
trigger for governance work, not for deletion.

### Trigger conditions for a follow-up archival cycle

A follow-up `chore: archive stale docs` PR becomes useful when ANY of
these fire:

| Trigger | Status as of 2026-05-24 | Effect |
|---|---|---|
| Raster pipeline officially retired (CLAUDE.md §10 stops marking raster as OUTDATED-but-kept). | NOT fired | Would unlock `proto_*.py`, `analyze_overpoly.py`, `crop_legend.py`, `peek_pdf.py`, `preprocess_walls.py` for archive. |
| `patches/README.md:194` stops citing `PROMPT-RENAN.md`. | NOT fired | Would unlock `PROMPT-RENAN.md` for archive. |
| `tests/test_renderers_migration.py` future-release gate explicitly closed. | NOT fired | Would unlock 5 `render_*.py` back-compat wrappers. |
| `runs/` archival decision (amends §1 hard rule). | NOT fired | Would unlock historical `runs/` subdirs. |
| `feature/window-aperture-semantics` merges + soft items become hard requirements. | PENDING (3 commits ahead) | Would promote quadrado fixtures + tests + assets from SOFT to CANONICAL in `project_state_check.py`. |

---

## 7. .gitignore review

Current `.gitignore` is comprehensive. No additions needed in this
report. Items covered:

- Python build / venv / cache (`.venv`, `__pycache__`, `*.egg-info`,
  `.pytest_cache`, `.ruff_cache`, `.mypy_cache`).
- Runtime outputs (`/runs/`, `/out/`, `/review/`).
- Local-only files (`*.log`, `.coverage`, `htmlcov/`, `dist/`,
  `build/`).
- IDE / OS (`.idea/`, `.vscode/`, `.DS_Store`, `Thumbs.db`).
- `.env*` except `.env.example`.
- `.claude/*` except the team-shared subdirs.
- `vendor/CubiCasa5k/weights/*.pkl|*.pth` + `repo/`.

Potential future additions when their trigger fires:
- `runs/<id>/_cockpit_cache/**` (currently caught by `/runs/`; if
  cockpit cache moves out, would need its own line).
- Per-cycle `runs/png_history/manifest.jsonl` (caught by `/runs/`).

---

## 8. Status: header coverage

The 5 new canonical docs all carry the `Status:` header per the
policy in [`../docs/REPO_HYGIENE.md`](../docs/REPO_HYGIENE.md) §2:

- `docs/PROJECT_STATE.md` — `Status: Canonical`
- `docs/HANDOFF.md` — `Status: Canonical`
- `docs/REPO_HYGIENE.md` — `Status: Canonical`
- `docs/GATES.md` — `Status: Canonical`
- `docs/ANTI_FORGETTING.md` — `Status: Canonical`

Validated by `tests/test_project_state_check.py::test_canonical_docs_carry_status_header`.

Older canonical docs (`CLAUDE.md`, `README.md`, `OVERVIEW.md`,
`AGENTS.md`, ADRs, etc.) do NOT yet carry the header. **Policy is
opt-in**: per `REPO_HYGIENE.md` §2, headers are added when the file is
touched for any reason, not via bulk rewrite.

---

## 9. Cross-reference searches performed

To validate "preserve by default", these searches were run during
this report (re-confirms 2026-05-10 audit + adds the 2026-05-24
fresh deltas):

```text
proto_runner|proto_red|proto_skel|proto_colored|proto_v2  → 11 hits (tests + 2026-04-f1-cycle archive + 2026-05-cleanup ROADMAP + this report's predecessor)
make_test_pdf|peek_pdf|crop_legend|preprocess_walls|analyze_overpoly  → same cluster
docs/SOLUTION.md  → 8 hits (tools/, OVERVIEW.md, .ai_bridge/PROJECT_CONTEXT.md)
SCHEMA-COHERENCE-REPORT|SCHEMA-V2  → 9 hits (CLAUDE.md, tools/, docs/, OVERVIEW.md, .ai_bridge/)
operational_roadmap|planta_74_clean_compatibility|matterport_capture_failure  → 7 hits
target_repo_architecture|repo_hardening_plan  → 21 hits
```

No file fell below the "1 active reference" floor.

---

## 10. Validations executed this cycle

- `python scripts/project_state_check.py` → exit 0 (30 PASS, 0 FAIL, 9 WARN).
- `pytest tests/test_project_state_check.py -v` → 5/5 PASS.
- `ruff check scripts/project_state_check.py tests/test_project_state_check.py` → clean.
- Manual git log of `feature/window-aperture-semantics` vs
  `origin/develop` → 3 commits ahead (`7e56dc7`, `ebdac1a`, `8799466`).

---

## 11. Risks if a future cycle proceeds to archive

Before archiving any file flagged here as "keep (uncertain)" or
"historical baseline", validate:

1. The trigger condition above has fired.
2. A grep of the file basename across `tests/`, `docs/`,
   `.github/workflows/`, `tools/`, `scripts/`, `patches/` returns
   zero live references (archive ledgers don't count).
3. The intended destination is `docs/_archive/<cycle-name>/` with a
   companion `README.md` index entry.
4. The PR title is `chore: archive ...` and contains no algorithmic
   change.
5. `python scripts/project_state_check.py` still passes after the move.

Mixing archive with algorithmic changes is banned by
[`../docs/REPO_HYGIENE.md`](../docs/REPO_HYGIENE.md) §3 and
[`../CLAUDE.md`](../CLAUDE.md) §15.

---

## 12. Next-cycle handoff

This report supersedes the "latest" pointer in
`docs/ops/repo_hygiene_audit_2026-05-10.md` only as the freshest
inventory. Both documents remain tracked. The next hygiene cycle
should:

1. Read this report's §6 trigger table.
2. Re-run `python scripts/project_state_check.py` and grep counts
   above.
3. Diff this report against the file list as of that cycle's HEAD.
4. Ship as `reports/repo_hygiene_report_<YYYY-MM-DD>.md` (one file
   per cycle) OR overwrite this one with explicit reference to the
   prior version in git history.

---

## Update log

| Date | Commit | What changed |
|---|---|---|
| 2026-05-24 | (this commit) | Initial inventory + classification. 125 `.md` + 17 root `.py` classified into 5 categories. 0 deletions / 0 archives / 0 source touched. |
