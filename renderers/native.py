"""Renderiza ``debug_walls.png`` + ``debug_junctions.png`` nativos
(replicando o SVG do repo). Uso: ``python -m renderers.native <run_dir>``.

Migrated from repo root ``render_native.py`` (2026-05-08) per
``docs/architecture/target_repo_architecture.md`` step 5.
"""
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw


def render(run_dir: Path) -> tuple[Path, Path]:
    """Render walls + junctions PNGs into ``run_dir``.

    Returns ``(walls_png, junctions_png)`` paths.
    """
    obs_path = run_dir / "observed_model.json"
    model = json.loads(obs_path.read_text(encoding="utf-8"))
    walls, juncs = model["walls"], model["junctions"]

    xs, ys = [], []
    for w in walls:
        xs += [w["start"][0], w["end"][0]]
        ys += [w["start"][1], w["end"][1]]
    for j in juncs:
        xs.append(j["point"][0])
        ys.append(j["point"][1])
    margin = 20
    min_x, min_y = min(xs) - margin, min(ys) - margin
    max_x, max_y = max(xs) + margin, max(ys) + margin
    width, height = int(max_x - min_x), int(max_y - min_y)

    # debug_walls.png
    a = Image.new("RGB", (width, height), "white")
    da = ImageDraw.Draw(a)
    for w in walls:
        da.line([(w["start"][0] - min_x, w["start"][1] - min_y),
                 (w["end"][0] - min_x, w["end"][1] - min_y)],
                fill=(15, 23, 42), width=max(1, int(w.get("thickness", 4) / 2)))
    walls_png = run_dir / "debug_walls.png"
    a.save(walls_png)

    # debug_junctions.png
    b = Image.new("RGB", (width, height), "white")
    db = ImageDraw.Draw(b)
    for w in walls:
        db.line([(w["start"][0] - min_x, w["start"][1] - min_y),
                 (w["end"][0] - min_x, w["end"][1] - min_y)],
                fill=(203, 213, 225), width=2)
    for j in juncs:
        cx, cy = j["point"][0] - min_x, j["point"][1] - min_y
        col = (239, 68, 68) if j.get("degree", 0) >= 3 else (37, 99, 235)
        r = 4
        db.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    junctions_png = run_dir / "debug_junctions.png"
    b.save(junctions_png)
    print(f"{width}x{height} -> debug_walls.png + debug_junctions.png")

    if not os.environ.get("PNG_HISTORY_DISABLE"):
        try:
            # Migrated from repo root (2026-05-08); tools/ is one level up now.
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
            from png_history import register
            for kind, png in (("debug_walls", walls_png),
                              ("debug_junctions", junctions_png)):
                register(png, kind=kind, source={"consensus": obs_path},
                         generator="renderers.native",
                         params={"run_dir": str(run_dir)})
        except Exception as e:
            print(f"[png_history skipped] {e}")

    return walls_png, junctions_png


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        print("Usage: python -m renderers.native <run_dir>", file=sys.stderr)
        return 2
    render(Path(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
