# CubiCasa5K oracle — manual setup

This folder vendors the pretrained CubiCasa5K Hourglass floorplan model so we
can use it as a **dev-time comparative oracle** against the pipeline's own
openings detector. It is **not** a production fallback: the model is loaded
manually by scripts, never by `main.py` or any service in the pipeline core.

> Comparative oracle only: run it on a plan, compare `oracle_openings.json`
> against `observed_model.json`, get a second opinion on where doors/windows
> probably are. Divergences are clues for debugging the pipeline, not
> authoritative output.

---

## 1. What gets downloaded

| Thing | Size | Where |
|---|---|---|
| CubiCasa5K repo (source) | ~5 MB | `vendor/CubiCasa5k/repo/` (gitignored) |
| Pretrained weights `model_best_val_loss_var.pkl` | ~96 MB | `vendor/CubiCasa5k/weights/` (gitignored) |
| PyTorch + torchvision (runtime deps) | ~500 MB | your Python env |

Total: ~600 MB on disk if you go through with everything.

---

## 2. License — read first

CubiCasa5K code and weights are published under
**Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**.

> **Non-commercial use only.** If you use this oracle in a commercial
> product, you need to get explicit permission from CubiCasa. Using it
> locally to debug your own pipeline (dev-time oracle) is fine; shipping
> the weights or their output as part of a paid product is not.

When in doubt, read the official license:
<https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE>

---

## 3. Setup (Linux / macOS / WSL)

The clone + weights download is automated by a single script. Run it from the
project root (`microservices/plan-extract-v2/`):

```bash
# From microservices/plan-extract-v2 root
python scripts/oracle/cubicasa_download.py
# Optional: --force re-runs even if already done
```

The script is idempotent: it will skip steps that are already complete unless
`--force` is passed. It requires `git` and `gdown` on `PATH`; install them
beforehand:

```bash
pip install --user gdown
# (git is assumed to be available on most dev machines)
```

You will also need PyTorch + a few small image libs for the inference script
(`scripts/oracle/cubicasa.py`):

```bash
# CPU is fine for oracle use; GPU makes inference ~10x faster
pip install torch torchvision
pip install jsonschema opencv-python-headless Pillow
```

## 4. Setup (Windows PowerShell)

```powershell
# From microservices/plan-extract-v2 root
python scripts/oracle/cubicasa_download.py
# Optional: --force re-runs even if already done
```

Prerequisites:

```powershell
pip install --user gdown
# git is assumed to be on PATH; install from https://git-scm.com/downloads if not.

# PyTorch. CPU-only:
pip install torch torchvision
# Or with CUDA 12.1:
#   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

pip install jsonschema opencv-python-headless Pillow
```

---

## 5. Weights metadata

| Field | Value |
|---|---|
| Filename | `model_best_val_loss_var.pkl` |
| Google Drive ID | `1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK` |
| Direct URL | <https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK> |
| Expected size | ~96 MB (exact bytes may vary by export) |
| SHA256 | **Not published upstream.** After your first successful download, compute it with `sha256sum weights/model_best_val_loss_var.pkl` and record the value in the `weights_sha256` field of `oracle_openings.json` so future runs can detect silent corruption. |

CubiCasa5K does not publish a canonical checksum for the weights, so we
treat the first successful inference run as our pinning event — whatever
SHA256 that file had is what we expect from now on. If a future download
produces a different hash, investigate before trusting output.

---

## 6. Architecture quick reference

The Hourglass (`hg_furukawa_original`) network outputs **44 channels** at 4x
the input resolution, split as:

| Range | Count | Meaning |
|---|---|---|
| `0:21` | 21 | heatmaps for wall-junctions / icon-corners / opening-endpoints |
| `21:33` | 12 | room-class segmentation (softmax across channels) |
| `33:44` | 11 | icon-class segmentation (softmax across channels) |

### Icon classes (channels 33-43)

| Local index | Global channel | Class |
|---|---|---|
| 0 | 33 | No Icon |
| **1** | **34** | **Window** |
| **2** | **35** | **Door** |
| 3 | 36 | Closet |
| 4 | 37 | Electrical Applience |
| 5 | 38 | Toilet |
| 6 | 39 | Sink |
| 7 | 40 | Sauna Bench |
| 8 | 41 | Fire Place |
| 9 | 42 | Bathtub |
| 10 | 43 | Chimney |

Our oracle script reads channels 34 (window) and 35 (door), runs an
argmax softmax across `icons[0..10]`, groups pixels into blobs via
`cv2.findContours`, and converts each blob into an `Opening` record in the
pipeline's schema.

### Preprocessing

1. Convert input to **RGB** (the model expects 3 channels).
2. Pad height and width up to the next multiple of **32** (Hourglass
   requires this; `copyMakeBorder` with `BORDER_REFLECT`).
3. Normalise to float32 `[0,1]` and apply **ImageNet mean/std**:
   - mean = `[0.485, 0.456, 0.406]`
   - std  = `[0.229, 0.224, 0.225]`
4. Transpose to CHW, add batch dim, send to device.
5. `model(x)` -> `(1, 44, 4*H, 4*W)`. The 4x upsampling is inside `model.upsample`.
6. Crop the 4x result back to the original input resolution for geometry.

---

## 7. Run the oracle

Once `cubicasa_download.py` has completed:

```bash
# From microservices/plan-extract-v2 root
python scripts/oracle/cubicasa.py --pdf planta_74.pdf --out runs/cubicasa_p74
# Optional: --raster-size 512 (default), 1024
# Optional: --device cpu (default) or cuda
```

The output is `runs/cubicasa_p74/cubicasa_observed.json`, which is
**schema-compliant against `docs/schema/observed_model.schema.json`**
(the script validates the payload before writing; on failure it writes
`cubicasa_observed.invalid.json` instead — see section 10).

Unlike the previous oracle (which only emitted a partial `oracle_openings.json`
opening list), the new payload is a full `observed_model` with walls,
junctions, rooms, and openings — the same shape the pipeline produces. Walls
carry `source: "cubicasa"` so they're distinguishable from pipeline walls if
you merge runs. Openings have `wall_a` and `wall_b` set to empty strings
(`""`) because CubiCasa outputs segmentation masks, not wall topology — there
is no wall ID to link to.

Example payload (truncated):

```json
{
  "schema_version": "2.2.0",
  "run_id": "<hex>",
  "source": {
    "filename": "planta_74.pdf",
    "source_type": "raster",
    "page_count": 1,
    "sha256": "<pdf-sha256>"
  },
  "walls": [
    {
      "wall_id": "cubicasa-wall-1",
      "parent_wall_id": "cubicasa-wall-1",
      "page_index": 0,
      "start": [120.0, 80.0],
      "end": [320.0, 80.0],
      "thickness": 4.0,
      "orientation": "horizontal",
      "source": "cubicasa",
      "confidence": 0.95
    }
  ],
  "junctions": [
    {"junction_id": "cubicasa-j-1", "point": [120.0, 80.0], "degree": 2, "kind": "pass_through"}
  ],
  "rooms": [
    {
      "room_id": "cubicasa-room-1",
      "polygon": [[120.0, 80.0], [320.0, 80.0], [320.0, 215.0], [120.0, 215.0]],
      "area": 27000.0,
      "centroid": [220.0, 147.5]
    }
  ],
  "openings": [
    {
      "opening_id": "cubicasa-opening-1",
      "page_index": 0,
      "orientation": "horizontal",
      "center": [200.0, 215.0],
      "width": 46.0,
      "wall_a": "",
      "wall_b": "",
      "kind": "door"
    }
  ],
  "peitoris": []
}
```

`wall_a` / `wall_b` are empty strings rather than null because the schema
requires string types on opening endpoints. A future `compare_oracles.py`
should ignore those fields when matching pipeline vs. oracle openings; match
by center + orientation + width.

---

## 8. Performance expectations

| Hardware | Inference time per 512x512 plan |
|---|---|
| CPU (i5 / Ryzen 5) | 5-15 s |
| GPU (any modern CUDA) | 0.2-2 s |

`scripts/oracle/cubicasa.py` defaults to `--device cpu`. Pass `--device cuda`
to run on GPU when a CUDA-enabled torch build is available; expect a ~10x
speedup on inference. First run takes a few extra seconds for torch to import
plus the model to load.

---

## 9. Limitations

- **Raster input only.** The model was trained on PNG-like raster floor
  plans. We render SVG to a 512x512 raster before running the model, which
  means the oracle is indirect for SVG-native plans. Choose the raster
  resolution carefully: too small and tiny doors vanish; too big and you
  pad beyond training distribution.
- **No wall-association.** Opening has no `wall_a` / `wall_b`.
- **CC BY-NC 4.0.** Non-commercial only (see section 2).
- **No canonical SHA256.** The first download is your pin. Corruption
  detection requires you to run `sha256sum` once after the first good run.
- **Model resolution.** CubiCasa's training plans are typically 500-1500
  px per side. Very small (< 200 px) or very large (> 4000 px) inputs may
  produce degraded segmentation; consider rescaling.

---

## 10. Troubleshooting

### `ImportError: cannot import floortrans.models`
You skipped or interrupted `cubicasa_download.py`. Run it again — it will
clone the upstream repo into `vendor/CubiCasa5k/repo/`. If you cloned
manually somewhere else, either move the clone to that path or set
`PYTHONPATH` to include your clone before running `cubicasa.py`.

### After running `cubicasa_download.py`, weights download fails with "Cannot retrieve the public link"
Google Drive sometimes rate-limits anonymous downloads of large files. The
download script will report a non-zero exit from `gdown` in this case. Open
<https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK> in a
browser logged into a Google account, download the `.pkl` manually, and
place it at:

```
vendor/CubiCasa5k/weights/model_best_val_loss_var.pkl
```

Then re-run `cubicasa_download.py` — it will detect the existing weights file
and skip the download step (or pass `--force` to redo it).

If the file gets saved with HTML quota-exceeded content (the size will be
well under 50 MB), the script's size sanity-check rejects it; delete and
retry.

### `torch.load` fails with pickle unpickling error
Newer torch versions default to `weights_only=True`. Our script passes
`weights_only=False` explicitly because CubiCasa saves a full checkpoint
dict, not just a state_dict. If you are calling `torch.load` yourself,
use the same flag.

### Output JSON validation fails
`cubicasa.py` validates its payload against
`docs/schema/observed_model.schema.json` before writing. If validation
fails, the script writes `cubicasa_observed.invalid.json` instead of the
canonical filename and exits with code 3. The validation error (with the
JSON path of the offending field) is printed to stderr — read it to see
which field is non-conforming.

### Oracle output has **zero** openings on a plan you know has doors
- Try raising `--raster-size` from 512 to 1024 to recover small doors.
- Confidence thresholds live as module-level constants in
  `scripts/oracle/cubicasa.py` (`DOOR_PROB_THRESHOLD`,
  `WINDOW_PROB_THRESHOLD`). Lower to 0.3 if needed.
- Re-run with `--device cuda` if available — CPU + small raster is the
  slowest combination and tends to make iteration painful.

---

## 11. Compare with the pipeline (3-way diff)

Once you have both `runs/<run>/observed_model.json` (pipeline output) and
`runs/cubicasa_<run>/cubicasa_observed.json` (this oracle's output), run
the comparison tool to get counts deltas, cross-signal flags and an
automatic narrative interpretation:

```bash
python scripts/oracle/compare_oracles.py \
    --pipeline runs/openings_refine_final \
    --cubicasa runs/cubicasa_p74 \
    --out runs/openings_refine_final/oracle_comparison.json
# Optional: --png to also render an oracle_comparison.png side-by-side
```

The JSON includes `counts`, `deltas`, `cross_signal.rooms_only_in_pipeline`,
`cross_signal.openings_only_in_pipeline` (anything in pipeline whose
centroid doesn't match a CubiCasa centroid within `--min-match-distance-px`,
default 30 px) and a one-paragraph `interpretation`.

If `oracle_diagnosis_llm.json` exists in the pipeline run dir (output of
`scripts/oracle/llm_architect.py`), it is auto-discovered and folded into
the same comparison.
