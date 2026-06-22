"""sofa_venezia_room.py — MT-SOFA-004 GATE DE CONTEXTO (pedido do GPT): o sofá venezia DENTRO da sala
(piso, paredes, rack+TV, mesa de centro, circulação visível), velho-caixa × novo no mesmo ângulo.
SU-free (render_parts_iso) — valida ESCALA + circulação, não material. A beleza do couro = V-Ray depois.

Uso: python -m tools.sofa_venezia_room [out_dir]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.render_parts_iso import render_parts            # noqa: E402
from tools.sofa_builder import build_sofa                  # noqa: E402
from tools.sofa_class import derive_spec                   # noqa: E402
from tools.sofa_class_matrix import _grid_sheet            # noqa: E402
from tools.sofa_venezia_compare import old_box             # noqa: E402

FLOOR = (198, 192, 182)
WALL = (214, 210, 204)
RACK = (54, 50, 48)
TV = (18, 18, 20)
CTAB = (104, 80, 58)
GRAPHITE = (54, 56, 57)   # couro slate/grafite (token da SOFA_BUILD_SPEC)
LEG = (22, 22, 24)        # ferro preto fosco
RW, RD, WALL_H = 3.15, 3.25, 1.2   # sala compacta justa (planta_74 living ~13.7 m²)


def _recolor_venezia(parts):
    """Pinta o sofá de couro grafite + pés de ferro preto (a peça dark premium)."""
    out = []
    for p in parts:
        q = dict(p)
        q["rgb"] = LEG if p.get("kind") == "foot" else GRAPHITE
        out.append(q)
    return out


def _box(x0, y0, z0, x1, y1, z1, rgb):
    return {"x0": x0, "y0": y0, "z0": z0, "x1": x1, "y1": y1, "z1": z1, "rgb": rgb, "edge": True}


def _translate(parts, dx, dy, dz=0.0):
    out = []
    for p in parts:
        q = dict(p)
        if p.get("verts8"):
            q["verts8"] = [(v[0] + dx, v[1] + dy, v[2] + dz) for v in p["verts8"]]
        q["x0"], q["x1"] = p["x0"] + dx, p["x1"] + dx
        q["y0"], q["y1"] = p["y0"] + dy, p["y1"] + dy
        q["z0"], q["z1"] = p["z0"] + dz, p["z1"] + dz
        out.append(q)
    return out


def _room():
    return [
        _box(-0.2, -0.2, -0.04, RW + 0.2, RD + 0.2, 0.0, FLOOR),     # piso
        _box(-0.2, RD, 0.0, RW + 0.2, RD + 0.1, WALL_H, WALL),       # parede de trás (atrás do sofá)
        _box(-0.2, -0.2, 0.0, -0.1, RD + 0.2, WALL_H, WALL),         # parede lateral esquerda
        _box(0.6, 0.0, 0.0, 2.4, 0.42, 0.42, RACK),                  # rack/console (parede oposta)
        _box(0.9, 0.07, 0.42, 2.1, 0.11, 1.02, TV),                  # TV em pé no rack
        _box(0.95, 1.55, 0.0, 1.95, 2.25, 0.38, CTAB),              # mesa de centro
    ]


def scene(spec, label, out_png, graphite=False):
    """Sofá encostado na parede de trás, de frente pro rack/TV; circulação = piso entre mesa e rack."""
    parts, _ = build_sofa(spec)
    if graphite:
        parts = _recolor_venezia(parts)
    sx = round((RW - spec.width) / 2, 3)
    sy = round(RD - spec.depth - 0.12, 3)           # back do sofá ~12cm da parede de trás
    parts = _translate(parts, sx, sy, 0.0)
    return render_parts(_room() + parts, out_png, elev=22, azim=-66, title=label)


def main(out_dir):
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    new3 = derive_spec(3, "venezia", "thin", "legs")
    cells = [
        ("OLD_caixa_na_sala", scene(old_box(), "OLD caixa na sala", out / "room_OLD.png"), "FAIL", ""),
        ("NEW_venezia_na_sala", scene(new3, "NEW venezia 3l (couro grafite) na sala", out / "room_NEW.png", graphite=True), "PASS", ""),
    ]
    sheet = _grid_sheet([(n, p, r, a) for n, p, r, a in cells],
                        out / "sofa_venezia_room.png",
                        "SOFA na SALA (circulacao visivel) — velho-caixa x novo venezia · mesmo angulo",
                        cols=2)
    return sheet


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "artifacts/review/furniture/sofa/venezia")
    print("sheet:", main(d))
