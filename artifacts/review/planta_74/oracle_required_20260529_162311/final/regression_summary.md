# SKP Visual Review — BLOCKED (controlled cycle)

## Time

2026-05-29T16:23:32Z

## Invocation

```bash
python -m tools.run_skp_visual_review \
  --fixture planta_74 \
  --out artifacts/review/planta_74/oracle_required_20260529_162311 \
  --oracle chatgpt_bridge \
  --require-oracle
```

## Result

```
exit_code = 3
[oracle] BLOCKED: bridge unreachable at http://localhost:8765
```

The script **fail-fast aborted** before invoking SketchUp. No
`.skp` / renders / geometry_report were generated — by design,
because `--require-oracle` makes the bridge a hard prerequisite.

This is the **expected and correct behaviour** of FP-030 maturity 2
under the user's controlled cycle:

> "Se a bridge não suportar imagem ou estiver indisponível,
> registrar BLOCKED com motivo técnico e próximo comando. Não
> fingir que validou visualmente."

## Technical blockers — two distinct issues

### Blocker 1 (runtime): bridge process not running

- `localhost:8765/health` returned timeout (TCP connection refused)
- `netstat` confirmed no listener on port 8765
- The bridge code exists at `E:/chatgpt-bridge/bridge.py` but is not
  currently started

Next command (operator):

```bash
# From E:/chatgpt-bridge/ , in a separate terminal:
python bridge.py
# This will launch the FastAPI server on localhost:8765
# (drives the ChatGPT Windows desktop app via UI automation)
```

### Blocker 2 (architectural): bridge does NOT accept images

Inspection of `E:/chatgpt-bridge/bridge.py:55-56`:

```python
class AskRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
```

Inspection of `E:/chatgpt-bridge/driver.py`: **zero matches** for
`image | attach | upload | file`.

The bridge contract is **text-only**:

- Endpoint: `POST /ask {prompt: str, timeout?: int}`
- It drives the ChatGPT desktop app's text input field only
- There is no image upload path

**This means**: even after fixing Blocker 1, the maturity 2
`call_oracle_bridge()` in `tools/run_skp_visual_review.py`
(which sends `{prompt, images: {…}, context}` with base64 PNGs)
**will not be accepted by the current bridge schema**.

The bridge would either reject the payload (Pydantic validation
error on missing/extra fields) or treat the JSON blob as the
text prompt — neither produces real vision review.

Next command (operator):

```bash
# Option A — extend the bridge to accept images
#   1. Add image fields to AskRequest model
#   2. Add UI automation in driver.py to attach images to the
#      ChatGPT desktop input via clipboard/upload button
#   3. Restart bridge.py
#
# Option B — switch oracle backend to a real vision API
#   1. Add `--oracle anthropic_vision` or `--oracle openai_vision`
#      to tools/run_skp_visual_review.py
#   2. Use the corresponding SDK with image attachment support
#   3. Document API key in env var
#
# Option C — accept that the bridge is text-only and run without
#   --require-oracle, treating qualitative axes as
#   `needs_claude_inline_review` (maturity ~60% cap)
```

## What was NOT validated

- `model.skp` — not built
- `model_top.png`, `model_iso.png` — not rendered
- `side_by_side_pdf_vs_skp.png` — not composed
- `geometry_report.json` — not produced
- 10 deterministic heuristics — not run
- Qualitative axes — not reviewed

This is **on purpose**. The user's controlled cycle explicitly
forbade faking a visual validation when the bridge is unavailable.

## Validator maturity after this run

**Unchanged: ~60% (per PR #202)**.

This run does **not** lower the maturity — it confirms that the
`--require-oracle` safety net works in real production conditions
(bridge offline AND bridge schema incompatible with images).

The maturity cap of ~70% without functional bridge remains valid.
Reaching ~70-75% requires resolving **both** Blocker 1 and
Blocker 2 above.

## Next jump (only with explicit user trigger)

Per user roadmap (post-#202), the natural progression is:

1. **Resolve Blocker 1 + Blocker 2** (bridge with image support)
   OR switch to a real vision API → maturity ~65-75%
2. **Overlay/diff geométrico** → maturity ~80%
3. **Positional heuristics** → maturity ~85-90%
4. **FP-031 auto-fix** — only with real FAIL trigger

## Summary requested by user

| Field | Value |
|---|---|
| Final verdict | BLOCKED |
| Artifacts | none (fail-fast before build) |
| Oracle status | unavailable (bridge offline) + incompatible (text-only schema) |
| FAIL | n/a |
| WARN | n/a |
| What was validated automatically | nothing — bridge prerequisite not met |
| What still needs human review | n/a — no artifacts to review |
| Validator maturity after this run | ~60% (unchanged from PR #202) |

## SketchUp sanity check

The user offered to open `final/model.skp` in SketchUp as a sanity
check, but **no `.skp` exists** in this run's `final/` — the script
aborted before invoking SU. There is nothing to open.

If a sanity check is desired, the prior baseline at
`artifacts/planta_74/planta_74.skp` (committed in PR #185/#191) is
still the canonical reference.
