"""Renderiza overlay incluindo bridges em verde + openings em laranja.

Uso: ``python -m renderers.with_openings <run_dir> [<mask>]``.

Migrated from repo root ``render_with_openings.py`` (2026-05-08) per
``docs/architecture/target_repo_architecture.md`` step 5.
"""
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def render(run_dir: Path, mask: Path | None = None) -> Path:
    obs_path = run_dir / "observed_model.json"
    obs = json.loads(obs_path.read_text())
    walls = obs["walls"]
    juncs = obs["junctions"]
    openings = obs.get("openings", [])
    sc = obs["scores"]

    xs = [c for w in walls for c in (w["start"][0], w["end"][0])]
    ys = [c for w in walls for c in (w["start"][1], w["end"][1])]
    margin = 40
    min_x, min_y = min(xs) - margin, min(ys) - margin
    max_x, max_y = max(xs) + margin, max(ys) + margin
    width, height = int(max_x - min_x), int(max_y - min_y)

    base = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(base, "RGBA")
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except Exception:
        font = ImageFont.load_default()

    # walls — vermelho normais, verde bridges
    for w in walls:
        x1, y1 = w["start"][0] - min_x, w["start"][1] - min_y
        x2, y2 = w["end"][0] - min_x, w["end"][1] - min_y
        if w.get("source") == "opening_bridge":
            d.line([(x1, y1), (x2, y2)], fill=(34, 197, 94), width=4)  # verde
        else:
            d.line([(x1, y1), (x2, y2)], fill=(220, 38, 38), width=4)

    # junctions
    for j in juncs:
        cx, cy = j["point"][0] - min_x, j["point"][1] - min_y
        col = (220, 38, 38) if j.get("degree", 0) >= 3 else (37, 99, 235)
        r = 5
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)

    # openings: laranja diamond no centro
    for o in openings:
        cx, cy = o["center"][0] - min_x, o["center"][1] - min_y
        r = 9
        d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                  fill=(249, 115, 22), outline="black")

    d.rectangle([0, 0, width, 32], fill=(255, 255, 255, 230))
    d.text((6, 4),
           f"walls={len(walls)} juncs={len(juncs)} rooms={len(obs['rooms'])} "
           f"openings={len(openings)} geom={sc['geometry']} topo={sc['topology']}",
           fill="black", font=font)

    out = run_dir / "overlay_with_openings.png"
    base.save(out)
    print(f"wrote {out}")

    if not os.environ.get("PNG_HISTORY_DISABLE"):
        try:
            # Migrated from repo root (2026-05-08); tools/ is one level up now.
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
            from png_history import register
            register(out, kind="overlay_with_openings",
                     source={"consensus": obs_path},
                     generator="renderers.with_openings",
                     params={"run": str(run_dir), "mask": str(mask) if mask else None,
                             "openings": len(openings)})
        except Exception as e:
            print(f"[png_history skipped] {e}")

    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    run_dir = Path(args[0]) if args else Path("runs/proto/p8_red_v5_run")
    mask = Path(args[1]) if len(args) > 1 else None
    render(run_dir, mask)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
