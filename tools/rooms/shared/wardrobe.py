"""wardrobe_builder.py — GUARDA-ROUPA parametrico como PECAS separadas (espelha bed/sofa
builder; regra Felipe: NAO bloco unico). De um WardrobeSpec gera: rodape recuado + corpo +
N portas (com FRESTAS/divisoes verticais) + puxadores — material por papel (corpo madeira,
portas laca/madeira mais clara, puxador metal escuro, rodape escuro).

Convencao: X=largura (ao longo da parede), Y=profundidade (FRENTE=Y=0=-Y vira p/ dentro do
quarto), Z=altura. As portas ficam na FRENTE (Y pequeno), o corpo atras. Coloca via
place_sofa_boxes (generico: rotaciona -Y -> facing + translada)."""
from __future__ import annotations

from tools.furniture_anatomy_spec import WARDROBE_REQUIRED_PARTS, WardrobeSpec, wardrobe_spec  # noqa: F401
from tools.sofa_builder import PT_TO_IN, _p, parts_to_boxes  # noqa: F401
from tools.sofa_builder import place_sofa_boxes as place_wardrobe_boxes  # noqa: F401  (generico)

MARGIN = 0.03   # margem lateral do conjunto de portas


def build_wardrobe(spec: WardrobeSpec):
    """Devolve (parts, meta). parts = pecas (caixas em m, com z0/z1)."""
    spec.validate()
    W, D, H = spec.width, spec.depth, spec.height
    ph, dt, gap = spec.plinth_h, spec.door_t, spec.door_gap
    n = spec.n_doors()
    body = tuple(spec.body_rgb)
    door = tuple(spec.door_rgb)
    handle = tuple(spec.handle_rgb)
    plinth = tuple(spec.plinth_rgb)
    parts = []

    # --- rodape recuado (base) + corpo (atras das portas) ---
    parts.append(_p("rodape", "rodape", 0.04, 0.04, W - 0.04, D - 0.04, 0.0, ph, plinth))
    parts.append(_p("corpo", "corpo", 0.0, dt, W, D, ph, H, body))

    # --- N portas na FRENTE (Y[0,dt]) com frestas (divisoes verticais) ---
    inner = W - 2 * MARGIN
    door_w = (inner - gap * (n - 1)) / n
    z0d, z1d = ph + 0.02, H - 0.03
    hz0 = (z0d + z1d) / 2 - spec.handle_h / 2
    hz1 = hz0 + spec.handle_h
    for i in range(n):
        dx0 = MARGIN + i * (door_w + gap)
        dx1 = dx0 + door_w
        parts.append(_p(f"porta_{i + 1}", "porta", dx0, 0.0, dx1, dt, z0d, z1d, door))
        # puxador: barra vertical fina na aresta da porta voltada p/ o centro (onde abre)
        cxi = (dx0 + dx1) / 2
        hx = (dx1 - 0.06) if cxi < W / 2 else (dx0 + 0.03)
        parts.append(_p(f"puxador_{i + 1}", "puxador", hx, 0.0, hx + 0.03, dt + 0.04, hz0, hz1, handle))

    meta = {"n_parts": len(parts), "n_doors": n, "bbox_m": spec.bbox_m(),
            "front_axis": "-Y", "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


if __name__ == "__main__":
    for w in (1.2, 1.8, 2.4):
        parts, meta = build_wardrobe(wardrobe_spec(width=w))
        print(f"W={w} {meta['n_parts']} pecas | portas={meta['n_doors']} | kinds={meta['kinds']} | bbox={meta['bbox_m']}")
