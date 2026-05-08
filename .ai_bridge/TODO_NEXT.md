# TODO Next — ROI-ordered

> Continuous queue. Top items execute first. Update as items land
> or new ones surface.
>
> **Ordering rule (per `feedback_autonomia_operacional_protocolo.md`):**
> GREEN first, then YELLOW with validation, then RED only after
> human unblock.

## Format

Each entry:
- **Color** — 🟢 GREEN / 🟡 YELLOW / 🔴 RED
- **Priority** — P0 / P1 / P2 / P3
- **Evidence** — why this matters
- **Touchpoints** — files / commands likely involved
- **Validation** — how to know it worked
- **Risk** — what can break

---

## ✅ DONE (2026-05-08 wave) — queue zerada

All 9 PRs from the previous queue merged. See `HANDOFF.md` for
per-PR table + merge SHAs. CI all green on develop. 85/85 tests.

Cycle 12 (Ground Truth v1 + Fidelity Engine) shipped with advisory
mode (`continue-on-error: true`) on the fidelity step until Cycle 8b
clears the 3 known FP-012 hard_fails.

## 🟡 P1 — Cycle 8b: promote concave-hull default

Highest-ROI remaining technical item.

- **Color:** YELLOW (alters baseline numbers — needs validation)
- **Goal:** flip `--use-concave-hull` default to True (or remove
  flag), recalibrate `tests/baselines/planta_74.json` and
  `ground_truth/planta_74_micro.json` ranges, regenerate
  `docs/preview/example_top.png`. Then remove
  `continue-on-error: true` from the fidelity step in
  `quality_gates.yml` (single-line change documented in
  `docs/ground_truth_v1.md`).
- **Decision required:** ratio choice. From the spike sweep
  (`docs/diagnostics/2026-05-07_planta_74_fp012_spike_results.md`):
  - ratio=0.30 → SUITE 01 = 18.61 m² (most architecturally correct,
    biggest baseline shift)
  - ratio=0.55 → SUITE 01 = 35.64 m² (less disruption, biggest fix
    that still preserves room shapes near-baseline)
- **Recommendation:** to be decided after consulting `planta-assistant`
  via Ollama (protocol-compliant — Felipe não é roteador humano).
- **Validation:** all 85 tests pass post-recalibration; quality_gates
  workflow turns from advisory → hard blocker; develop stays green;
  fidelity_report shows global=1.0.
- **Risk:** medium. PR INTENTIONALLY changes baseline numbers.
  Can split into two PRs (flag promote first, GT recalibration
  second) if review surface gets too big.

## 🔴 P1 — Cycle 6: wire autorun inspector into smoke gate F (Stage 1.6)

- **Color:** RED — Stage 1.6 was explicitly held in earlier session
- **To unblock:** Felipe needs to lift Stage 1.6 hold

## 🔴 P2 — Multi-PDF corpus

- **Color:** RED — needs Felipe to provide 3+ different real planta
  PDFs
- **Goal:** widen the test surface beyond `planta_74` so detector
  retunes don't accidentally specialize

## 🔴 P3 — `feature/smoke-promotes-inspector-v2-gate` orphan branch

- **Color:** RED — coupled to Stage 1.6
- **Status:** branch on origin + local, never had PR opened.
  Contains gate G2 + inspector v2 schema.
- **Decision required:** open PR + merge (after Stage 1.6 unblock)
  OR delete branch (if Cycle 6 supersedes it)

## 🟢 P3 — Cleanup hygiene scan (CLAUDE.md §15)

- **Color:** GREEN — additive, no risk
- **Goal:** scan repo for stale .md / generated PNG / abandoned
  scripts after the 9-PR wave
- **Touchpoints:** root-level `.md`, `runs/_archive/`, top-level
  `proto_*.py` candidates
- **Validation:** nothing live broken; archive doc updated
- **Risk:** low. Per CLAUDE.md §15: archive instead of delete;
  preserve baselines / ground_truth / regression artifacts.
