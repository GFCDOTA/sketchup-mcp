# Planta validator microservice

Microservice that scores every PNG registered in
`runs/png_history/manifest.jsonl` and writes the result back into the
manifest's `validation` field, so subsequent runs can spot regressions.

The validator never *generates* PNGs — that's done by the render scripts
that auto-register their output via `tools.png_history.register`. The
validator is read-only on the render side and append-only on the manifest
(via `tools.png_history.apply_validation`).

Pair this doc with [`png_history_protocol.md`](png_history_protocol.md),
which describes the manifest itself.

---

## Layout

```
validator/
  __init__.py
  pipeline.py        # validate_entry / validate_pending
  service.py         # FastAPI app on port 8770
  run.py             # CLI: --once / --watch / --port / --show
  vision.py          # optional Ollama qwen2.5vl:7b critique
  scorers/
    __init__.py     # REGISTRY + dispatch (kind -> scorer)
    base.py         # ScorerContext, Issue, ScorerResult dataclasses
    axon.py         # axon_axon, axon_top, axon_*
    skp_view.py     # skp_view, _skp_*, _su_screenshot, sidebyside_skp
    sidebyside.py   # sidebyside, side_by_side, sidebyside_axon, triple_*
    legacy.py       # fallback (sanity check only)
```

---

## CLI

```bash
# validate every pending entry once and exit
.venv/Scripts/python -m validator.run --once

# re-run scorer on entries already validated (e.g. heuristic update)
.venv/Scripts/python -m validator.run --once --force

# poll the manifest every 30s (configurable via --interval)
.venv/Scripts/python -m validator.run --watch

# serve the FastAPI app
.venv/Scripts/python -m validator.run --port 8770

# show one-line summary per entry (id, kind, score, issue codes)
.venv/Scripts/python -m validator.run --show

# enable Ollama qwen2.5vl:7b qualitative critique (best effort)
.venv/Scripts/python -m validator.run --once --vision
```

`--vision` adds a `validation.vision` block to each result with the
model's free-text critique. Skipped silently if Ollama isn't reachable
on `http://localhost:11434` (matches `feedback_gpt_critico_imagens`:
the vision pass is a *qualitative* supplement, not the primary signal).

---

## REST API (port 8770)

| Method | Path                              | Purpose |
|--------|-----------------------------------|---------|
| GET    | `/health`                         | basic liveness + counts |
| GET    | `/metrics`                        | aggregate scores by kind |
| GET    | `/entries`                        | full manifest |
| GET    | `/entries/pending`                | entries with `validation == null` |
| GET    | `/entries/{id}`                   | one entry as stored |
| POST   | `/validate/{id}?vision=false`     | run scorer for one entry, persist |
| POST   | `/validate-pending?vision=false&limit=N` | validate every pending |

---

## Scorer dispatch

`scorers.resolve(kind, original_path)` chooses a scorer by:

1. exact `kind` match in `REGISTRY`
2. longest-prefix match (`axon_axon` → `axon_axon`, falls back to `axon`)
3. if `kind == 'legacy'`, sniff `original_path` filename for known
   suffixes (`_skp_`, `axon_top`, `sidebyside`, etc.) and reroute
4. `__default__` (legacy scorer)

Adding a new scorer:

```python
# validator/scorers/myscorer.py
from .base import Issue, ScorerContext, ScorerResult

def score_my_kind(entry, ctx: ScorerContext) -> ScorerResult:
    ...
    return ScorerResult(score=0.85, issues=[...], notes="...",
                        metrics={...}, scorer="my_kind")

# validator/scorers/__init__.py
REGISTRY["my_kind"] = score_my_kind
```

---

## Per-kind heuristics (current)

### `axon_axon`, `axon_top`, `axon`

- **rooms_score (45%)**: `consensus.rooms` length vs target ≥ 6 for the
  planta_74 baseline. 0 rooms = critical.
- **fill_score (35%)**: non-white pixel fraction inside the *tight*
  drawing bbox. Target 20–85%. <5% or >97% = render is broken.
- **coverage_score (20%)**: canvas-wide non-white fraction. Expected
  5–70%; outside that = something is off.

Background is calibrated for the cream RGB(245,243,238) `render_axon`
canvas — strict-white thresholds would saturate.

### `skp_view`, `_skp_*`, `_su_screenshot`, `sidebyside_skp`

- Resolves the inspect_walls_report.rb output whose `meta.skp_path`
  basename matches `entry.source.skp.path`, choosing the report whose
  mtime is closest to (≥) the .skp's mtime.
- **overlaps_score (40%)**: 1.0 if `wall_overlaps_top20 == []`,
  decays linearly to 0 by 3 overlaps.
- **default_score (40%)**: 1.0 if `default_faces_count == 0`,
  decays to 0 by 20 default-material faces.
- **png_basic (20%)**: PNG isn't blank-white, blank-black, or uniform
  (color-bin diversity check catches "VMware viewport never repainted").

Falls back to PNG-only score (cap 0.4) when no inspect report matches.

### `sidebyside`, `side_by_side`, `sidebyside_axon`, `triple_comparison`

- **parity_score (70% if SSIM available, else 100%)**: left/right
  non-white coverage ratio should be in [0.4, 2.5]. One blank half = 0.
- **ssim_norm (30%, optional)**: SSIM between left half and the source
  PDF rasterized via `pypdfium2`, normalized so [0.05, 0.45] maps to
  [0, 1]. Skipped silently if PDF or `skimage` unavailable.

### `__default__` / `legacy` fallback

- Just confirms the PNG exists, sha256 matches the manifest, image isn't
  blank. Caps at 0.7 since we don't know what the PNG was supposed to
  show.

---

## Score interpretation

| Score      | Meaning |
|------------|---------|
| `1.00`     | All checks passed |
| `0.80–0.99`| Minor warnings (warns only) |
| `0.50–0.79`| At least one error or major warning |
| `< 0.50`   | Likely broken render OR no source artifacts to cross-check |
| `0.00`     | PNG missing / completely blank / scorer crashed |

A `0.40` from `skp_view` typically means "no inspect report available
for this .skp" — re-run `tools/inspect_walls_report.rb` against that
.skp and the score will refresh on the next `--once`.

---

## Validation entry schema

`apply_validation(id, payload)` writes:

```json
{
  "score":  0.913,
  "issues": [
    {
      "severity": "warn|error|info",
      "code":     "coverage_parity_off",
      "message":  "left/right non-white coverage ratio = 0.26 (expected 0.4..2.5)",
      "detail":   {"...arbitrary..."}
    }
  ],
  "notes":  "sidebyside: parity=0.74 ssim=0.51",
  "metrics": {
    "size": [4472, 1406],
    "nonwhite_left":  0.198,
    "nonwhite_right": 0.754,
    "coverage_ratio": 0.263,
    "ssim_left_vs_pdf": 0.508
  },
  "scorer": "sidebyside",
  "validated_at": "2026-05-02T15:42:11+00:00",
  "vision": {            // only if --vision
    "model": "qwen2.5vl:7b",
    "response": "OK — render alinhado..."
  }
}
```

Each entry's `id` is the manifest's `entry_id`; same as
`runs/png_history/manifest.jsonl`'s line `id` field.

---

## Known limitations

1. **No content-hash matching for inspect reports.** `inspect_walls_report.rb`
   doesn't yet record the .skp's sha256, so we match by basename + mtime.
   This silently fails for renamed copies (e.g. `planta_74_pre_fix.skp`
   gets no match). Fix: extend the Ruby plugin to emit `meta.skp_sha256`.
2. **Vision LLM is local-only.** `validator.vision` hits Ollama; there's
   no GPT-4V path because the chatgpt-bridge currently has no image
   upload (see `feedback_gpt_critico_imagens`). When/if the bridge gets
   image support, swap `vision.py`'s POST target.
3. **PDF baseline is page 1 only.** Multi-page plantas would need
   per-entry hint of which page to compare.
4. **No regression alerting.** The validator scores entries but doesn't
   diff against historical scores. Easy follow-up — manifest already has
   a stable `id` ordering by timestamp.
