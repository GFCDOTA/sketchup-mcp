# GPT Requests — append-only log

> Format spec: see `.ai_bridge/README.md` and the protocol doc in
> `~/.claude/projects/E--Claude/memory/feedback_ai_bridge_protocol.md`.
> Each request gets a corresponding entry in `GPT_RESPONSES.md`.

---

## Request 2026-05-07 03:30 — bootstrap entry

### Context

Initial seeding of `.ai_bridge/`. No real GPT consultation yet
this session — direction was clear from the user's autonomous-mode
prompt + previous handoff state.

### Files / Evidence

- `CLAUDE.md` §14 (Autonomous Continuation Protocol) — directs
  agent to consult GPT only on real bifurcations
- Memory rule `feedback_ias_decidem_bifurcacoes.md` — when
  Claude+local converge, execute directly; ask only on real
  scope ambiguity

### Current Hypothesis

When this log starts seeing real entries, that's the signal that the
project hit a non-trivial decision point (architectural / regression /
unclear trade-off). Until then, this file stays empty as proof that
the autonomous loop is sufficient.

### Question

(none — bootstrap entry)

### Expected Output

(none — bootstrap entry)

---

<!-- New requests below this line, newest at top -->

## Request 2026-05-08 14:30 — Cycle 8b promote: ratio choice + PR strategy

### Context

Post-Wave-2026-05-08 state: 9-PR queue zerada (PRs #52–#60 merged),
develop @ `05ba96d`, fidelity engine v1 shipped in advisory mode
(`continue-on-error: true`) with 3 known FP-012 hard_fails. The
next high-ROI technical item is Cycle 8b — promote the
`--use-concave-hull` flag to default-on and remove the advisory
guard.

User installed permanent autonomy protocol
(`feedback_autonomia_operacional_protocolo.md`) authorizing direct
LLM consultation instead of routing through Felipe.

ChatGPT bridge (localhost:8765) was offline at consult time —
fallback per `feedback_always_consult_gpt.md` rule was Ollama local
`planta-assistant:latest`.

### Files / Evidence

- `tools/rooms_from_seeds.py:163-169` — convex hull bug FP-012
- `docs/diagnostics/2026-05-07_planta_74_fp012_spike_results.md`
  — full ratio sweep table
- `docs/diagnostics/2026-05-07_planta_74_suite01_polygon_leakage.md`
  — original FP-012 root cause
- `ground_truth/planta_74/expected_model.json` — current GT v1
  ranges (calibrated against convex-hull observed)
- `.github/workflows/quality_gates.yml` — has the
  hashFiles-guarded fidelity step in advisory mode

### Current Hypothesis (Claude preliminary)

ratio=0.30 is the most architecturally correct (SUITE 01 = 18.61 m²
in a 74 m² apartment, vs 69.91 today). But it would push COZINHA
to 5.23 m² (outside current GT range [7, 18]) and A.S. to ~2 m²
(outside [2.5, 11]). ratio=0.50 lets all current GT ranges pass
(SUITE 01 = 26.75, COZINHA = 8.80) but is less aggressive on
the underlying bug.

### Question

For Cycle 8b promote-to-default, which ratio (0.30 vs 0.55) and
which PR strategy (single-PR coordinated change vs 2-PR split)?

### Expected Output

A clear ratio recommendation + PR-strategy decision in <= 600
words.

### Response → see GPT_RESPONSES.md

