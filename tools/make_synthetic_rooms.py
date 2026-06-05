"""Gera fixtures SINTETICAS de sala-de-estar pra provar que o cerebro de layout
nao overfitou na planta_74 (A2 sintetico, spec do GPT em docs/interiors/
gpt_composition_spec.md). Salas retangulares/L simples, com porta + porta-vidro
(varanda) + paredes-TV candidatas. NAO sao plantas reais — so testam se o
ranking se comporta certo (core ancorado vence, opcional removido se bloqueia).

Uso: python -m tools.make_synthetic_rooms   (gera fixtures/synthetic_rooms/*.json)
"""
import json
from pathlib import Path

M = 5.4 / 0.19   # metros -> pdf-points (~28.42)
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_rooms"
DOOR_W, BALC_W = 0.85, 1.60   # m


def _wall(wid, a, b, orient):
    return {"id": wid, "start": [round(a[0], 2), round(a[1], 2)],
            "end": [round(b[0], 2), round(b[1], 2)], "orientation": orient,
            "thickness": 5.4}


def _open(oid, kind, wid, center, width_m):
    return {"id": oid, "kind_v5": kind, "kind": kind, "wall_id": wid,
            "center": [round(center[0], 2), round(center[1], 2)],
            "opening_width_pts": round(width_m * M, 2), "geometry_origin": "synthetic"}


def rect_room(name, w_m, d_m, door_wall="wL", door_frac=0.18, balcony_wall="wT"):
    """Retangulo W x D (m). Porta perto de um CANTO de uma parede lateral +
    porta-vidro (varanda) no meio de uma parede larga -> a parede larga OPOSTA a
    varanda fica livre como parede-TV boa (como numa sala real). wB/wT = h (W);
    wL/wR = v (D)."""
    W, D = w_m * M, d_m * M
    walls = [_wall("wB", (0, 0), (W, 0), "h"), _wall("wR", (W, 0), (W, D), "v"),
             _wall("wT", (0, D), (W, D), "h"), _wall("wL", (0, 0), (0, D), "v")]
    wmap = {w["id"]: w for w in walls}

    def pt_on(wid, frac):
        a, b = wmap[wid]["start"], wmap[wid]["end"]
        return [a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac]

    openings = [_open("door1", "interior_door", door_wall, pt_on(door_wall, door_frac), DOOR_W),
                _open("balc1", "glazed_balcony", balcony_wall, pt_on(balcony_wall, 0.5), BALC_W)]
    room = {"id": "living", "name": name,
            "polygon_pts": [[0, 0], [W, 0], [W, D], [0, D], [0, 0]]}
    return {"wall_thickness_pts": 5.4, "walls": walls, "openings": openings,
            "rooms": [room], "soft_barriers": []}


SPECS = {
    "living_small_rect_10m2": dict(w_m=3.6, d_m=2.8),
    "living_medium_rect_18m2": dict(w_m=5.0, d_m=3.6),
    "living_large_rect_28m2": dict(w_m=6.2, d_m=4.5),
    "living_long_narrow": dict(w_m=6.5, d_m=2.5, door_wall="wL", balcony_wall="wR"),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, kw in SPECS.items():
        con = rect_room(name, **kw)
        (OUT / f"{name}.json").write_text(json.dumps(con, indent=2), encoding="utf-8")
        area = kw["w_m"] * kw["d_m"]
        print(f"{name}: {kw['w_m']}x{kw['d_m']} m = {area:.1f} m2 -> {OUT.name}/{name}.json")


if __name__ == "__main__":
    main()
