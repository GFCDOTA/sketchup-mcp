# Current State — 2026-05-13 (post PR #121 merge)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `develop` (clean, fast-forwarded)
- **develop @** `39a8f3a` — PR #121 (`feat(human-walls): protocol
  + tools to fix global SKP visual fidelity`) merged 2026-05-13
- **Open PRs:** none
- **Open issues:** **#122** — `planta_74: close
  global_visual_fidelity WARN advisory (post-PR #121)`, advisory
  only, body at
  `.ai_bridge/pr_bodies/ISSUE_BODY_visual_confirm_pendente.md`

## Most recent PR

| PR | Title | SHA | When |
|---|---|---|---|
| #121 | feat(human-walls): protocol + tools to fix global SKP visual fidelity | `39a8f3a` | 2026-05-13 23:48 UTC |

8-commit feature branch squashed to develop. +11 423 LOC. Three
hard fidelity axes PASS; advisory axis (global_visual_fidelity)
WARN with operator-verbal-waived rationale documented in
`fixtures/planta_74/operator_acknowledgment_2026-05-13.md`.

## Pipeline state for planta_74

The 4-axis verdict on
`fixtures/planta_74/fidelity_4axis_report.json`:

```
wall_fidelity            PASS  h_o005 cut_into_wall via h_w000
soft_barrier_fidelity    PASS  0 cells need a soft_barrier
semantic_room_fidelity   PASS  SALA labels preserved
global_visual_fidelity   WARN  operator waived; issue #122 tracks
verdict_top_level        WARN  (advisory only)
```

Consensus: `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json`
(35 walls, 11 rooms, 12 openings, 1 soft_barrier).

Final priors in `tools/find_loop_closure_candidates.py`
`PLANTA_74_PAIR_PRIORS`:

| Pair                                  | candidate_type        | evidence  | conf |
|---------------------------------------|-----------------------|-----------|------|
| A.S. ↔ TERRACO SOCIAL                 | `already_explained`   | `h_w001`  | n/a  |
| **A.S. ↔ TERRACO TECNICO**            | `semantic_room_split` | `open_plan` | 0.85 |
| **TERRACO SOCIAL ↔ TERRACO TECNICO**  | `semantic_room_split` | `open_plan` | 0.90 |
| SALA DE JANTAR ↔ SALA DE ESTAR        | `semantic_room_split` | `open_plan` | n/a  |

The two **bold** rows changed in PR #121's final commit
(2026-05-13). Earlier values were `human_soft_barrier(peitoril)`;
the change is honesty about the absence of any physical divider
in the PDF.

## Last 5 develop merges

| SHA | PR | Title |
|---|---|---|
| `39a8f3a` | #121 | feat(human-walls): protocol + tools to fix global SKP visual fidelity |
| `9ae9203` | #120 | fix(human-openings): host classifier + shift gate |
| `0f4465b` | #118 | feat(human-openings): real planta_74 annotation run + auto-calibrate |
| `3c9761c` | #117 | docs(claude-md): record human-openings ground-truth protocol in §10 |
| `f18da68` | #116 | feat(human-openings): mandatory ground-truth pipeline (FP-014 P0 ship) |

## Top of next-session queue

1. 🟡 **P1 — Slice 6a** — `room_polygon_override` schema + apply
   layer per ADR-002 §4. Touches `cockpit/overrides.py`,
   `tools/apply_overrides.py`,
   `tools/fidelity/compare_generated_to_expected.py`. ~25 new tests.
   MEDIUM risk (first override branch to mutate room geometry).
2. 🟡 P1 — Slice 6b — chip promotion + text-area polygon entry UX.
   Depends on 6a.
3. 🟡 P1 — Cycle 6 (Stage 1.6 SU integration) — wire autorun
   inspector into `gate_f`. SU runtime; focused session.
4. 🟢 P2 — Cycle 7: promote `--inspect-strict` default in CI
   (after Cycle 6).
5. ↘ Issue #122 — visual-confirm advisory for planta_74; bundle
   into next planta_74 cycle, don't make it standalone.
6. 🔴 P2 — REAL multi-PDF corpus (RED — needs Felipe to provide
   3+ real planta PDFs).

## Tooling notes

- **gh CLI** at `C:\Program Files\GitHub CLI\gh.exe`; not on Bash
  PATH. Always invoke via absolute path +
  `--repo GFCDOTA/sketchup-mcp`. Auth keyring
  (account `fmodesto30`, scope `repo`). See
  `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`.
- Squash-merge is the established pattern on this repo (see commit
  history: #114/#116/#118/#120/#121 all squashed).
- `--delete-branch` deletes the remote branch on merge; the local
  feature branch must be deleted manually
  (`git branch -D feat/<name>` after `git pull --ff-only`).
