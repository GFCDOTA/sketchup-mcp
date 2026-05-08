# Post-Wave State + Hygiene Scan — 2026-05-08

> Operational snapshot after the 9-PR wave merge + autonomy
> protocol installation. Companion to `.ai_bridge/HANDOFF.md` (live)
> and `.ai_bridge/GPT_REQUESTS.md` (audit trail).

## Wave summary

9 PRs from yesterday's queue + 1 follow-up = 10 PRs merged on
`develop`:

| PR  | Title (truncated) | Merge SHA |
|-----|-------------------|-----------|
| #52 | docs(claude): §17 Non-Stop Autonomy Rule | `148db2b` |
| #53 | docs(diagnostic): SUITE 01 polygon leakage FP-012 | `5840532` |
| #54 | docs(readme,overview): Stage 1.5/1.6 + Fidelity Engine v1 | `b4d3ab4` |
| #55 | ci(rubocop): Ruby lint workflow + 12 baseline Lint fixes | `0dd2ecd` |
| #56 | ci(quality-gates): strict CI workflow + Cycle 13 hashFiles guard | `fbe7d45` |
| #57 | feat(rooms-from-seeds): FP-012 spike --use-concave-hull (default OFF) | `3fcbbf6` |
| #59 | feat(ground-truth): Cycle 7 — planta_74_micro 1→4 rooms | `ceb2702` |
| #60 | docs(ai-bridge): persistent agent communication scaffolding | `31ef3de` |
| #58 | feat(ground-truth): v1 schema + fidelity engine (advisory mode) | `07fd499` |
| #61 | docs(ai_bridge): refresh state post-wave + autonomy protocol | `05ba96d` |

**develop @ `05ba96d`** — 4 CI workflows green; 85/85 tests pass.

## CI status

| Workflow | Status on develop | Role |
|---|---|---|
| `ci.yml` | ✅ green | unit tests + ruff (informational) + smoke harness cheap gates |
| `skp_fidelity_gate.yml` | ✅ green | SKP fidelity invariants on PR diff |
| `rubocop.yml` | ✅ green | Ruby Lint on `tools/*.rb` (post-#55 baseline clean) |
| `quality_gates.yml` | ✅ green | Plan Truth + Coherence-strict + Micro-strict + Fidelity-advisory |

**Fidelity step is advisory** (`continue-on-error: true`) until
Cycle 8b promote. Report still emitted as artifact for human inspection.

## Hygiene scan findings

Per CLAUDE.md §15 hygiene protocol — scan, classify, never delete blindly.

### Scope scanned

- root-level `.md` (6 files)
- root-level `.py` (12 files: 5 `proto_*` + 7 others)
- `docs/_archive/` already exists (`2026-04-f1-cycle/`)
- `runs/` (gitignored — out of scope)

### Classification

| File | Class | Notes |
|---|---|---|
| `AGENTS.md` | active | invariants spec referenced from CLAUDE.md and OVERVIEW |
| `CLAUDE.md` | active | constitution |
| `OVERVIEW.md` | active | onboarding doc |
| `PROMPT-FELIPE.md` / `PROMPT-RENAN.md` | unknown / preserve | personalized handoff prompts |
| `README.md` | active | repo entry point |
| `main.py` | active | CLI entry; in `[project.scripts]` |
| `analyze_overpoly.py` | unknown / preserve | one-off analysis script; no imports found |
| `crop_legend.py` | unknown / preserve | sibling of `proto_*` cluster |
| `make_test_pdf.py` | unknown / preserve | test PDF generator; possibly used historically |
| `peek_pdf.py` | unknown / preserve | PDF inspector; useful when debugging |
| `preprocess_walls.py` | unknown / preserve | Hough preprocess; pre-vector-pipeline era |
| `proto_colored.py` | dívida técnica documented | listed in `pyproject.toml` `[tool.ruff].extend-exclude` with note "tech debt — hardcoded local paths (C:/Users/felip_local/...)" |
| `proto_red.py` | dívida técnica documented | same |
| `proto_runner.py` | unknown / preserve | sibling; not in pyproject exclude |
| `proto_skel.py` | unknown / preserve | sibling; not in pyproject exclude |
| `proto_v2.py` | unknown / preserve | sibling; not in pyproject exclude |
| `render_*.py` (7 files) | mixed | `render_debug.py` referenced in `docs/architecture/target_repo_architecture.md`; `render_sidebyside.py` listed in pyproject ruff-exclude as tech debt; others unverified |

### Search performed

- `import <name>` and `from <name>` across all `*.py`, excluding `.venv/`
- references in `*.md`
- `.github/workflows/` content scan
- `pyproject.toml` `[tool.ruff].extend-exclude` cross-check

### Recommendation

**No archive action this PR.** All candidate files either:
- have at least one indirect reference (pyproject ruff config, docs);
- are small (< 100 LOC each) and cheap to keep;
- appear in the documented "tech debt — will be turned into CLI args"
  category in `pyproject.toml`.

A real archive cycle would need:
1. Felipe to confirm which `proto_*` / `render_*` are dead
2. coordinate with `docs/repo_hardening_plan.md` cleanup
3. update pyproject ruff-exclude entries

That's a YELLOW operation requiring human input — defer.

## LLM consultation: Cycle 8b strategy

Per the new autonomy protocol, `planta-assistant:latest` (Ollama
localhost:11434, fallback for the offline ChatGPT desktop bridge)
was queried on the Cycle 8b ratio + PR-strategy decision. Full
audit trail in:

- `.ai_bridge/GPT_REQUESTS.md` (newest entry)
- `.ai_bridge/GPT_RESPONSES.md` (newest entry)

**LLM recommendation:** ratio=0.30 + single coordinated PR.

**Claude caveat:** ratio=0.30 pushes COZINHA / A.S. outside their
current GT v1 ranges. The LLM's recommendation implicitly requires
GT recalibration as part of the same PR. ratio=0.55 is less
disruptive but less correct architecturally. Cycle 8b stays
**RED-blocked** in the operational protocol — explicit unblock by
Felipe required before proceeding.

## Next steps (RED-blocked, awaiting Felipe input)

1. Cycle 8b authorize: which ratio (0.30 vs 0.55), single PR vs split,
   GT-recalibration scope.
2. Stage 1.6 unblock (Cycle 6 autorun inspector + the orphan
   `feature/smoke-promotes-inspector-v2-gate` branch).
3. Multi-PDF corpus: Felipe needs to provide 3+ additional planta
   PDFs to widen the test surface beyond `planta_74`.

## What this PR is

Documentation only. Adds:
- `docs/ops/post_wave_state_2026-05-08.md` (this file)
- `.ai_bridge/GPT_REQUESTS.md` new entry (Cycle 8b consult question)
- `.ai_bridge/GPT_RESPONSES.md` new entry (LLM answer + Claude caveat)

No code, no tests, no schema, no thresholds, no Ruby/SU. Pure
ops snapshot + audit trail.
