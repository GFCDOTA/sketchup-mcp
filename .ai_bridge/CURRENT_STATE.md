# Current State — 2026-05-23 (consolidation cycle on `docs/adr-005`)

> Per-session snapshot. Overwrite (not append). For history →
> `HANDOFF.md` or `docs/ops/`.

## Branch

- **Working:** `docs/adr-005-spec-driven-development` (in progress;
  not pushed yet; consolidation + canonical-artifact-rule docs)
- **develop @** `8724ca2` — PR #142
  (`fix(plan-shell): door leaf hinge_world for vertical walls (FP-015)`)
  merged 2026-05-20
- **Open PRs:** to be checked via gh
- **Untracked files in tools/:**
  - `tools/build_room_ring_skp.py`
  - `tools/build_room_ring_skp.rb`
  - `tools/dump_skp_groups.py`
  - `tools/dump_skp_groups.rb`
  (left from earlier session; investigation pending — see TODO_NEXT)

## Most recent PRs on develop (post-#121)

| PR | Title | SHA | When |
|---|---|---|---|
| #142 | fix(plan-shell): door leaf hinge_world for vertical walls (FP-015) | `8724ca2` | 2026-05-20 |
| #141 | feat(plan-shell): Phase 2 visual parity — doors / windows / glazed / passage | `70aeeb6` | 2026-05-20 |
| #140 | chore(plan-shell): geometry invariants hardening + provenance audit | `d0adf60` | 2026-05-19 |
| #139 | test(plan-shell): mutation suite + mutant inputs + FP regression catalog (ADR-004) | `2d8daff` | 2026-05-19 |
| #138 | fix(plan-shell): soft_barriers as per-segment swept slabs + invariant suite | `8e16fbf` | 2026-05-18 |
| #137 | feat(plan-shell): wire as smoke gate F alternative + content-hash cache | `bcd54da` | 2026-05-17 |
| #136 | feat(plan-shell): experimental parallel exporter via shapely union | `46acfb5` | 2026-05-16 |
| #135 | chore: final pass on fixtures/planta_74/ — 6 orphan version-iterations | `e59ab26` | 2026-05-16 |
| #134 | chore: deep repo hygiene — delete 70+ stale artifacts, archive 2 | `b66841f` | 2026-05-15 |
| #133 | chore: delete 36 obsolete runs/ subdirs (−17 MB, 0 active refs) | `296f429` | 2026-05-15 |
| #132 | fix: disarm sketchup autoruns on every launch (FP-014) | `4c34c93` | 2026-05-14 |
| #131 | feat(planta_74): annotated paint guide for pending soft_barrier zones | `de43852` | 2026-05-14 |
| #130 | Reclassify h_o005 host wall — drops planta_74 from FAIL to WARN | `0f358aa` | 2026-05-14 |
| #129 | feat(visual-gate): PR B4 — wire visual_fidelity_gate into verify_fidelities | `d4e256d` | 2026-05-14 |
| #128 | feat(visual-gate): PR B3 — 8 algorithmic checks for the visual fidelity gate | `a6e7ec2` | 2026-05-14 |
| ... | (PRs #122–#127 omitted, visual_fidelity_gate B0–B2 wave) | | |
| #121 | feat(human-walls): protocol + tools to fix global SKP visual fidelity | `39a8f3a` | 2026-05-13 |

(21 PRs landed between this snapshot's previous freeze at #121 and
the current #142.)

## Active artifacts (canonical, do NOT replace with parallel demos)

| Artifact | Purpose |
|---|---|
| `runs/planta_74_plan_shell/model.skp` | Planta_74 canonical SKP from `plan_shell` exporter (Phase 2) |
| `runs/planta_74_plan_shell_smoke/model.skp` | Smoke harness output (gate F alternative) |
| `runs/quadrado_demo/quadrado.skp` | Micro-fixture canônico: 34 entities raw, opens clean in SU |
| `runs/quadrado_demo/quadrado_with_window.skp` | POC of in-place window edit (etapa 2 of micro→planta flow) — 19 faces, 8/8 invariants PASS |
| `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json` | Canonical consensus post-PR #121 (35 walls, 11 rooms, 12 openings, 1 soft_barrier) |
| `fixtures/planta_74/human_openings_annotation.png` | PNG ground truth for openings (per FP-014 protocol) |
| `planta_baixa_74m2.pdf` | PDF source of geometric truth |

## Active rules (priority order; read CLAUDE.md first)

1. **Canonical Artifact Rule** (user MEMORY
   `feedback_canonical_artifact_rule.md`, priority ROOT_RULE,
   2026-05-23) — micro-fixture → planta in 5 disciplined etapas;
   in-place edit > rebuild; no parallel demos.
2. **CLAUDE.md** — git flow (§0), hard safety rules (§1), pipeline
   invariants (§2), SketchUp last gate (§3), Non-Stop Autonomy (§17)
3. **Visual Fidelity Gate** (§10, 2026-05-14) — 7 artifact set
   required for top-level PASS
4. **Human-openings ground-truth protocol** (FP-014 cycle) — PNG
   annotation supersedes detector for planta_74

## Pipeline state for planta_74

The 4-axis verdict on
`fixtures/planta_74/fidelity_4axis_report.json`:

```
wall_fidelity            PASS  h_o005 cut_into_wall via h_w000
soft_barrier_fidelity    PASS  0 cells need a soft_barrier
semantic_room_fidelity   PASS  SALA labels preserved
global_visual_fidelity   WARN  operator waived; issue #122 tracks (advisory)
verdict_top_level        WARN  (advisory only)
```

Plan-shell exporter is now the **primary** SKP producer (post PR
#137 — wired as smoke gate F alternative with content-hash cache).
Cycle 6 (autorun inspector wired into gate F) is still pending.

## Top of next-session queue (canonical-artifact-aware)

1. 🟡 **P1 — Etapa 4+5 of quadrado window POC**: promote
   `runs/quadrado_demo/_invariants.py` to
   `tests/test_quadrado_window_invariants.py` (regression gate) +
   apply the same in-place edit pattern to `runs/planta_74_plan_shell/model.skp`
   (one of the existing windows or a new one as proof-of-method) +
   comparison report.
2. 🟡 P1 — **Slice 6a** — `room_polygon_override` schema + apply
   layer per ADR-002 §4. Unchanged from last cycle.
3. 🟡 P1 — Cycle 6 (Stage 1.6 SU integration) — wire autorun
   inspector into `gate_f`. SU runtime; focused session.
4. 🟡 P1 — Investigate 4 untracked files in `tools/`
   (`build_room_ring_skp.{py,rb}`, `dump_skp_groups.{py,rb}`):
   either promote (add tests + commit) or archive.
5. 🟢 P2 — Cycle 7: promote `--inspect-strict` default in CI
   (after Cycle 6).
6. 🟢 P2 — Document the canonical-artifact rule in CLAUDE.md as
   §18 (currently lives only in user MEMORY).
7. 🔴 P2 — REAL multi-PDF corpus (RED — needs 3+ real planta PDFs).

## Recently added rules/lessons (2026-05-23)

- **LL-013** — Canonical Artifact Rule: 5-step micro→planta flow.
- **LL-014** — Read coordinates from the model, never hardcode.
- **LL-015** — SU runner mode protocol (interactive default, opt-in
  headless). Reference helper:
  `tools/su_runner_safety.py` (parse_mode / should_terminate /
  is_attach / log_mode), 35 unit tests in
  `tests/test_su_runner_safety.py`.
- **FP-016** — Path proliferation (parallel artifacts outside
  canonical run dir).
- **FP-017** — Rebuild via `consume_consensus.rb` when in-place
  edit was correct.
- **FP-018** — Hardcoded coords cause `intersect_with` float drift.
- **FP-019** — Python `subprocess.terminate` of SU confuses user
  about SKP stability. Now backed by runtime gate
  (`tools/su_runner_safety.py` + 35 tests).

## Pipeline-core focus (priority for next ROI cycles)

The real product is `plan_shell` exporter producing planta_74 SKP.
Everything else is laboratory or scaffolding. Next ROI cycles
should ALL pass the "pipeline real or pretty demo?" filter:

- ✅ Pipeline-core: anything that improves wall_shell / plan_shell /
  openings carving / room polygons / fidelity gate / smoke harness
  / overlay reports / comparison against PDF / regression gates.
- ⚠️ Laboratory: micro-fixture (quadrado_demo) experiments — OK if
  the path to planta is declared (etapas 4–5 of LL-013).
- ❌ Embelezamento: dashboard polish, render aesthetics, demo
  artifacts without canonical path back to planta.

The current branch (`docs/adr-005-spec-driven-development`) ships
docs + protocol + safety helper — all pipeline-adjacent (specs,
rules, runner safety). After PR #150 merges, the next high-ROI
cycle is **etapa 5 of the quadrado POC**: apply the in-place edit
method to `runs/planta_74_plan_shell/model.skp` and produce a
comparison report against the plan_shell exporter baseline.

## Tooling notes

- **gh CLI** at `C:\Program Files\GitHub CLI\gh.exe`; not on Bash
  PATH. Always invoke via absolute path +
  `--repo GFCDOTA/sketchup-mcp`. Auth keyring
  (account `fmodesto30`, scope `repo`). See
  `~/.claude/projects/E--Claude/memory/reference_gh_cli_absolute_path.md`.
- **Python**: `E:/Python312/python.exe` (matplotlib 3.10.8); the
  Windows Store stub at
  `C:\Users\felip_local\AppData\Local\Microsoft\WindowsApps\python.exe`
  is broken — error 0x80070002.
- **SU 2026**: `C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe`.
  Launch with positional `.skp` to skip welcome dialog (LL-009).
  Plugins dir: `%APPDATA%\SketchUp\SketchUp 2026\SketchUp\Plugins`.
  Autorun mechanism: control files (`autorun_*_control.txt`) +
  `disarm_sketchup_autoruns` (FP-014 fix).
- Squash-merge is the established pattern on this repo (see commit
  history: #114/#116/#118/#120/#121/.../#142 all squashed).
- `runs/` is gitignored — outputs of pipeline runs are local.
  `tools/runs/` (dashboard manifest dir) IS tracked.
