# LL-024 — GPT Auto-Consult Gate

## Status

Delivered in `feat/ll-024-gpt-auto-consult-gate` (2026-05-29).

## Problem

The user has been asked to be a copy/paste relay between Claude and
ChatGPT when architectural / merge / WARN-carry decisions arise. This
is a workflow bug. When there is a real decision to make and a bridge
to ChatGPT is available, the agent should consult it automatically,
record the exchange, and act.

This gate is **text-only**. It does **not** replace the FP-030 Visual
Oracle Gate (which handles image review via `ollama_vision` provider).

## Rule

```text
The user is not a copy/paste relay.
When a canonical trigger applies AND a bridge is reachable,
the agent SHALL package the context, send it to the bridge,
and persist the exchange in .ai_bridge/.
When the bridge is offline, the gate records the question
and skips honestly (or BLOCKs if --require-consult was set).
```

## When this gate applies (9 canonical triggers)

| # | Trigger | Example |
|---|---|---|
| 1 | `oracle_verdict_neq_final_verdict` | Oracle says PASS, final says FAIL |
| 2 | `oracle_pass_but_known_warnings` | PR #206 case: oracle PASS, baseline WARNs carry |
| 3 | `final_fail_non_obvious_fix` | FAIL but no clear source-supported fix |
| 4 | `a_b_c_decision_with_tradeoff` | Path A vs B vs C with real trade-off |
| 5 | `risk_of_inventing_geometry` | Hard Rule #1 territory |
| 6 | `about_to_open_new_cycle_post_slice` | Slice complete, no real trigger to continue |
| 7 | `require_oracle_blocks_backend` | `--require-oracle` BLOCKED, A/B/C needed |
| 8 | `big_pr_changes_gate_or_spec` | Risk of friction tax in governance change |
| 9 | `user_requested_consult` | Explicit user trigger |

## When this gate does NOT apply

- Typo / doc-only / trivial changes
- Small evident tests
- Merge of small green PR
- Local cleanup with no impact
- Decision already covered by a canonical rule (constitution.md,
  operational_rules.md, lessons_learned.md, deprecated_context.md)
- Loop that would repeat a previously answered question — agent must
  scan `.ai_bridge/responses/` before invoking

## Contract

### Input

```json
{
  "trigger": "<one of the 9 canonical triggers>",
  "repo_state": {
    "branch": "...",
    "develop_sha": "...",
    "pr": 206
  },
  "context": { "<free shape>": "<typically verdicts, paths, counts>" },
  "question": "<one specific architectural / merge / risk question>"
}
```

### Output

```
.ai_bridge/questions/<UTC>_<trigger>.md   ← prompt sent (or that would have been)
.ai_bridge/responses/<UTC>_<trigger>.md   ← raw response + decision block (when bridge online)
```

### Exit codes

| Code | Status | Meaning |
|---|---|---|
| 0 | ok or SKIPPED_OFFLINE | success or honest skip |
| 2 | invalid | unknown trigger or empty question |
| 3 | BLOCKED_BRIDGE_OFFLINE | `--require-consult` + bridge offline |

## Bridge

Uses the existing text-only ChatGPT bridge at `localhost:8765/ask`
(`bridge.py` at `E:/chatgpt-bridge/`). Contract:

```
POST /ask { "prompt": "..." } -> { "response": "..." }
GET  /health                  -> 200 OK
```

When offline:
- Default: status `GPT_CONSULT_SKIPPED_OFFLINE`. Question file is
  written for manual forward.
- With `--require-consult`: status `BLOCKED_BRIDGE_OFFLINE`, exit 3.

## Tool

`tools/ask_gpt_gate.py` — CLI runner and library. See its docstring
for CLI usage examples.

## Prompt

`tools/prompts/gpt_auto_consult_gate.md` — short reviewer prompt that
forces a 4-section response (Verdict / Reasoning / Risks / Suggested
next action). No markdown fences, no fluff.

## Skill

`.claude/skills/gpt-auto-consult-gate/SKILL.md` — auto-discoverable
skill that fires the agent when one of the 9 triggers applies.

## Tests

`tests/test_ask_gpt_gate.py`:
- Trigger validation (rejects unknown)
- Question file written when bridge offline
- `--require-consult` + offline returns `BLOCKED_BRIDGE_OFFLINE`
- Default + offline returns `SKIPPED_OFFLINE` (exit 0)
- Prompt builder includes all 4 expected sections
- Probe is honest when bridge unreachable

## Dogfooding evidence

`.ai_bridge/questions/<UTC>_oracle_pass_but_known_warnings.md`
documents the trigger #2 case using PR #206 as the dogfood input.
Bridge was offline at run time, so status is `SKIPPED_OFFLINE` and
the question file alone is the evidence.

## Encaixe operacional

Categoria 5 (user-requested milestone) do
`memory/operational_rules.md`. Não cria novo ciclo — operacionaliza
o existente, removendo Felipe do meio.

## What this spec / tool does NOT do

- Does NOT call image-based vision (use FP-030 + `ollama_vision`)
- Does NOT auto-fix code (FP-031 backlog, untriggered)
- Does NOT replace constitution / operational_rules
- Does NOT consult GPT for every trivial change
- Does NOT fabricate a response when the bridge is offline

## Follow-up (only with explicit user trigger)

- Cache: scan `.ai_bridge/responses/` before invoking to avoid duplicate
  questions
- Inline auto-trigger from `run_skp_visual_review.py` when verdict
  divergence is detected (currently the agent decides per-turn)
- Bridge with broader response timeout for complex questions

## Related

- Constitution: `.claude/constitution.md`
- Memory: `.claude/memory/multi_agent_coordination.md` (`.ai_bridge/` pattern)
- FP-030 Visual Oracle Gate: `docs/specs/FP-030_visual_oracle_gate.md`
