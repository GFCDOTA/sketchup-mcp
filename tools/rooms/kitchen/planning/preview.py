"""Synthetic proof preview for FP-050. No SketchUp and no canonical files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box

from tools.rooms.kitchen.planning.cabinet_placement import select_wall_cabinet_positions


def render_preview(*, room, plan: dict, furniture, door_swings, protected_circulation, destination: Path) -> None:
    """Save a top-view diagram of the synthetic validated L1 result."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 7))

    def draw(geom, label, alpha=1.0, dashed=False):
        x, y = geom.exterior.xy
        line, = ax.plot(x, y, "--" if dashed else "-", linewidth=2, alpha=alpha, label=label)
        if alpha < 1:
            ax.fill(x, y, color=line.get_color(), alpha=alpha * 0.25)

    draw(room, "Room boundary")
    for i, geom in enumerate(furniture):
        draw(geom, "Existing furniture" if i == 0 else "", alpha=0.7)
    for i, geom in enumerate(door_swings):
        draw(geom, "Door swing" if i == 0 else "", alpha=0.7)
    for i, geom in enumerate(protected_circulation):
        draw(geom, "Protected circulation" if i == 0 else "", alpha=0.45)
    if plan["status"] == "OPTIONS_ONLY":
        for i, c in enumerate([plan["selected"], *plan["alternatives"]]):
            if i > 0:
                draw(Polygon(c["footprint_xy_m"]), "Other valid positions" if i == 1 else "", alpha=0.3, dashed=True)
            else:
                draw(Polygon(c["footprint_xy_m"]), "Selected cabinet (proposal)", alpha=1)
                draw(Polygon(c["front_access_xy_m"]), "Required front access", alpha=0.6, dashed=True)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title("FP-050 synthetic kitchen | L1 options only")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=160)
    plt.close(fig)


def demo(out_dir: Path) -> dict:
    """All dimensions are fictional and explicitly chosen for a micro-fixture."""
    room = box(0, 0, 3, 4)
    furniture = [box(0.62, 1.4, 1.3, 2.6)]
    door_swings = [box(0, 0, 0.8, 0.6)]
    protected_circulation = [box(2.3, 0, 2.8, 4)]
    plan = select_wall_cabinet_positions(
        room=room, wall=LineString([(0, 0), (0, 4)]), inward=(1, 0),
        anchor=Point(0, 2), width_m=0.6, depth_m=0.6, access_depth_m=0.8,
        furniture=furniture, door_swings=door_swings,
        protected_circulation=protected_circulation,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "placement_report.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    render_preview(room=room, plan=plan, furniture=furniture,
                   door_swings=door_swings, protected_circulation=protected_circulation,
                   destination=out_dir / "placement_plan.png")
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic L1 kitchen cabinet placement demo")
    parser.add_argument("--out", type=Path, required=True, help="Output directory (never canonical assets)")
    args = parser.parse_args()
    report = demo(args.out)
    print(json.dumps({"status": report["status"], "output": str(args.out),
                      "rejection_counts": report.get("rejection_counts", {})}, ensure_ascii=False))


if __name__ == "__main__":
    main()
