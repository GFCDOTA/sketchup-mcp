# Current State — 2026-05-24 (repo governance + anti-forgetting branch)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `chore/repo-governance-anti-forgetting` (from
  `origin/develop @ 14212ea`)
- **`develop` HEAD:** `14212ea` — PR #153
  (`feat(safety): SU runner mode protocol — clean cherry-pick from
  #150`)
- **In-flight feature branch:** `feature/window-aperture-semantics`
  (3 commits ahead of develop; not yet PR'd)
  - `7e56dc7` `fix(openings): enforce wall-hosted window semantics`
  - `ebdac1a` `fix(walls): canonicalize wall shell and remove residual sliver geometry`
  - `8799466` `chore(quadrado): promote canonical success reference + smoke gate`

## What this branch does

Repo governance pass per user request (2026-05-24):
"diagnostique, classifique, limpe com segurança, documente, crie gate,
valide e commite."

Scope agreed with user (autonomous within these limits):
- **DO** create canonical state docs + ADRs + gate script + hygiene
  report.
- **DO** refresh `.ai_bridge/` with fresh entries.
- **DON'T** delete or archive files (per 3 prior audits' converging
  recommendation; require explicit trigger).

## Pipeline state for planta_74

Unchanged from 2026-05-13 baseline (33 walls / 11 rooms / 12 openings
including human-annotated soft barrier / 8 soft_barriers). The new
wall-shell + window aperture work lives on
`feature/window-aperture-semantics` and improves the quadrado
canonical render but does not alter planta_74 counts.

## Docs added this branch

- `docs/PROJECT_STATE.md` (canonical state snapshot)
- `docs/HANDOFF.md` (canonical onboarding)
- `docs/REPO_HYGIENE.md` (canonical policy)
- `docs/GATES.md` (canonical gate catalogue)
- `docs/ANTI_FORGETTING.md` (10 permanent rules)
- `scripts/project_state_check.py` + `tests/test_project_state_check.py`
- `reports/repo_hygiene_report.md`

## Top of next-session queue

Same as before this branch, plus one new item:

1. 🟢 **THIS BRANCH** — open PR `chore/repo-governance-anti-forgetting
   → develop`. Doc-only + new gate script + 1 new test. Low risk.
2. 🟡 **P1 — Merge `feature/window-aperture-semantics` into `develop`.**
   3 commits with quadrado canonical work, wall-shell canonicalisation,
   window aperture 3D carve. Needs PR.
3. 🟡 P1 — Slice 6a — `room_polygon_override` schema + apply layer
   (ADR-002 §4).
4. 🟡 P1 — Cycle 6 (Stage 1.6 SU integration) — wire autorun inspector
   into `gate_f`.
5. 🟢 P2 — Cycle 7: promote `--inspect-strict` default in CI.
6. 🔴 P2 — REAL multi-PDF corpus (needs Felipe to provide PDFs).

## Tooling notes

- gh CLI at `C:\Program Files\GitHub CLI\gh.exe`; always pass
  `--repo GFCDOTA/sketchup-mcp`.
- Squash-merge is established pattern (PRs #114/#116/#118/#120/#121
  /#134/#135/#153 all squashed).
- New gate: `python scripts/project_state_check.py` validates the
  presence of canonical docs / fixtures / gates listed in
  `PROJECT_STATE.md` and `GATES.md`.
