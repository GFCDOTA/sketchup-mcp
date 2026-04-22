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

```bash
cd vendor/CubiCasa5k/

# 1. Clone the official repo (source code for the model architecture)
git clone https://github.com/CubiCasa/CubiCasa5k repo

# 2. Download pretrained weights (~96 MB, from Google Drive)
pip install --user gdown
gdown --id 1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK -O weights/model_best_val_loss_var.pkl

# 3. Install PyTorch (CPU is fine for oracle use; GPU makes inference ~10x faster)
pip install torch torchvision

# 4. Install remaining deps used by our script
pip install scikit-image scipy opencv-python-headless cairosvg Pillow
```

## 4. Setup (Windows PowerShell)

```powershell
cd vendor/CubiCasa5k/

# 1. Clone the official repo
git clone https://github.com/CubiCasa/CubiCasa5k repo

# 2. Download pretrained weights
pip install --user gdown
gdown --id 1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK -O weights/model_best_val_loss_var.pkl

# 3. PyTorch. CPU-only:
pip install torch torchvision
# Or with CUDA 12.1:
#   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# 4. Script deps
pip install scikit-image scipy opencv-python-headless cairosvg Pillow
```

> `cairosvg` requires Cairo native libs on Windows. If install/runtime fails,
> the oracle script falls back to rasterising SVGs via the pipeline's own
> `ingest/render` path or via Pillow. See the script's help text.

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

Once weights are in place:

```bash
# From project root
python scripts/run_cubicasa_oracle.py \
    --svg tests/fixtures/svg/minimal_room.svg \
    --out runs/oracle_minimal/oracle_openings.json
```

Output JSON (pipeline-compatible opening schema):

```json
{
  "source": "CubiCasa5K oracle",
  "weights_path": "vendor/CubiCasa5k/weights/model_best_val_loss_var.pkl",
  "weights_sha256": "<first-run-computed>",
  "input": {"svg": "tests/fixtures/svg/minimal_room.svg", "raster_size": [512, 512]},
  "openings": [
    {
      "opening_id": "oracle-1",
      "page_index": 0,
      "orientation": "horizontal",
      "center": [200.0, 215.0],
      "width": 46.0,
      "wall_a": null,
      "wall_b": null,
      "kind": "door"
    }
  ]
}
```

Note `wall_a` / `wall_b` are `null` for oracle records. CubiCasa doesn't
output wall IDs — it outputs segmentation masks — so we can't link each
opening to two specific walls. `scripts/compare_oracle.py` ignores those
fields when comparing against pipeline output; matching is purely by
center + orientation + width.

---

## 8. Performance expectations

| Hardware | Inference time per 512x512 plan |
|---|---|
| CPU (i5 / Ryzen 5) | 5-15 s |
| GPU (any modern CUDA) | 0.2-2 s |

First run takes a few extra seconds for torch to import + model to load.
Subsequent runs with the `WallMaskOracle` singleton cached in a script
hitting multiple plans will be faster.

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
You skipped step 1 (cloning the repo). Either clone `repo/` here or add the
CubiCasa5K folder to `PYTHONPATH` before running the script.

### Weights download fails with "Cannot retrieve the public link"
Google Drive sometimes rate-limits anonymous downloads of large files. Use
a browser with a Google account to open
<https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK> and
place the downloaded `.pkl` in `weights/` manually.

### `torch.load` fails with pickle unpickling error
Newer torch versions default to `weights_only=True`. Our script passes
`weights_only=False` explicitly because CubiCasa saves a full checkpoint
dict, not just a state_dict. If you are calling `torch.load` yourself,
use the same flag.

### Oracle output has **zero** openings on a plan you know has doors
- Check the rendered raster first (`runs/<name>/oracle_raster.png`).
  If the walls aren't visible, the SVG-to-raster step lost contrast.
- Try raising `--raster-size` from 512 to 1024 to recover small doors.
- Confidence thresholds live in `scripts/run_cubicasa_oracle.py`
  (`DOOR_PROB_THRESHOLD`, `WINDOW_PROB_THRESHOLD`). Lower to 0.3 if needed.
