"""Build room adjacency graph from consensus_model.json.

For each opening, find the two rooms it connects by point-in-polygon testing
two probe points offset perpendicular to the opening's wall orientation.

Outputs:
  - In-place injection of `adjacency` field into consensus_model.json:
      adjacency = {
        "edges": [{"room_a": str, "room_b": str, "via": str, "kind": str}],
        "nodes": [{"room_id": str, "label": str, "openings_count": int}],
        "facade_openings": [{"opening_id": str, "room": str, "kind": str}]
      }
  - SVG render of graph at runs/final_planta_74/room_graph.svg
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from collections import Counter, defaultdict

CONSENSUS = Path(r"E:\Claude\sketchup-mcp-exp-dedup\runs\final_planta_74\consensus_model.json")
SVG_OUT = Path(r"E:\Claude\sketchup-mcp-exp-dedup\runs\final_planta_74\room_graph.svg")

# Probe offsets perpendicular to the opening's wall direction.
# Tried in increasing magnitude until we get two distinct rooms (or run out).
PROBE_OFFSETS_PT = [8.0, 14.0, 22.0, 32.0, 45.0, 60.0]

KIND_COLOR = {
    "door": "#e67e22",      # laranja
    "window": "#3498db",    # azul
    "passage": "#7f8c8d",   # cinza
    "unknown": "#bdc3c7",
}


# ----------------------------- geometry helpers ----------------------------- #
def point_in_poly(pt, poly):
    """Ray-cast point-in-polygon test."""
    x, y = pt
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def dist_point_to_segment(p, a, b):
    """Shortest distance from p to segment ab."""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def nearest_wall(opening, walls):
    """Return the wall whose segment is closest to the opening center."""
    cx, cy = opening["center"]
    best = None
    best_d = float("inf")
    for w in walls:
        d = dist_point_to_segment((cx, cy), w["start"], w["end"])
        if d < best_d:
            best_d = d
            best = w
    return best, best_d


def opening_orientation(opening, walls):
    """Return angle (degrees) of the wall the opening sits on.
    Falls back to opening['orientation'] field ('h'=0, 'v'=90) if no wall close.
    """
    if opening.get("orientation") in ("h", "v"):
        # short-circuit: trust explicit orientation
        return 0.0 if opening["orientation"] == "h" else 90.0
    w, d = nearest_wall(opening, walls)
    if w is not None:
        return float(w.get("angle_deg", 0.0))
    return 0.0


def find_room_at(point, rooms):
    for r in rooms:
        if point_in_poly(point, r["polygon"]):
            return r
    return None


# ----------------------------- graph building ------------------------------- #
def build_graph(model):
    rooms = model["rooms"]
    walls = model["walls"]
    openings = model["openings"]

    edges = []
    facade = []
    openings_per_room = Counter()

    # ensure every opening gets room_a/room_b populated
    for op in openings:
        cx, cy = op["center"]
        ang = opening_orientation(op, walls)
        # perpendicular unit vector (perpendicular to wall direction)
        rad = math.radians(ang)
        perp_x = -math.sin(rad)
        perp_y = math.cos(rad)

        room_a = None
        room_b = None
        chosen_offset = None
        for off in PROBE_OFFSETS_PT:
            pa = (cx + perp_x * off, cy + perp_y * off)
            pb = (cx - perp_x * off, cy - perp_y * off)
            ra = find_room_at(pa, rooms)
            rb = find_room_at(pb, rooms)
            if ra and rb and ra["room_id"] != rb["room_id"]:
                room_a, room_b = ra, rb
                chosen_offset = off
                break
            # if exactly one side hits a room, remember it as candidate facade
            if ra and not room_b:
                room_a = room_a or ra
            if rb and not room_a:
                room_b = room_b or rb

        kind = op.get("kind") or "unknown"
        if room_a and room_b and room_a["room_id"] != room_b["room_id"]:
            op["room_a"] = room_a["room_id"]
            op["room_b"] = room_b["room_id"]
            edges.append({
                "room_a": room_a["room_id"],
                "room_b": room_b["room_id"],
                "via": op["opening_id"],
                "kind": kind,
                "probe_offset_pt": chosen_offset,
            })
            openings_per_room[room_a["room_id"]] += 1
            openings_per_room[room_b["room_id"]] += 1
        else:
            single = room_a or room_b
            if single:
                op["room_a"] = single["room_id"]
                op["room_b"] = None
                facade.append({
                    "opening_id": op["opening_id"],
                    "room": single["room_id"],
                    "kind": kind,
                })
                openings_per_room[single["room_id"]] += 1
            # else: opening hits no room at all, skip

    nodes = [
        {
            "room_id": r["room_id"],
            "label": r.get("label_qwen") or "(sem rotulo)",
            "openings_count": openings_per_room.get(r["room_id"], 0),
        }
        for r in rooms
    ]
    adjacency = {"edges": edges, "nodes": nodes, "facade_openings": facade}
    return adjacency


# ----------------------------- SVG rendering -------------------------------- #
def render_svg(adjacency, model, out_path: Path):
    """Render graph using matplotlib (always available with networkx)."""
    try:
        import networkx as nx
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        print(f"[warn] matplotlib/networkx missing ({exc}); falling back to plain SVG")
        return _render_plain_svg(adjacency, model, out_path)

    G = nx.MultiGraph()
    label_map = {n["room_id"]: f"{n['label']}\n({n['openings_count']} ab.)" for n in adjacency["nodes"]}
    for n in adjacency["nodes"]:
        G.add_node(n["room_id"], label=label_map[n["room_id"]])

    edge_colors = []
    edge_styles = []
    for e in adjacency["edges"]:
        G.add_edge(e["room_a"], e["room_b"], key=e["via"], kind=e["kind"], via=e["via"])
        edge_colors.append(KIND_COLOR.get(e["kind"], KIND_COLOR["unknown"]))

    # Use room polygon centroids as initial layout (matches plant orientation)
    pos = {}
    for r in model["rooms"]:
        xs = [p[0] for p in r["polygon"]]
        ys = [p[1] for p in r["polygon"]]
        # Flip Y so plant orientation is preserved (image coords -> plot coords)
        pos[r["room_id"]] = (sum(xs) / len(xs), -sum(ys) / len(ys))

    fig, ax = plt.subplots(figsize=(13, 11))
    # Draw nodes as squares sized roughly by openings_count
    sizes = [800 + 350 * adjacency["nodes"][i]["openings_count"] for i in range(len(adjacency["nodes"]))]
    nx.draw_networkx_nodes(
        G, pos,
        node_color="#ecf0f1",
        edgecolors="#2c3e50",
        linewidths=1.5,
        node_size=sizes,
        node_shape="s",
        ax=ax,
    )

    # Draw edges with kind-based colors. MultiGraph: per-edge color list.
    # networkx draw_networkx_edges takes edgelist + edge_color
    edgelist = [(e["room_a"], e["room_b"]) for e in adjacency["edges"]]
    nx.draw_networkx_edges(
        G, pos,
        edgelist=edgelist,
        edge_color=edge_colors,
        width=2.0,
        alpha=0.85,
        ax=ax,
    )

    # Node labels
    nx.draw_networkx_labels(G, pos, labels=label_map, font_size=8, font_color="#2c3e50", ax=ax)

    # Edge labels (via opening_id)
    edge_labels = {}
    pair_count = defaultdict(int)
    for e in adjacency["edges"]:
        key = tuple(sorted([e["room_a"], e["room_b"]]))
        if pair_count[key] == 0:
            edge_labels[(e["room_a"], e["room_b"])] = e["via"]
        else:
            cur = edge_labels.get((e["room_a"], e["room_b"]), "") or edge_labels.get((e["room_b"], e["room_a"]), "")
            edge_labels[(e["room_a"], e["room_b"])] = f"{cur}+{e['via']}"
        pair_count[key] += 1
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=6, font_color="#34495e", ax=ax)

    # Legend
    from matplotlib.lines import Line2D
    legend_handles = [
        Line2D([0], [0], color=KIND_COLOR["door"], lw=2.5, label="door (porta)"),
        Line2D([0], [0], color=KIND_COLOR["window"], lw=2.5, label="window (janela)"),
        Line2D([0], [0], color=KIND_COLOR["passage"], lw=2.5, label="passage"),
    ]
    if any(f for f in adjacency["facade_openings"]):
        legend_handles.append(Line2D([0], [0], marker="o", linestyle="", color="#c0392b",
                                     markersize=8, label=f"facade ({len(adjacency['facade_openings'])})"))
    ax.legend(handles=legend_handles, loc="lower right", fontsize=9)

    ax.set_title(
        f"Grafo de adjacencia de comodos - apto 74m2\n"
        f"{len(adjacency['nodes'])} rooms | {len(adjacency['edges'])} edges | "
        f"{len(adjacency['facade_openings'])} facade openings",
        fontsize=12,
    )
    ax.set_axis_off()
    ax.margins(0.1)
    plt.tight_layout()
    plt.savefig(out_path, format="svg", bbox_inches="tight")
    # Also drop a PNG companion next to the SVG for quick preview
    png_path = out_path.with_suffix(".png")
    plt.savefig(png_path, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return True


def _render_plain_svg(adjacency, model, out_path: Path):
    """Minimal pure-SVG fallback (no matplotlib)."""
    pos = {}
    for r in model["rooms"]:
        xs = [p[0] for p in r["polygon"]]
        ys = [p[1] for p in r["polygon"]]
        pos[r["room_id"]] = (sum(xs) / len(xs), sum(ys) / len(ys))
    label = {n["room_id"]: n["label"] for n in adjacency["nodes"]}

    minx = min(p[0] for p in pos.values()) - 60
    maxx = max(p[0] for p in pos.values()) + 60
    miny = min(p[1] for p in pos.values()) - 60
    maxy = max(p[1] for p in pos.values()) + 60
    w, h = maxx - minx, maxy - miny

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx} {miny} {w} {h}" width="900" height="{int(900 * h / w)}">']
    out.append('<style>text{font-family:Arial;font-size:10px;fill:#2c3e50}</style>')
    for e in adjacency["edges"]:
        a, b = pos[e["room_a"]], pos[e["room_b"]]
        c = KIND_COLOR.get(e["kind"], KIND_COLOR["unknown"])
        out.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{c}" stroke-width="2"/>')
    for rid, (x, y) in pos.items():
        out.append(f'<rect x="{x-35}" y="{y-12}" width="70" height="24" fill="#ecf0f1" stroke="#2c3e50"/>')
        out.append(f'<text x="{x}" y="{y+4}" text-anchor="middle">{label[rid]}</text>')
    out.append("</svg>")
    out_path.write_text("\n".join(out), encoding="utf-8")
    return True


# ---------------------------------- main ------------------------------------ #
def main():
    model = json.loads(CONSENSUS.read_text(encoding="utf-8"))
    adjacency = build_graph(model)
    model["adjacency"] = adjacency
    CONSENSUS.write_text(json.dumps(model, indent=2, ensure_ascii=False), encoding="utf-8")
    render_svg(adjacency, model, SVG_OUT)

    # Summary
    rooms_by_id = {r["room_id"]: r.get("label_qwen") or r["room_id"] for r in model["rooms"]}
    print(f"[ok] rooms={len(adjacency['nodes'])} edges={len(adjacency['edges'])} "
          f"facade={len(adjacency['facade_openings'])}")
    print(f"[ok] svg -> {SVG_OUT}")
    print(f"[ok] consensus_model.json updated with `adjacency` field")
    print()
    print("Edges sample (first 12):")
    for e in adjacency["edges"][:12]:
        la = rooms_by_id.get(e["room_a"], e["room_a"])
        lb = rooms_by_id.get(e["room_b"], e["room_b"])
        print(f"  {la} <-> {lb}  via {e['via']} ({e['kind']})")
    if adjacency["facade_openings"]:
        print()
        print("Facade openings:")
        for f in adjacency["facade_openings"][:8]:
            print(f"  {rooms_by_id.get(f['room'], f['room'])}: {f['opening_id']} ({f['kind']})")


if __name__ == "__main__":
    main()
