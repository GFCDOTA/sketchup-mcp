"""Renderiza overlay (mask em preto + walls extraidas em vermelho +
junctions em azul) pra cada prototipo.

Uso: ``python -m renderers.proto_overlays``.

Migrated from repo root ``render_proto_overlays.py`` (2026-05-08) per
``docs/architecture/target_repo_architecture.md`` step 5.
"""
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROTOS = ["p1_components", "p2_thickness", "p3_kmeans", "p4_roi"]
DEFAULT_RUN_DIR = Path("runs/proto")


def _load_history_register():
    if os.environ.get("PNG_HISTORY_DISABLE"):
        return None
    try:
        # Migrated from repo root (2026-05-08); tools/ is one level up now.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
        from png_history import register as _history_register
        return _history_register
    except Exception as e:
        print(f"[png_history skipped] {e}")
        return None


def render(run_dir: Path = DEFAULT_RUN_DIR, protos: list[str] | None = None) -> list[Path]:
    """Render overlay PNGs for each prototype run under ``run_dir``.

    Returns the list of generated overlay paths.
    """
    proto_names = list(protos) if protos else list(PROTOS)
    history_register = _load_history_register()

    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except Exception:
        font = ImageFont.load_default()

    outputs: list[Path] = []
    for name in proto_names:
        mask_png = run_dir / f"{name}_mask.png"
        proto_run = run_dir / f"{name}_run"
        obs = json.loads((proto_run / "observed_model.json").read_text(encoding="utf-8"))
        walls = obs["walls"]
        juncs = obs["junctions"]
        sc = obs["scores"]

        # mask como base, branca ao fundo
        mask = Image.open(mask_png).convert("L")
        base = Image.new("RGB", mask.size, "white")
        # mask preta (paredes) sobre branco
        base.paste((0, 0, 0), mask=Image.eval(mask, lambda v: 80 if v > 0 else 0))
        d = ImageDraw.Draw(base)

        # walls em vermelho
        for w in walls:
            d.line([tuple(w["start"]), tuple(w["end"])], fill=(220, 38, 38),
                   width=max(2, int(w.get("thickness", 4) / 2)))
        # junctions em azul
        for j in juncs:
            cx, cy = j["point"]
            col = (220, 38, 38) if j.get("degree", 0) >= 3 else (37, 99, 235)
            r = 5
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

        # legenda topo
        d.rectangle([0, 0, base.width, 50], fill=(255, 255, 255, 230))
        d.text((10, 10),
               f"{name}  walls={len(walls)} juncs={len(juncs)} rooms={len(obs['rooms'])} "
               f"geom={sc['geometry']} topo={sc['topology']}",
               fill="black", font=font)

        base.thumbnail((1200, 1200))
        out = run_dir / f"{name}_overlay.png"
        base.save(out)
        print(f"wrote {out}")
        outputs.append(out)

        if history_register:
            try:
                history_register(out, kind="proto_overlay",
                                 source={"consensus": proto_run / "observed_model.json"},
                                 generator="renderers.proto_overlays",
                                 params={"proto": name})
            except Exception as e:
                print(f"[png_history skipped {name}] {e}")

    return outputs


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    run_dir = Path(args[0]) if args else DEFAULT_RUN_DIR
    render(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
