"""shell_parts.py — o ENVELOPE arquitetônico (paredes/portas/janelas) como parts
do render iso SU-free.

Por que existe: o painel de juízes e o GPT-Docker deram nota 2/10 consistente em
TODAS as variantes do sweep com o MESMO diagnóstico — "furniture-only, sem envelope
arquitetônico". O caminho-pro-10 literal: "envelope-first floorplan rendering
(walls before contents)". Este módulo converte as walls do consensus (a fonte de
verdade — Hard Rule #1: nunca inventar parede) em caixas pro render_parts_iso,
no MESMO sistema de coordenadas dos móveis (pts × core.scale.PT_TO_IN, sem flip —
paridade com furnish_apartment linha ~337).

Decisões de legibilidade (corte dollhouse):
- Paredes cortadas a WALL_CUT_M (~1.1 m): acima de bancada (0.9), abaixo do olho —
  o envelope aparece SEM esconder a mobília no iso.
- Porta = GAP real na massa da parede (recorte por wall_id + center + width).
- Janela = trecho da parede em tom AZULADO (vidro legível); não fura a massa —
  no corte de 1.1 m um peitoril real (~1.0 m) sumiria, e massa furada leria como
  porta errada (pior que a convenção de cor).

Puro e determinístico: consensus dict → list[part]. Nada de I/O aqui.
"""
from __future__ import annotations

# corte dollhouse da parede no iso (m) — legibilidade, não altura real
WALL_CUT_M = 1.1
M_TO_IN = 39.3700787402

RGB_WALL = [168, 162, 152]     # cinza-concreto quente (neutro, não compete com mobília)
RGB_WINDOW = [140, 170, 190]   # azulado discreto = vidro/janela (convenção do corte)


def _wall_axis_span(w: dict) -> tuple[str, float, float, float, float]:
    """(axis, a0, a1, c, half_t) em PTS: eixo longitudinal, extremos ordenados,
    centro transversal e meia-espessura."""
    (x0, y0), (x1, y1) = w["start"], w["end"]
    t = float(w.get("thickness") or 5.0)
    if str(w.get("orientation", "h")).lower() == "h":
        a0, a1 = sorted((float(x0), float(x1)))
        return "x", a0, a1, (float(y0) + float(y1)) / 2.0, t / 2.0
    a0, a1 = sorted((float(y0), float(y1)))
    return "y", a0, a1, (float(x0) + float(x1)) / 2.0, t / 2.0


def _openings_on(wall_id: str, openings: list[dict]) -> list[dict]:
    return [o for o in openings or [] if str(o.get("wall_id")) == wall_id]


def _segments(a0: float, a1: float, doors: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Subtrai os gaps de porta [ (g0,g1), ... ] do intervalo [a0,a1] — sobra a
    massa de parede. Gaps clampados ao intervalo; sobreposição tolerada."""
    cuts = sorted((max(a0, g0), min(a1, g1)) for g0, g1 in doors if g1 > a0 and g0 < a1)
    segs, cur = [], a0
    for g0, g1 in cuts:
        if g0 > cur:
            segs.append((cur, g0))
        cur = max(cur, g1)
    if cur < a1:
        segs.append((cur, a1))
    return [(s0, s1) for s0, s1 in segs if s1 - s0 > 0.5]  # descarta lasca <0.5pt


def _box(axis: str, s0: float, s1: float, c: float, half_t: float,
         pt_to_in: float, z1_in: float, rgb: list[int]) -> dict:
    if axis == "x":
        x0, x1, y0, y1 = s0, s1, c - half_t, c + half_t
    else:
        y0, y1, x0, x1 = s0, s1, c - half_t, c + half_t
    return {"x0": x0 * pt_to_in, "y0": y0 * pt_to_in,
            "x1": x1 * pt_to_in, "y1": y1 * pt_to_in,
            "z0": 0.0, "z1": z1_in, "rgb": list(rgb), "kind": "shell_wall"}


def shell_parts(con: dict, *, pt_to_in: float | None = None,
                wall_cut_m: float = WALL_CUT_M) -> list[dict]:
    """Consensus → parts do envelope (mesmas unidades dos móveis: shell inches).

    Nunca inventa: só o que está em con["walls"]/con["openings"]. Consensus sem
    walls → lista vazia (o caller decide se renderiza furniture-only honesto).
    """
    if pt_to_in is None:
        from core.scale import PT_TO_IN  # fonte única (env PT_TO_M → 0.0259)
        pt_to_in = PT_TO_IN
    z1_in = wall_cut_m * M_TO_IN
    openings = con.get("openings") or []
    parts: list[dict] = []
    for w in con.get("walls") or []:
        axis, a0, a1, c, half_t = _wall_axis_span(w)
        doors, windows = [], []
        for o in _openings_on(str(w.get("id")), openings):
            width = float(o.get("opening_width_pts") or 0.0)
            center = o.get("center") or [0.0, 0.0]
            oc = float(center[0] if axis == "x" else center[1])
            span = (oc - width / 2.0, oc + width / 2.0)
            if width <= 0.0:
                continue
            (doors if str(o.get("kind")) == "door" else windows).append(span)
        # massa de parede = intervalo − portas (portas FURAM; janela não)
        for s0, s1 in _segments(a0, a1, doors):
            parts.append(_box(axis, s0, s1, c, half_t, pt_to_in, z1_in, RGB_WALL))
        # janela = sobreposição azulada na própria massa (levemente mais alta
        # pra vencer o z-fight e ler como faixa de vidro no topo do corte)
        for g0, g1 in windows:
            g0, g1 = max(a0, g0), min(a1, g1)
            if g1 - g0 > 0.5:
                p = _box(axis, g0, g1, c, half_t + 0.2, pt_to_in, z1_in * 1.02, RGB_WINDOW)
                p["kind"] = "shell_window"
                parts.append(p)
    return parts
