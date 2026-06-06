"""Gera fixtures SINTETICAS de QUARTO (dormitorio) pra provar que o bedroom
layout brain (proximos cycles) nao overfita na planta_74. Quartos retangulares
com 1 porta (interior_door, perto de um canto de uma parede lateral) + 1 janela
(window, no meio de uma parede de fundo). Sempre sobra >=1 parede LIMPA (sem
porta nem janela) como boa parede de cabeceira. NAO sao plantas reais —
exercitam o ranking (cabeceira na parede limpa, guarda-roupa, criados-mudos,
sem bloquear porta/janela; cama sob janela = soft).

Espelha os helpers/ancora de tools.make_synthetic_rooms (self-contained pra
rodar standalone, igual ao sibling). Regras de dormitorio
validadas com ChatGPT (consult "Prioridade Quartos e Layout", 2026-06-05).
Felipe 2026-06-05. NAO usa 3D Warehouse / estilo / SKP.

Uso: python tools/make_synthetic_bedrooms.py
     -> fixtures/synthetic_rooms/bedroom_{small,medium,large}_*.json
"""
import json
from pathlib import Path

M = 5.4 / 0.19   # metros -> pdf-points (~28.42); mesma ancora de make_synthetic_rooms
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic_rooms"
DOOR_W, WIN_W = 0.80, 1.20   # m


def _wall(wid, a, b, orient):
    return {"id": wid, "start": [round(a[0], 2), round(a[1], 2)],
            "end": [round(b[0], 2), round(b[1], 2)], "orientation": orient,
            "thickness": 5.4}


def _open(oid, kind, wid, center, width_m):
    return {"id": oid, "kind_v5": kind, "kind": kind, "wall_id": wid,
            "center": [round(center[0], 2), round(center[1], 2)],
            "opening_width_pts": round(width_m * M, 2), "geometry_origin": "synthetic"}


def rect_bedroom(room_name, w_m, d_m, door_wall="wL", door_frac=0.18,
                 window_wall="wT", window_frac=0.5):
    """Retangulo W x D (m). Porta perto de um CANTO de uma parede lateral +
    janela no meio de uma parede de fundo. wB/wT = h (largura W); wL/wR = v
    (profundidade D). A(s) parede(s) sem porta nem janela = candidata(s) a
    cabeceira (parede limpa)."""
    W, D = w_m * M, d_m * M
    walls = [_wall("wB", (0, 0), (W, 0), "h"), _wall("wR", (W, 0), (W, D), "v"),
             _wall("wT", (0, D), (W, D), "h"), _wall("wL", (0, 0), (0, D), "v")]
    wmap = {w["id"]: w for w in walls}

    def pt_on(wid, frac):
        a, b = wmap[wid]["start"], wmap[wid]["end"]
        return [a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac]

    openings = [
        _open("door1", "interior_door", door_wall, pt_on(door_wall, door_frac), DOOR_W),
        _open("win1", "window", window_wall, pt_on(window_wall, window_frac), WIN_W),
    ]
    room = {"id": "bedroom", "name": room_name,
            "polygon_pts": [[0, 0], [W, 0], [W, D], [0, D], [0, 0]]}
    return {"wall_thickness_pts": 5.4, "walls": walls, "openings": openings,
            "rooms": [room], "soft_barriers": []}


# (filename) -> (room_name, kwargs). room_name casa como BEDROOM em room_type.
# small: tight, degrada (1 criado, guarda-roupa de correr). medium/large:
# folgado (cama centralizada, 2 criados). door em parede diferente da janela ->
# sempre sobra parede limpa de cabeceira.
SPECS = {
    "bedroom_small_9m2":   ("QUARTO PEQUENO", dict(w_m=3.0, d_m=3.0)),
    "bedroom_medium_14m2": ("SUITE 02", dict(w_m=3.5, d_m=4.0)),
    "bedroom_large_18m2":  ("SUITE MASTER",
                            dict(w_m=4.2, d_m=4.3, door_wall="wB", window_wall="wT")),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for fname, (room_name, kw) in SPECS.items():
        con = rect_bedroom(room_name, **kw)
        (OUT / f"{fname}.json").write_text(json.dumps(con, indent=2), encoding="utf-8")
        area = kw["w_m"] * kw["d_m"]
        print(f"{fname}: {kw['w_m']}x{kw['d_m']} m = {area:4.1f} m2 "
              f"('{room_name}') -> synthetic_rooms/{fname}.json")


if __name__ == "__main__":
    main()
