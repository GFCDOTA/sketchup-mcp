---
description: Run JSON->SKP via cheap smoke gates. Only opens SketchUp if the cheap gates pass and the consensus hash changed.
---

# /validate-skp

End-to-end SketchUp validation through the smoke gates. SketchUp is
the LAST gate, never the first.

> ⚠️ **Pre-requisite (planned):** `scripts/smoke/smoke_skp_export.py`
> does not exist yet. It is tracked as `tooling/sketchup-smoke-gates`
> in [`docs/operational_roadmap.md`](../../docs/operational_roadmap.md).
> Until it lands, run the cheap gates manually:
>
> 1. JSON structural validation of `consensus_model.json`.
> 2. `python tools/render_axon.py` (top + axon previews).
> 3. SHA256 of `consensus_model.json`; skip SU if it matches the
>    previous export.
> 4. Then invoke `python -m tools.skp_from_consensus` directly.
>
> The Sequence below describes the harness once it lands; treat it
> as the contract for the upcoming PR, not as runnable today.

## Sequence

1. **Locate consensus**

   - Prefer `runs/vector/consensus_model.json`.
   - Else accept `--consensus <path>` argument.
   - Else accept `--pdf <path>` argument and generate consensus via
     the documented vector pipeline (see `OVERVIEW.md` §4.4).

2. **Run smoke harness**

   ```bash
   python scripts/smoke/smoke_skp_export.py \
     --consensus runs/vector/consensus_model.json \
     --out-dir runs/smoke/<timestamp> \
     --sketchup "C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe"
   ```

   The harness runs gates A→H in order:
   - A. Preparation (env, paths)
   - B. Acquire consensus
   - C. JSON structural validation
   - D. Preview PNG (top + axon, no SU)
   - E. Hash + skip-if-unchanged
   - F. Export .skp via tools.skp_from_consensus
   - G. Validate .skp (size, optional inspector)
   - H. Reports

3. **If first run / changed input**:
   - Review `runs/smoke/<timestamp>/sketchup_smoke_report.md`
   - If verdict OK and you want a visual check, run with `--open`:

     ```bash
     python scripts/smoke/smoke_skp_export.py ... --open
     ```

4. **If repeated run with same consensus**:
   - Smoke harness skips F automatically (cache by content hash).
   - Use `--force-skp` only when you need to re-export.

## When SketchUp is NOT opened

- During development loops with `--skip-skp`.
- When the consensus hash matches a previous successful export.
- When gate C (structural validation) fails.
- When gate D (preview generation) fails.

## When SketchUp IS opened

- First run with a given consensus, after C and D pass.
- Explicit `--force-skp`.
- After a fix to `consume_consensus.rb` or `skp_from_consensus.py`
  (the consume code is in the cache key, so the hash changes).

## Output

The smoke harness writes:
- `runs/smoke/<timestamp>/sketchup_smoke_report.json`
- `runs/smoke/<timestamp>/sketchup_smoke_report.md`
- `runs/smoke/<timestamp>/preview_top.png`
- `runs/smoke/<timestamp>/preview_axon.png`
- `runs/smoke/<timestamp>/model.skp` (if F ran)
- `runs/smoke/<timestamp>/_skp_cache.json` (cache marker for E)

`runs/` is gitignored — these are local artifacts.

## Visual checklist (when opening manually)

- [ ] No continuous white band on exterior walls
- [ ] Parapets do not cross walls
- [ ] Walls have proper material (no default-white)
- [ ] Floors have per-room colors
- [ ] Door arcs visible at openings
- [ ] Rooms within plant boundary
- [ ] No duplicated walls / z-fighting
- [ ] Scale looks compatible with real-world sizes

If any check fails: do NOT modify the exporter directly. Open an
issue or a discussion first; SketchUp changes go through the
sketchup-specialist review path.
