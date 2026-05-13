"""One-shot diagnostic render: dump every belief Claude has about the
planta into one image so the operator can mark what is wrong.

Shows: PDF base, consensus walls, human walls (with IDs), existing +
painted soft_barriers, room seeds (with the TERRACO TECNICO seed-bug
flagged), merged cells, per-pair classification under the PROPOSED
priors (semantic_room_split for the trio, already_explained for
A.S.↔TERRACO SOCIAL via h_w001).

Not part of the production pipeline — operator-debug only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pypdfium2 as pdfium
from matplotlib.patches import Patch, Rectangle
from matplotlib.patches import Polygon as MplPolygon


PROPOSED_PRIORS = {
    frozenset({"A.S.", "TERRACO SOCIAL"}):
        ("already_explained", "#0288d1", "h_w001 already painted"),
    frozenset({"A.S.", "TERRACO TECNICO"}):
        ("semantic_room_split", "#9e9e9e", "PROPOSED: no physical divider"),
    frozenset({"TERRACO SOCIAL", "TERRACO TECNICO"}):
        ("semantic_room_split", "#9e9e9e", "PROPOSED: no mureta"),
    frozenset({"SALA DE JANTAR", "SALA DE ESTAR"}):
        ("semantic_room_split", "#9e9e9e", "open plan (confirmed)"),
}

ROOM_NAMES = {
    "A.S.", "TERRACO SOCIAL", "TERRACO TECNICO", "COZINHA",
    "SUITE 01", "SUITE 02", "BANHO 01", "BANHO 02", "LAVABO",
    "SALA DE JANTAR", "SALA DE ESTAR",
}


def render(pdf_path: Path, consensus_path: Path, labels_path: Path,
            out_path: Path, dpi: int = 180) -> None:
    consensus = json.loads(consensus_path.read_text())
    labels = json.loads(labels_path.read_text())

    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[0]
    page_w, page_h = page.get_size()
    bitmap = page.render(scale=2.5).to_pil()
    pdf.close()

    fig, ax = plt.subplots(figsize=(20, 14), dpi=dpi, facecolor="#fafafa")
    ax.imshow(bitmap, extent=(0, page_w, 0, page_h),
              aspect="equal", alpha=0.45)

    walls = consensus.get("walls", [])
    thickness = float(consensus.get("wall_thickness_pts", 5.4))
    rooms = consensus.get("rooms", [])
    soft_barriers = consensus.get("soft_barriers", [])

    # Merged cells
    for r in rooms:
        name = r.get("name", "")
        if "|" not in name:
            continue
        pts = r.get("polygon_pts", [])
        if len(pts) < 3:
            continue
        ax.add_patch(MplPolygon(pts, closed=True,
                                 facecolor="#fff59d", edgecolor="#f57f17",
                                 linewidth=1.5, alpha=0.30, zorder=2,
                                 hatch="//"))

    # Walls
    for w in walls:
        s, e = w["start"], w["end"]
        is_human = w.get("geometry_origin") == "human_annotation"
        fc = "#1a237e" if is_human else "#9e9e9e"
        ec = "#000" if is_human else "#616161"
        lw = 1.4 if is_human else 0.5
        z = 6 if is_human else 3
        if w["orientation"] == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            ax.add_patch(Rectangle((x0, cy - thickness/2),
                                    x1 - x0, thickness,
                                    facecolor=fc, edgecolor=ec,
                                    linewidth=lw, alpha=0.85, zorder=z))
        else:
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            ax.add_patch(Rectangle((cx - thickness/2, y0),
                                    thickness, y1 - y0,
                                    facecolor=fc, edgecolor=ec,
                                    linewidth=lw, alpha=0.85, zorder=z))
        if is_human:
            ax.text(s[0] + 3, s[1] + 3, w["id"], fontsize=7,
                    color="#1a237e", zorder=10, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white",
                               ec="#1a237e", lw=0.6, alpha=0.95))

    # Soft barriers
    for b in soft_barriers:
        pts = b.get("polyline_pts", [])
        if len(pts) < 2:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        is_human = b.get("geometry_origin") == "human_annotation"
        color = "#00bcd4" if is_human else "#ff8f00"
        lw = 4 if is_human else 1.2
        ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.85, zorder=5)
        if is_human:
            cx, cy = sum(xs)/len(xs), sum(ys)/len(ys)
            ax.text(cx, cy - 6,
                    f'{b["id"]}\n{b.get("barrier_type", "?")} h={b.get("height_m", "?")}m',
                    fontsize=6, ha="center", color="#006064",
                    zorder=11, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="#e0f7fa",
                               ec="#006064", lw=0.6))

    # Seeds
    seed_by_name = {lb["name"]: lb["seed_pt"] for lb in labels
                     if lb["name"] in ROOM_NAMES}
    for name, sp in seed_by_name.items():
        is_bug = (name == "TERRACO TECNICO")
        if is_bug:
            ax.plot(sp[0], sp[1], "*", color="#fff", markersize=22,
                    markerfacecolor="#ff1744", markeredgewidth=2.0,
                    markeredgecolor="#b71c1c", zorder=15)
            ax.text(sp[0] + 5, sp[1] - 4,
                    f'BUG: seed em texto, nao no comodo real\n'
                    f'{name} ({sp[0]:.0f}, {sp[1]:.0f})',
                    fontsize=6, color="#b71c1c", zorder=16,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.25", fc="#ffebee",
                               ec="#b71c1c", lw=1.0, alpha=0.95))
        else:
            ax.plot(sp[0], sp[1], "*", color="#000", markersize=12,
                    markerfacecolor="#ffeb3b", markeredgewidth=1.0,
                    zorder=12)
            ax.text(sp[0] + 4, sp[1],
                    f'{name}\n({sp[0]:.0f}, {sp[1]:.0f})',
                    fontsize=6, color="#000", zorder=13,
                    bbox=dict(boxstyle="round,pad=0.20", fc="white",
                               ec="#666", lw=0.4, alpha=0.85))

    # Per-pair lines
    drawn = set()
    for cell in rooms:
        name = cell.get("name", "")
        if "|" not in name:
            continue
        cell_names = [n.strip() for n in name.split("|")]
        for i in range(len(cell_names)):
            for j in range(i + 1, len(cell_names)):
                a, b = cell_names[i], cell_names[j]
                key = frozenset({a, b})
                if key in drawn:
                    continue
                drawn.add(key)
                if a not in seed_by_name or b not in seed_by_name:
                    continue
                sa = seed_by_name[a]
                sb = seed_by_name[b]
                cls, color, note = PROPOSED_PRIORS.get(
                    key, ("inferred", "#999", "?"))
                ax.plot([sa[0], sb[0]], [sa[1], sb[1]], "--",
                        color=color, linewidth=1.4, alpha=0.85, zorder=11)
                mx, my = (sa[0] + sb[0]) / 2, (sa[1] + sb[1]) / 2
                ax.text(mx, my, f"{cls}\n{note}",
                        fontsize=6, ha="center", va="center",
                        color=color, zorder=14, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.20", fc="white",
                                   ec=color, lw=0.7, alpha=0.95))

    # Title + claims
    claims = (
        "MEUS APONTAMENTOS - confirme ou corrija cada item:\n"
        "  (1) h_w000 (h, topo A.S.) + h_w001 (v, direita A.S.) = paredes reais (voce ja confirmou)\n"
        "  (2) h_sb000 (cyan rodape) = UNICO peitoril fisico (parapeito externo H=1,10M)\n"
        "  (3) A.S. <-> TERRACO SOCIAL: already_explained por h_w001 (rodape A.S. abre pro terraco)\n"
        "  (4) A.S. <-> TERRACO TECNICO: semantic_room_split (PROPOSTA NOVA, sem divisor fisico)\n"
        "  (5) TERRACO SOCIAL <-> TERRACO TECNICO: semantic_room_split (PROPOSTA NOVA, sem mureta)\n"
        "  (6) SALA DE JANTAR <-> SALA DE ESTAR: semantic_room_split (open plan, confirmado)\n"
        "  (7) BUG SEPARADO: seed TERRACO TECNICO esta na coord do TEXTO 'TERRACO TECNICO' no PDF,\n"
        "      nao no centroide do comodo. Aponte com seta vermelha onde TERRACO TECNICO realmente esta."
    )
    ax.text(page_w / 2, page_h - 5, claims,
            fontsize=8, ha="center", va="top", color="#000", zorder=20,
            bbox=dict(boxstyle="round,pad=0.5", fc="#fffde7",
                       ec="#f57f17", lw=1.2, alpha=0.95))

    legend = [
        Patch(facecolor="#9e9e9e", edgecolor="#616161",
              label=f"consensus walls ({len([w for w in walls if w.get('geometry_origin') != 'human_annotation'])})"),
        Patch(facecolor="#1a237e", edgecolor="#000",
              label="human walls (h_w000, h_w001)"),
        Patch(facecolor="#ff8f00", edgecolor="#ff8f00",
              label=f"existing soft_barriers ({len([b for b in soft_barriers if b.get('geometry_origin') != 'human_annotation'])} polylines)"),
        Patch(facecolor="#00bcd4", edgecolor="#006064",
              label="painted soft_barrier (h_sb000 parapet)"),
        Patch(facecolor="#ffeb3b", edgecolor="#000",
              label="room seed (text label position)"),
        Patch(facecolor="#ff1744", edgecolor="#b71c1c",
              label="seed BUG (TERRACO TECNICO)"),
        Patch(facecolor="#fff59d", edgecolor="#f57f17", hatch="//",
              label="merged cell (post-walls)"),
        Patch(facecolor="#0288d1", edgecolor="#0288d1",
              label="pair: already_explained"),
        Patch(facecolor="#9e9e9e", edgecolor="#9e9e9e",
              label="pair: semantic_room_split"),
    ]
    ax.legend(handles=legend, loc="lower left", fontsize=8, framealpha=0.95)

    ax.set_title(
        "Diagnostico Visual: o que Claude acredita sobre planta_74 - corrija os erros",
        fontsize=13, pad=10, color="#000", fontweight="bold")
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor="#fafafa")
    plt.close(fig)
    print(f"wrote: {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    render(args.pdf, args.consensus, args.labels, args.out)


if __name__ == "__main__":
    main()
