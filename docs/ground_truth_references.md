# Ground Truth References — public datasets survey

> Companion to `docs/ground_truth_v1.md`. Short, opinionated.
> The single rule: **Do not treat Google Images, Google 3D
> Warehouse, or scraped Pinterest content as ground truth.** They
> are visual reference at most.

---

## Datasets evaluated

### CubiCasa5K

- **Content**: ~5,000 floor-plan raster images, semantic
  segmentation masks for walls / doors / windows / rooms with
  per-pixel labels, plus svg/json with vectorial annotations.
- **License**: CC BY-NC 4.0 — research / non-commercial.
- **Use here**: BENCHMARK + REFERENCE. Already tracked as a
  potential P3 work item in `.ai_bridge/TODO_NEXT.md` and
  `docs/ROADMAP.md` FASE 4 ("DL Wall Oracle"). Useful to compare
  this pipeline's wall/room detection against a labelled corpus
  on plans whose stylistic conventions overlap.
- **Risk**: NC license blocks production use. Treat as eval only.
- **Not adequate for**: shipping CubiCasa labels into commercial
  output, redistributing the masks, fine-tuning a model that this
  project ships.

### FloorPlanCAD

- **Content**: ~10,000 floorplan CAD files with per-element
  semantic class labels (walls / doors / windows / rooms /
  furniture).
- **License**: research-only release.
- **Use here**: REFERENCE. CAD-side coverage where CubiCasa is
  raster-side. The richer per-element classes match this
  project's vector pipeline.
- **Risk**: same as CubiCasa — not for shipping.

### Structured3D

- **Content**: ~3,500 photo-realistic synthetic apartments,
  geometry + semantic labels + textures.
- **License**: research-only.
- **Use here**: NOT ADEQUATE for v1. The synthetic 3D apartments
  are higher-fidelity than this project's 2D-vector PDF input;
  the geometry surface is too different to compare without a
  big projection step.
- **Risk**: hours-of-work projection layer for marginal value.
  Skip.

### LayoutNet / RPLAN / Raster-to-Vector / etc.

- Multiple academic datasets exist for floorplan parsing.
- **Status**: not surveyed for v1. Open for v2 once multi-PDF
  corpus + CubiCasa eval pipeline are wired.

### Google Images / 3D Warehouse / Pinterest scrapes

- **Content**: arbitrary internet imagery, no labels, no licensing
  guarantees, no schema, no scale anchor.
- **Use here**: **NOT ADEQUATE FOR GROUND TRUTH.** Visual reference
  at most, when a human annotator is debugging a single planta and
  wants to understand "what does a typical Brazilian
  apartamento-de-2-suites look like". Even then, the human
  authors `expected_model.json` from architectural priors, not
  from the image.
- **Risk**: license unknown for every individual asset; ground
  truth derived from these is legally fragile and methodologically
  wrong (no anchor, no schema, no audit trail).

---

## Decision matrix

| Source | License | Schema | Scale | Use as v1 GT? | Use as benchmark? |
|---|---|---|---|---|---|
| Manual `expected_model.json` (this repo) | this repo | yes (v1.0) | yes | **YES** | n/a |
| `ground_truth/<plant>_micro.json` | this repo | yes (1.0) | yes | yes (subset) | yes (per-room) |
| `tests/baselines/<plant>.json` | this repo | yes (1.0) | partial | as baseline only | yes (regression) |
| CubiCasa5K | CC BY-NC | yes | yes | NO (NC) | yes |
| FloorPlanCAD | research-only | yes | yes | NO | yes |
| Structured3D | research-only | yes | yes | NO (3D mismatch) | maybe v3+ |
| Google Images | unknown | no | no | NO | NO |
| 3D Warehouse | unknown | no | no | NO | NO |

---

## Recommended path forward

1. v1 stays in-repo, manually authored, as it is now.
2. Do NOT pull external dataset content into ground_truth/. Keep
   that directory's provenance 100 % "authored by humans on this
   project".
3. When DL oracle work starts (FASE 4 of `docs/ROADMAP.md`),
   CubiCasa5K weights ship as `vendor/CubiCasa5K/` per the
   existing pattern; the eval is a SEPARATE pipeline that reads
   CubiCasa labels and produces a comparison report — never
   write CubiCasa labels into `ground_truth/`.
4. Synthetic GT (the planned `expected_model.json -> render PDF
   -> pipeline -> compare` cycle, see `docs/ground_truth_v1.md`)
   is preferred over scraping more real plants; the synthetic
   path generates ground truth that is provably correct by
   construction.

---

## See also

- `docs/ground_truth_v1.md` — the v1 itself
- `docs/ROADMAP.md` FASE 4 — DL Wall Oracle plan
- `vendor/CubiCasa5k/README.md` — current CubiCasa5K vendor stub
