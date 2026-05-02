# PNG history & external validator protocol

Every PNG produced by the pipeline (axonometric renders, top-down
views, side-by-side comparisons, SU screenshots, debug overlays) is
copied to `runs/png_history/` and indexed in
`runs/png_history/manifest.jsonl`, so an external **planta validator
microservice** can consume the stream, score each render, and report
regressions back into the manifest.

## Storage layout

```
runs/png_history/
    manifest.jsonl                         # append-only, one JSON per line
    2026-05-02T05-30-04_5286411_axon_3d_post_fix_88ef2ba6.png
    2026-05-02T05-30-05_5286411_axon_top_post_fix_9118c26b.png
    ...
```

Filename pattern: `<UTC timestamp>_<git short>_<original stem>_<sha8>.png`.

## Manifest entry schema

```json
{
  "id": "20260502T053004Z_5286411_axon_3d_post_fix_88ef2ba6",
  "created_at": "2026-05-02T05:30:04+00:00",
  "kind": "axon_axon | axon_top | skp_view | sidebyside | overlay | legacy | ...",
  "history_path": "runs/png_history/2026-05-02T05-30-04_..._88ef2ba6.png",
  "original_path": "runs/vector/axon_3d_post_fix.png",
  "sha256": "<png hash>",
  "size": 209594,
  "source": {
    "skp":       {"path": "...", "sha256": "...", "size": 248013, "mtime": "..."} | null,
    "consensus": {"path": "...", "sha256": "...", "size": ..., "mtime": "..."} | null,
    "pdf":       {"path": "...", "sha256": "...", "size": ..., "mtime": "..."} | null
  },
  "generator": {"script": "tools/render_axon.py", "git_commit": "5286411"},
  "params": {"mode": "axon", "dpi": "200", "state": "post_fix"},
  "validation": null
}
```

`validation: null` means **pending**.

## How a generator records a PNG

```python
from tools.png_history import register
register(
    "runs/vector/axon_3d.png",
    kind="axon_axon",
    source={"skp": "runs/vector/planta_74.skp",
            "consensus": "runs/vector/consensus_model.json",
            "pdf": "planta_74.pdf"},
    generator="tools/render_axon.py",
    params={"mode": "axon", "dpi": 200},
)
```

Or CLI: `python -m tools.png_history register PNG --kind X --skp ... --consensus ...`.

`tools/render_axon.py` already calls `register()` automatically; pass
`--no-history` to skip.

## Validator microservice contract

The validator runs out-of-process (any language, any host), polling
or watching the manifest. Recommended loop:

1. **Fetch pending:**
   ```bash
   python -m tools.png_history pending
   ```
   Each line is a manifest entry with `validation: null`.

2. **Score the PNG.** Read it from `<repo>/<history_path>`. The
   validator can use any combination of:
   - PDF baseline at `source.pdf.path` (ground-truth geometry)
   - consensus geometry at `source.consensus.path`
   - the .skp at `source.skp.path` (open with SKP SDK or our
     `tools/inspect_walls_report.rb`)

3. **PATCH the entry:**
   ```bash
   python -m tools.png_history validate <id> \
       --score 0.91 \
       --issues '["parapet_height_off_by_5cm","missing_door_w012"]' \
       --notes "axon matches PDF perimeter; door w012 absent in render"
   ```
   This rewrites `manifest.jsonl` atomically (`.tmp` → rename), setting:
   ```json
   "validation": {
     "score": 0.91,
     "issues": ["parapet_height_off_by_5cm", "missing_door_w012"],
     "notes": "...",
     "validated_at": "2026-05-02T06:00:00+00:00"
   }
   ```

## Programmatic access

```python
from tools.png_history import list_entries, pending_validation, apply_validation

for e in pending_validation():
    score, issues, notes = my_validator(e)
    apply_validation(e["id"], {"score": score, "issues": issues, "notes": notes})
```

## Why JSONL (not JSON or DB)

- Append-only writes are crash-safe (no corrupt-mid-write).
- Generators don't have to lock or re-read the whole file.
- The validator updates by rewrite-and-rename, which is atomic on POSIX
  and Windows (`os.replace`).
- Easy to `tail -f` or pipe to `jq`.

## Known PNG kinds (initial vocabulary)

| `kind` | Generator | Notes |
|---|---|---|
| `axon_axon` | `tools/render_axon.py --mode axon` | matplotlib isometric |
| `axon_top`  | `tools/render_axon.py --mode top`  | matplotlib top-down |
| `skp_view`  | PowerShell screenshot of SU2026   | full-desktop capture, params.view |
| `sidebyside` | `render_sidebyside.py` | PDF + render diptych |
| `overlay`   | `render_proto_overlays.py`, `render_with_openings.py` | wall/opening overlays on PDF |
| `legacy`    | backfill of pre-history PNGs       | params.state=pre_fix to flag stale renders |

Add new kinds freely; the validator uses `kind` to dispatch which
heuristics to apply but unknown kinds default to a generic visual
sanity check.
