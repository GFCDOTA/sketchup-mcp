"""CubiCasa5K oracle — dev-time comparative opening detector.

Inference pipeline: SVG -> raster -> Hourglass (hg_furukawa_original) ->
44-channel segmentation -> extract Door/Window blobs from icon channels ->
emit pipeline-compatible `openings` JSON.

This is an oracle, not a production component. The pipeline core never
imports from this script. Output is compared against `observed_model.json`
via `scripts/compare_oracle.py`.

Usage:
    python scripts/run_cubicasa_oracle.py \\
        --svg tests/fixtures/svg/minimal_room.svg \\
        --out runs/oracle_minimal/oracle_openings.json \\
        [--weights vendor/CubiCasa5k/weights/model_best_val_loss_var.pkl] \\
        [--raster-size 512] \\
        [--device cpu|cuda]

Output schema (pipeline-compatible):
    {
      "source": "CubiCasa5K oracle",
      "weights_path": "...",
      "weights_sha256": "...",
      "input": {"svg": "...", "raster_size": [W, H]},
      "openings": [
        {
          "opening_id": "oracle-1",
          "page_index": 0,
          "orientation": "horizontal" | "vertical",
          "center": [x, y],
          "width": float,
          "wall_a": null,           # oracle cannot link to specific walls
          "wall_b": null,
          "kind": "door" | "window"
        }
      ]
    }

Torch is treated as an OPTIONAL dependency. If the vendor setup is
incomplete (no weights, no repo, no torch), the script raises with a clear
message pointing to vendor/CubiCasa5k/README.md.

Reference:
    https://github.com/CubiCasa/CubiCasa5k
    License: CC BY-NC 4.0 (non-commercial)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------- vendor layout ----------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = PROJECT_ROOT / "vendor" / "CubiCasa5k"
DEFAULT_WEIGHTS = VENDOR_DIR / "weights" / "model_best_val_loss_var.pkl"
VENDOR_REPO = VENDOR_DIR / "repo"  # optional clone of github.com/CubiCasa/CubiCasa5k

# Channel layout of the hg_furukawa_original model (44 classes total).
HEATMAP_COUNT = 21
ROOM_COUNT = 12
ICON_COUNT = 11

HEATMAPS_OFFSET = 0
ROOMS_OFFSET = HEATMAPS_OFFSET + HEATMAP_COUNT       # 21
ICONS_OFFSET = ROOMS_OFFSET + ROOM_COUNT             # 33

# Icon class indices (local to the 11 icon channels).
ICON_NO_ICON = 0
ICON_WINDOW = 1
ICON_DOOR = 2

# ImageNet normalisation (the upstream samples.ipynb uses this).
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# Blob filters (tuned for a 512x512 raster of a ~75 m2 plan).
MIN_BLOB_AREA_PX = 12           # smaller: noise; larger: miss small doors
DOOR_PROB_THRESHOLD = 0.40      # softmax probability for icon==Door
WINDOW_PROB_THRESHOLD = 0.40


# ---------- data classes ----------


@dataclass(frozen=True)
class OracleOpening:
    opening_id: str
    page_index: int
    orientation: str
    center: tuple[float, float]
    width: float
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "opening_id": self.opening_id,
            "page_index": self.page_index,
            "orientation": self.orientation,
            "center": [round(self.center[0], 3), round(self.center[1], 3)],
            "width": round(self.width, 3),
            "wall_a": None,
            "wall_b": None,
            "kind": self.kind,
        }


# ---------- setup checks ----------


def _fail_setup(reason: str) -> None:
    """Raise RuntimeError with a pointer to the vendor README."""
    raise RuntimeError(
        f"{reason}\n"
        f"See vendor/CubiCasa5k/README.md for the setup steps. "
        f"This is a dev-time oracle; the pipeline does not depend on it."
    )


def _require_weights(path: Path) -> Path:
    if not path.exists():
        _fail_setup(
            f"CubiCasa5K weights not found at {path}.\n"
            f"Download them manually (Google Drive ID "
            f"'1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK' — ~96 MB) and place the "
            f"file at {DEFAULT_WEIGHTS}."
        )
    return path


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _prepare_import_path() -> None:
    """Make `floortrans` importable by preferring the vendored repo clone.

    Falls through if the user installed CubiCasa5K globally via `pip install -e`.
    """
    if VENDOR_REPO.exists() and str(VENDOR_REPO) not in sys.path:
        sys.path.insert(0, str(VENDOR_REPO))


# ---------- SVG -> raster ----------


@dataclass(frozen=True)
class RasterTransform:
    """Describes the pixel-space -> SVG viewBox-space affine used when we
    rasterised the input. Applied to oracle centers/widths to emit openings
    in the SVG coordinate system (so GT and pipeline JSON compare directly).

    Invariants:
        vb_x = (px_x - offset_x) / scale
        vb_y = (px_y - offset_y) / scale
    """

    scale: float           # pixels per SVG user-unit (uniform)
    offset_x: float        # letterbox offset in pixels, x
    offset_y: float        # letterbox offset in pixels, y
    vb_min_x: float
    vb_min_y: float
    vb_width: float
    vb_height: float


def _read_svg_viewbox(svg_path: Path) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, width, height) for the SVG viewBox.

    Falls back to (0,0,width,height) if only width/height are given, and
    to (0,0,size,size) as a last resort.
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(str(svg_path)).getroot()
    except Exception:
        return (0.0, 0.0, 0.0, 0.0)

    vb = root.attrib.get("viewBox")
    if vb:
        parts = [float(x) for x in vb.replace(",", " ").split()]
        if len(parts) == 4:
            return tuple(parts)  # type: ignore[return-value]

    def _as_num(val: str | None) -> float:
        if not val:
            return 0.0
        return float("".join(c for c in val if c.isdigit() or c in ".-"))

    w = _as_num(root.attrib.get("width"))
    h = _as_num(root.attrib.get("height"))
    return (0.0, 0.0, w, h)


def svg_to_raster(
    svg_path: Path, size: int
) -> tuple["numpy.ndarray", RasterTransform]:  # type: ignore[name-defined]
    """Render SVG to a `size x size` RGB raster (numpy uint8, HxWx3) and
    return both the raster and the pixel->viewBox transform.

    Tries resvg-py first (pure Rust, no native DLL deps on Windows),
    then cairosvg (needs Cairo DLLs), finally Pillow (only works if
    the file is actually a raster with an SVG extension). None of these
    are mandatory for the rest of the project, so we import lazily and
    raise a clear error if every path fails.
    """
    import numpy as np

    vb_min_x, vb_min_y, vb_w, vb_h = _read_svg_viewbox(svg_path)

    # Path 1: resvg-py (preferred on Windows — ships self-contained)
    try:
        import resvg_py
        from PIL import Image
        import io

        # background='white' is essential: without it, resvg emits a
        # fully opaque canvas with RGB=(0,0,0) and alpha=255 everywhere,
        # because our synthetic plans are unfilled strokes on a
        # transparent canvas. A transparent->RGB convert via PIL collapses
        # to pure black and wipes out the wall strokes.
        png_bytes = bytes(
            resvg_py.svg_to_bytes(
                svg_path=str(svg_path),
                width=size,
                height=size,
                background="white",
            )
        )
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        rendered_w, rendered_h = img.size
        # resvg preserves aspect ratio when both width+height are passed,
        # so the resulting canvas may be letterbox-shaped. Pad to square on a
        # white background so the model sees the full plan at the requested
        # raster_size on both axes.
        if img.size != (size, size):
            bg = Image.new("RGB", (size, size), (255, 255, 255))
            off_x = (size - rendered_w) // 2
            off_y = (size - rendered_h) // 2
            bg.paste(img, (off_x, off_y))
            img = bg
        else:
            off_x = 0
            off_y = 0
        # scale: pixels per SVG user-unit. Uniform (aspect preserved).
        if vb_w > 0 and vb_h > 0:
            scale = min(rendered_w / vb_w, rendered_h / vb_h)
        else:
            scale = 1.0
        transform = RasterTransform(
            scale=scale,
            offset_x=float(off_x),
            offset_y=float(off_y),
            vb_min_x=vb_min_x,
            vb_min_y=vb_min_y,
            vb_width=vb_w,
            vb_height=vb_h,
        )
        return np.array(img), transform
    except ImportError:
        pass
    except Exception:
        # resvg may choke on exotic features — fall through
        pass

    # Path 2: cairosvg (needs native Cairo; usually unavailable on vanilla Windows)
    try:
        import cairosvg
        from PIL import Image
        import io

        png_bytes = cairosvg.svg2png(
            url=str(svg_path), output_width=size, output_height=size
        )
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        # cairosvg forces exactly size x size; if the user gave a non-square
        # viewBox this stretches — document by recording the x/y scales
        # separately isn't supported by our uniform-scale RasterTransform,
        # so we record the geometric-mean scale and accept some mapping
        # error on the minor axis.
        if vb_w > 0 and vb_h > 0:
            scale = (size / vb_w + size / vb_h) / 2.0
        else:
            scale = 1.0
        return np.array(img), RasterTransform(
            scale=scale, offset_x=0.0, offset_y=0.0,
            vb_min_x=vb_min_x, vb_min_y=vb_min_y,
            vb_width=vb_w, vb_height=vb_h,
        )
    except ImportError:
        pass
    except Exception:
        pass

    # Path 3: Pillow-only path (works only if file is actually raster)
    try:
        from PIL import Image

        img = Image.open(svg_path).convert("RGB").resize((size, size))
        return np.array(img), RasterTransform(
            scale=1.0, offset_x=0.0, offset_y=0.0,
            vb_min_x=0.0, vb_min_y=0.0,
            vb_width=float(size), vb_height=float(size),
        )
    except Exception as exc:
        _fail_setup(
            f"Could not rasterise {svg_path}: {exc}. "
            f"Install resvg-py ('pip install resvg-py') or cairosvg "
            f"('pip install cairosvg' — needs Cairo DLLs on Windows), "
            f"or convert the SVG to PNG first and pass it as --svg."
        )
        raise  # unreachable, _fail_setup raises


# ---------- CubiCasa5K model loading ----------


def load_cubicasa_model(weights_path: Path, device: str):
    """Load hg_furukawa_original with CubiCasa5K pretrained weights.

    Returns (model, torch_device). Raises RuntimeError with guidance if
    imports fail.
    """
    _prepare_import_path()

    try:
        import torch
    except ImportError:
        _fail_setup("PyTorch is not installed. Run `pip install torch torchvision`.")
        raise  # unreachable

    try:
        from floortrans.models import get_model
    except ImportError:
        _fail_setup(
            f"Could not import `floortrans.models`. Clone the CubiCasa5K repo "
            f"into {VENDOR_REPO} ('git clone https://github.com/CubiCasa/"
            f"CubiCasa5k {VENDOR_REPO}'), or install it globally with "
            f"'pip install -e .' from inside the cloned repo."
        )
        raise  # unreachable

    n_classes = HEATMAP_COUNT + ROOM_COUNT + ICON_COUNT  # 44

    # Match the upstream samples.ipynb recipe: instantiate with 51 heads,
    # then override the final conv + upsample to the 44-head config used
    # by the published checkpoint.
    #
    # `hg_furukawa_original.init_weights()` hardcodes a relative path to
    # 'floortrans/models/model_1427.pth', which exists at the root of the
    # cloned repo. We chdir into the vendor repo for the duration of
    # `get_model` so that relative lookup resolves against the repo root.
    import os
    prev_cwd = os.getcwd()
    try:
        if VENDOR_REPO.exists():
            os.chdir(str(VENDOR_REPO))
        model = get_model("hg_furukawa_original", 51)
    finally:
        os.chdir(prev_cwd)
    model.conv4_ = torch.nn.Conv2d(256, n_classes, bias=True, kernel_size=1)
    model.upsample = torch.nn.ConvTranspose2d(
        n_classes, n_classes, kernel_size=4, stride=4
    )

    checkpoint = torch.load(weights_path, map_location="cpu", weights_only=False)
    state = checkpoint.get("model_state", checkpoint)
    state = {k.replace("module.", ""): v for k, v in state.items()}

    try:
        model.load_state_dict(state, strict=True)
    except RuntimeError as exc:
        # Don't silently swallow — report explicitly which keys mismatch.
        # Then try again non-strict so the user at least gets a run.
        print(f"[oracle] strict load failed: {exc}", file=sys.stderr)
        print("[oracle] retrying with strict=False (some weights ignored)", file=sys.stderr)
        model.load_state_dict(state, strict=False)

    torch_device = torch.device(device)
    model = model.to(torch_device).eval()
    return model, torch_device


# ---------- inference ----------


def run_inference(model, torch_device, rgb: "numpy.ndarray"):  # type: ignore[name-defined]
    """Run the Hourglass on an RGB image and return the 44-channel output
    cropped back to the input resolution.
    """
    import numpy as np
    import torch
    import cv2

    h, w = rgb.shape[:2]

    # Pad to the next multiple of 32 (hourglass requirement).
    pad_h = (32 - h % 32) % 32
    pad_w = (32 - w % 32) % 32
    if pad_h or pad_w:
        padded = cv2.copyMakeBorder(rgb, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
    else:
        padded = rgb

    normalized = padded.astype(np.float32) / 255.0
    normalized = (normalized - np.array(IMAGENET_MEAN)) / np.array(IMAGENET_STD)
    chw = np.transpose(normalized, (2, 0, 1))[None, ...].astype(np.float32)
    batch = torch.from_numpy(chw).to(torch_device)

    with torch.no_grad():
        out = model(batch)  # (1, 44, 4*H_padded, 4*W_padded)

    # The model emits 4x upsampled predictions; downsample back to the
    # padded raster size so every pixel in `rgb` has one probability vector.
    _, c, oh, ow = out.shape
    if (oh, ow) != padded.shape[:2]:
        out = torch.nn.functional.interpolate(
            out, size=padded.shape[:2], mode="bilinear", align_corners=False
        )

    # Crop padding back off.
    return out[0, :, :h, :w].detach().cpu().numpy()


def _px_to_vb(
    px_x: float, px_y: float, transform: RasterTransform | None
) -> tuple[float, float]:
    """Map pixel-space point back to SVG viewBox-space."""
    if transform is None or transform.scale <= 0:
        return (px_x, px_y)
    vb_x = (px_x - transform.offset_x) / transform.scale + transform.vb_min_x
    vb_y = (px_y - transform.offset_y) / transform.scale + transform.vb_min_y
    return (vb_x, vb_y)


def _px_to_vb_length(px_len: float, transform: RasterTransform | None) -> float:
    """Map pixel length back to SVG viewBox user units."""
    if transform is None or transform.scale <= 0:
        return px_len
    return px_len / transform.scale


def extract_openings_from_output(
    output: "numpy.ndarray",  # type: ignore[name-defined]
    page_index: int = 0,
    transform: RasterTransform | None = None,
) -> list[OracleOpening]:
    """Convert the 44-channel output into pipeline-compatible openings.

    We look at the icon logits (channels 33..43), softmax across the 11
    icon classes, and read the Door (local=2) and Window (local=1) channels.
    Each channel is thresholded into a binary mask, blobbed with
    cv2.findContours, and each blob becomes one opening record.

    If `transform` is provided, centers and widths are mapped back from
    pixel space to the SVG viewBox coordinate space so oracle output
    shares units with `observed_model.json` and GT YAML.
    """
    import numpy as np
    import cv2

    icons_logits = output[ICONS_OFFSET : ICONS_OFFSET + ICON_COUNT]  # (11, H, W)

    # Softmax across the icon axis (channel 0).
    e = np.exp(icons_logits - icons_logits.max(axis=0, keepdims=True))
    icons_probs = e / e.sum(axis=0, keepdims=True)

    door_prob = icons_probs[ICON_DOOR]
    window_prob = icons_probs[ICON_WINDOW]

    openings: list[OracleOpening] = []
    counter = 1

    for kind, prob_map, thresh in (
        ("door", door_prob, DOOR_PROB_THRESHOLD),
        ("window", window_prob, WINDOW_PROB_THRESHOLD),
    ):
        mask = (prob_map > thresh).astype(np.uint8) * 255
        if mask.sum() == 0:
            continue

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < MIN_BLOB_AREA_PX:
                continue

            x, y, bw, bh = cv2.boundingRect(contour)
            cx_px = x + bw / 2.0
            cy_px = y + bh / 2.0

            # Longer axis determines orientation; width = longer axis length.
            if bw >= bh:
                orientation = "horizontal"
                width_px = float(bw)
            else:
                orientation = "vertical"
                width_px = float(bh)

            cx_vb, cy_vb = _px_to_vb(cx_px, cy_px, transform)
            width_vb = _px_to_vb_length(width_px, transform)

            openings.append(
                OracleOpening(
                    opening_id=f"oracle-{counter}",
                    page_index=page_index,
                    orientation=orientation,
                    center=(cx_vb, cy_vb),
                    width=width_vb,
                    kind=kind,
                )
            )
            counter += 1

    return openings


# ---------- CLI ----------


def run(
    svg_path: Path,
    out_path: Path,
    weights_path: Path,
    raster_size: int,
    device: str,
    page_index: int = 0,
) -> dict[str, Any]:
    """End-to-end oracle run. Returns the JSON-serialisable result dict."""
    _require_weights(weights_path)
    sha256 = _compute_sha256(weights_path)

    rgb, transform = svg_to_raster(svg_path, raster_size)
    model, torch_device = load_cubicasa_model(weights_path, device)
    output = run_inference(model, torch_device, rgb)
    openings = extract_openings_from_output(
        output, page_index=page_index, transform=transform,
    )

    payload: dict[str, Any] = {
        "source": "CubiCasa5K oracle",
        "weights_path": str(weights_path),
        "weights_sha256": sha256,
        "input": {
            "svg": str(svg_path),
            "raster_size": [raster_size, raster_size],
            "device": device,
            "viewbox": [
                transform.vb_min_x,
                transform.vb_min_y,
                transform.vb_width,
                transform.vb_height,
            ],
            "px_per_unit": transform.scale,
            "letterbox_offset_px": [transform.offset_x, transform.offset_y],
        },
        "openings": [o.to_dict() for o in openings],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--svg", required=True, type=Path,
        help="Path to an SVG (or PNG) floor plan.",
    )
    parser.add_argument(
        "--out", required=True, type=Path,
        help="Where to write oracle_openings.json.",
    )
    parser.add_argument(
        "--weights", type=Path, default=DEFAULT_WEIGHTS,
        help=f"CubiCasa5K checkpoint. Defaults to {DEFAULT_WEIGHTS}.",
    )
    parser.add_argument(
        "--raster-size", type=int, default=512,
        help="Side length of the intermediate raster (square). Default 512.",
    )
    parser.add_argument(
        "--device", default="cpu", choices=("cpu", "cuda"),
        help="Torch device. 'cuda' requires a GPU + CUDA-enabled torch build.",
    )
    parser.add_argument(
        "--page-index", type=int, default=0,
        help="page_index field on emitted openings (multi-page PDFs).",
    )

    args = parser.parse_args(argv)

    try:
        payload = run(
            svg_path=args.svg,
            out_path=args.out,
            weights_path=args.weights,
            raster_size=args.raster_size,
            device=args.device,
            page_index=args.page_index,
        )
    except RuntimeError as exc:
        print(f"[oracle] setup error: {exc}", file=sys.stderr)
        return 2

    print(f"[oracle] wrote {args.out} ({len(payload['openings'])} openings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
