# planta_74 — .skp correction journey (learning kept, binaries discarded)

The `.skp` is a **regenerable build output** (`consensus.json` + builder = the
real source of truth). So the value of every superseded build is the *why it was
wrong*, captured here; the heavy binaries are discarded (scratch in `runs/` is
gitignored + regenerable; tracked evidence `.skp` removed via `git rm` =
recoverable from history). The **current canonical** is kept:
`artifacts/review/planta_74/canonical_20260531/final/model.skp`.

Regenerate any stage: `PT_TO_M=0.0252 .venv/Scripts/python.exe
tools/build_plan_shell_skp.py fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json --out runs/planta_74/<x>/model.skp --force-skp`.

## The chain (each row = a discarded .skp + why it was superseded)

| stage (.skp) | what it was | why WRONG / superseded | ref |
|---|---|---|---|
| `planta_74.skp`, `*_stub_review`, `manual_validation_*`, `visual_oracle_bridge_*`, `visual_loop_current` | earliest builds | **scale wrong** (PT_TO_M 0.0352 ≈ 1.4× too big vs cotas 5.45/2.60/2.40); windows read as raw voids | scale_anchor report |
| `scale_fix_*/candidate.skp` | scale fixed via `ENV['PT_TO_M']=0.0252` | scale-axis only; representation still open | decision.md (scale_fix) |
| `runs/.../repr_glass` | GLASS_ALPHA=0.72 experiment | **FAIL_PARTIAL** — alpha can't make a thin edge-on pane read; balcony got more dominant. Reverted | — |
| `window_frame_20260530` | caixilho/frame on the windows | **WRONG: framed INVENTED windows on the wrong wall** — exposed the FP-031 bug. Reverted | LL-031 |
| `runs/.../placement_fix` | `find_wall_face` host-filter | killed the invented windows (`window_built=0`) but left no representation | — |
| `window_fix_20260530`, `runs/.../panel*` | windows as PANELS at the opening centre (aperture-first, panel fallback) | honest stopgap, but **surface bands, not see-through** — root cause (broken `opening→wall_id`) still there | LL-031 |
| `runs/.../gate`, `gate29` | overlay_diff sidecar + deterministic top camera | experiments folded into the builder (#2/#29) | — |
| `regen_candidate_20260531` | merged-consensus → windows = see-through **APERTURES** | Felipe VISUAL_REVIEW = IMPROVED → promoted. Superseded by canonical (which adds the glass fix) | LL-032/033 |

## Root causes that the chain converged on (the real learning)
1. **Scale**: anchor PT_TO_M to PDF cotas (0.0252), not the default 0.0352. (env override, no fixture mutation)
2. **Windows on the wrong wall** = broken `opening→wall_id` from **collinear wall fragmentation**. Fix = regenerate consensus: merge collinear segments + re-host (35→19 walls). Then windows carve as real apertures. (LL-032)
3. **BANHO 2 had the cutout but no glass** = the merged host wall (`m003`) is thicker (5.52pt) than the global (5.40pt), so the aperture pushpull stopped short → blind pocket. Fix = carve the **host wall's own thickness**. (commit 528e302)
4. **Process**: deterministic detectors (`opening_host_audit`, `overlay_diff`, `wall_overlap_audit`) catch the data bugs; **promotion to canonical + the visual look stay Felipe's call** (VISUAL_REVIEW). See LL-031..034.

Current canonical = regenerated 19-wall consensus + deterministic camera + 4 see-through window apertures (BANHO 2 glass fixed) + balcony.
</content>
