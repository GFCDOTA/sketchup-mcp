"""Renderiza overlay com cores semanticas: walls vermelho, bridges verde,
portas laranja, janelas ciano, passagens roxo, peitoris marrom.

Uso: ``python -m renderers.semantic <run_dir>``.

Migrated from repo root ``render_semantic.py`` (2026-05-08) per
``docs/architecture/target_repo_architecture.md`` step 5.
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

KIND_COLORS = {
    "door":    (249, 115, 22),   # laranja
    "window":  (6, 182, 212),    # ciano
    "passage": (168, 85, 247),   # roxo
}


def render(run_dir: Path) -> Path:
    obs_path = run_dir / "observed_model.json"
    obs = json.loads(obs_path.read_text())
    walls = obs["walls"]
    juncs = obs["junctions"]
    openings = obs.get("openings", [])
    peitoris = obs.get("peitoris", [])
    sc = obs["scores"]

    xs = [c for w in walls for c in (w["start"][0], w["end"][0])] + \
         [b for p in peitoris for b in (p["bbox"][0], p["bbox"][2])]
    ys = [c for w in walls for c in (w["start"][1], w["end"][1])] + \
         [b for p in peitoris for b in (p["bbox"][1], p["bbox"][3])]
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

    # rooms shaded primeiro (atrás)
    palette = [(254, 226, 226, 120), (186, 230, 253, 120), (187, 247, 208, 120),
               (254, 240, 138, 120), (216, 180, 254, 120), (252, 165, 165, 120),
               (125, 211, 252, 120)]
    for i, r in enumerate(obs["rooms"]):
        poly = r.get("polygon") or []
        if len(poly) < 3:
            continue
        pts = [(p[0] - min_x, p[1] - min_y) for p in poly]
        d.polygon(pts, fill=palette[i % len(palette)])

    # peitoris (marrom translúcido)
    for p in peitoris:
        x1, y1, x2, y2 = p["bbox"]
        d.rectangle([x1 - min_x, y1 - min_y, x2 - min_x, y2 - min_y],
                    fill=(139, 69, 19, 180), outline=(101, 52, 15), width=2)

    # walls
    for w in walls:
        x1, y1 = w["start"][0] - min_x, w["start"][1] - min_y
        x2, y2 = w["end"][0] - min_x, w["end"][1] - min_y
        if w.get("source") == "opening_bridge":
            d.line([(x1, y1), (x2, y2)], fill=(34, 197, 94), width=4)
        else:
            d.line([(x1, y1), (x2, y2)], fill=(220, 38, 38), width=4)

    # junctions
    for j in juncs:
        cx, cy = j["point"][0] - min_x, j["point"][1] - min_y
        col = (220, 38, 38) if j.get("degree", 0) >= 3 else (37, 99, 235)
        d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=col)

    # openings classificados
    for o in openings:
        cx, cy = o["center"][0] - min_x, o["center"][1] - min_y
        col = KIND_COLORS.get(o.get("kind", "door"), (128, 128, 128))
        r = 9
        d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
                  fill=col, outline="black")

    d.rectangle([0, 0, width, 32], fill=(255, 255, 255, 230))
    kinds = Counter(o.get("kind", "door") for o in openings)
    d.text((6, 4),
           f"walls={len(walls)} juncs={len(juncs)} rooms={len(obs['rooms'])} "
           f"openings={len(openings)} ({dict(kinds)}) peitoris={len(peitoris)}  "
           f"geom={sc['geometry']} topo={sc['topology']} rooms={sc['rooms']}",
           fill="black", font=font)

    out = run_dir / "overlay_semantic.png"
    base.save(out)
    print(f"wrote {out}")

    if not os.environ.get("PNG_HISTORY_DISABLE"):
        try:
            # Migrated from repo root (2026-05-08); tools/ is one level up now.
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
            from png_history import register
            register(out, kind="overlay_semantic", source={"consensus": obs_path},
                     generator="renderers.semantic",
                     params={"run": str(run_dir), "openings": len(openings),
                             "peitoris": len(peitoris)})
        except Exception as e:
            print(f"[png_history skipped] {e}")

    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        print("Usage: python -m renderers.semantic <run_dir>", file=sys.stderr)
        return 2
    render(Path(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
