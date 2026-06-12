"""armchair_class.py — a TEORIA EXECUTAVEL da classe POLTRONA (armchair de estar).
Cycle 001 do programa arquiteto-de-classe — 2a classe, replicando o template que
levou o SOFA ao PASS (3 ciclos): ranges ergonomicos + relacoes + arquetipos +
derive + gate + sabotagens + matriz.

GEOMETRIA: REUSA tools/sofa_builder.build_sofa com seats=1 — a poltrona herda a
gramatica congelada do sofa (sapata/cap/taper de braco, rake, bevel, overhang,
base_recess). O que a distingue e' a TEORIA: braco proporcionalmente MUITO mais
presente (arm_span_ratio 0.28-0.45 vs ~0.12-0.25 do sofa), footprint quase-
QUADRADO (w/d 0.85-1.15 vs retangulo 2.5:1+ do sofa), encosto que sobe clara-
mente acima do braco. Fonte: tabela ergonomica da classe (workflow 2026-06-12).

Uso: python -m tools.armchair_class           (prova: arquetipos + sabotagens)
     python -m tools.armchair_class --matrix  (matriz visual pro juiz)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.furniture_anatomy_spec import SofaSpec   # noqa: E402

# ----------------------------------------------------------------- faixas duras
ARMCHAIR_RANGES = {
    "seat_height": (0.36, 0.47),
    "seat_depth": (0.48, 0.60),          # util; lounge funda ate 0.60
    "depth": (0.72, 1.05),               # total
    "height": (0.72, 1.18),              # total (lounge/high-back ate 1.18)
    "arm_width": (0.10, 0.26),           # ESPESSURA de cada braco (eixo do estilo).
                                         # >0.26 nao fecha com span<=0.50 e W<=1.05
                                         # dentro da MESMA peca: vira poltrona-e-meia
                                         # (classe FUTURA, nao um knob desta)
    "backrest_rake": (5.0, 28.0),
    "cushion_thickness": (0.10, 0.22),
    "seat_width": (0.45, 0.65),          # util (1 corpo, solo = generoso)
    "width": (0.68, 1.05),               # total; >1.05 = poltrona-e-meia
}
FOOT_EXPOSED = (0.10, 0.22)              # pernas visiveis (standard/lounge)
FOOT_PLINTH = (0.0, 0.08)                # club: saia/base ao chao (faixa propria,
                                         # mais larga que a do sofa)

# ----------------------------------------------------- relacoes (a alma da classe)
RELATIONS = {
    # O DISTINTIVO da poltrona: braco PRESENTE. <0.22 = "sofa de 1 lugar magro";
    # >0.50 = bracos engolem o assento (fresta). NOTA de teoria: seat_util/width
    # e' matematicamente 1-este_ratio — manter UMA regua so (bug de redundancia
    # inconsistente pego no proprio gate, cycle001 da poltrona).
    "arm_span_ratio": (
        lambda s: 2 * s.arm_width / s.width, 0.22, 0.50,
        "2*arm/width fora de [0.22,0.50] — braco de sofa (fino) ou fresta"),
    # poltrona e' quase-quadrada em planta (sofa e' retangulo largo)
    "footprint_quadrado": (
        lambda s: s.width / s.depth, 0.80, 1.30,
        "width/depth fora de [0.80,1.30] — footprint de mini-sofa ou gaveta"),
    # encosto sobe CLARAMENTE acima do braco (senao os planos colapsam em bloco)
    "encosto_acima_do_braco": (
        lambda s: s.height - s.arm_height, 0.16, 0.65,
        "encosto nao sobe >=0.16m acima do braco — bloco sem costas"),
    "suporte_de_costas": (
        lambda s: s.height - s.seat_height, 0.38, 0.80,
        "encosto acima do assento fora de [0.38,0.80]"),
    "braco_apoia_antebraco": (
        lambda s: s.arm_height - s.seat_height, 0.14, 0.30,
        "braco vs assento fora de [0.14,0.30]m — cotovelo alto/baixo demais"),
    "profundidade_coerente": (
        lambda s: s.depth - (s.seat_depth + s.back_thickness), 0.0, 0.30,
        "seat_depth+back_thickness nao cabe em depth (ou sobra demais)"),
    # lounge reclinada pede profundidade: depth_total cresce com o rake
    "recline_pede_profundidade": (
        lambda s: s.depth - 0.72 - max(0.0, (s.backrest_rake - 12.0)) * 0.010,
        0.0, 0.40,
        "rake alto sem profundidade total — usuario escorrega pra fora"),
    "almofada_cabe_na_base": (
        lambda s: (s.seat_height - s.foot_height) - s.cushion_thickness, 0.005, 10.0,
        "cushion_thickness nao cabe entre pes e topo do assento"),
}

# ------------------------------------------------------- arquetipos (intencao)
# eixo: club (bloco aconchegante controlado) <-> standard <-> lounge (recostar).
ARCHETYPES = {
    "club": dict(seat_height=0.43, seat_depth=0.52, seat_width=0.52,
                 back_above_seat=0.46, backrest_rake=9.0, arm_above_seat=0.25,
                 arm_width=0.26, depth=0.86, cushion_thickness=0.17,
                 cushion_bevel=0.04, base_style_default="plinth",
                 foot_legs=0.10, foot_plinth=0.04,
                 arm_cap=False, arm_relief=0.05, arm_taper=0.0,
                 seat_overhang=0.0, base_recess=0.05),
    "standard": dict(seat_height=0.43, seat_depth=0.52, seat_width=0.54,
                     back_above_seat=0.53, backrest_rake=13.0, arm_above_seat=0.21,
                     arm_width=0.18, depth=0.85, cushion_thickness=0.14,
                     cushion_bevel=0.04, base_style_default="legs",
                     foot_legs=0.14, foot_plinth=0.03,
                     arm_cap=True, arm_relief=0.0, arm_taper=0.0,
                     seat_overhang=0.0, base_recess=0.06),
    "lounge": dict(seat_height=0.40, seat_depth=0.57, seat_width=0.55,
                   back_above_seat=0.66, backrest_rake=22.0, arm_above_seat=0.18,
                   arm_width=0.13, depth=0.97, cushion_thickness=0.19,
                   cushion_bevel=0.05, base_style_default="legs",
                   foot_legs=0.16, foot_plinth=0.03,
                   arm_cap=False, arm_relief=0.0, arm_taper=0.0,
                   seat_overhang=0.04, base_recess=0.09),
}


def derive_armchair_spec(archetype="standard", base_style=None, **overrides) -> SofaSpec:
    """Deriva a poltrona PELA CLASSE como SofaSpec(seats=1) — reusa a gramatica
    congelada do sofa; largura = seat_width + 2*arm_width (nunca chutada)."""
    assert archetype in ARCHETYPES, f"arquetipo desconhecido: {archetype}"
    a = ARCHETYPES[archetype]
    base_style = base_style or a["base_style_default"]
    assert base_style in ("legs", "plinth")
    foot_h = a["foot_legs"] if base_style == "legs" else a["foot_plinth"]
    spec = SofaSpec(
        variant="straight", seats=1,
        width=round(a["seat_width"] + 2 * a["arm_width"], 3),
        depth=a["depth"],
        height=round(a["seat_height"] + a["back_above_seat"], 3),
        seat_height=a["seat_height"], seat_depth=a["seat_depth"],
        back_thickness=0.20,
        arm_width=a["arm_width"],
        arm_height=round(a["seat_height"] + a["arm_above_seat"], 3),
        foot_height=foot_h,
        cushion_thickness=a["cushion_thickness"],
        cushion_bevel=a["cushion_bevel"],
        backrest_rake=a["backrest_rake"],
        arm_cap=a["arm_cap"], arm_relief=a["arm_relief"], arm_taper=a["arm_taper"],
        seat_overhang=a["seat_overhang"], base_recess=a["base_recess"],
    )
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec.validate()


def armchair_class_gate(spec: SofaSpec, parts=None):
    """Gate de PROPORCAO da classe poltrona. {result, errors, warnings, metrics}."""
    errors, warnings, metrics = [], [], {}
    seat_w = spec.width - 2 * spec.arm_width
    vals = {
        "seat_height": spec.seat_height, "seat_depth": spec.seat_depth,
        "depth": spec.depth, "height": spec.height, "arm_width": spec.arm_width,
        "backrest_rake": spec.backrest_rake,
        "cushion_thickness": spec.cushion_thickness,
        "seat_width": seat_w, "width": spec.width,
    }
    metrics["seat_width_m"] = round(seat_w, 3)
    for k, (lo, hi) in ARMCHAIR_RANGES.items():
        v = vals[k]
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{k}={v:.3f} fora da faixa de classe [{lo},{hi}]")

    if spec.seats != 1:
        errors.append(f"poltrona tem 1 lugar (seats={spec.seats})")

    fh = spec.foot_height
    in_legs = FOOT_EXPOSED[0] - 1e-9 <= fh <= FOOT_EXPOSED[1] + 1e-9
    in_plinth = FOOT_PLINTH[0] - 1e-9 <= fh <= FOOT_PLINTH[1] + 1e-9
    metrics["base_style"] = "legs" if in_legs else "plinth" if in_plinth else "ambiguo"
    if not (in_legs or in_plinth):
        errors.append(f"foot_height={fh:.3f} no vale (nem saia<=0.08 nem pes>=0.10)")

    for name, (fn, lo, hi, msg) in RELATIONS.items():
        v = fn(spec)
        metrics[name] = round(v, 3)
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{name}={v:.3f}: {msg}")

    # anti-pattern de linguagem: pernas-palito sob corpo macico de club
    if spec.arm_width >= 0.24 and fh >= 0.18:
        warnings.append("pernas altas sob corpo macico de club — conflito de linguagem")

    if parts is not None:
        kinds = {p["kind"] for p in parts}
        need = {"base", "seat_cushion", "back_cushion", "arm", "foot"}
        missing = need - kinds
        if missing:
            errors.append(f"partes obrigatorias ausentes: {sorted(missing)}")

    result = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {"result": result, "errors": errors, "warnings": warnings,
            "metrics": metrics}


# ------------------------------------------------------------------ sabotagens
def _raw(**kw):
    s = SofaSpec(seats=1, width=0.90, depth=0.85, height=0.96,
                 seat_height=0.43, seat_depth=0.52, arm_width=0.18,
                 arm_height=0.64, foot_height=0.14, backrest_rake=13.0)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _sabotages():
    return [
        ("braco de sofa (fino 0.08 = '1 lugar magro')", lambda: _raw(arm_width=0.08)),
        ("fresta (bracos 0.30 engolem assento 0.90)", lambda: _raw(arm_width=0.30)),
        ("footprint de mini-sofa (1.4x0.85)", lambda: _raw(width=1.40, arm_width=0.35)),
        ("bloco (encosto na altura do braco)", lambda: _raw(arm_height=0.92)),
        ("lounge rasa reclinada (rake 26, depth 0.74)",
         lambda: _raw(backrest_rake=26.0, depth=0.74)),
        ("banqueta alta (assento 0.52)", lambda: _raw(seat_height=0.52, height=1.05)),
    ]


# ------------------------------------------------------------------ matriz
MATRIX = [
    ("club-plinth", dict(archetype="club", base_style="plinth")),
    ("club-legs", dict(archetype="club", base_style="legs")),
    ("club-wide", dict(archetype="club", base_style="plinth", arm_width=0.26,
                       width=round(0.53 + 2 * 0.26, 3))),
    ("standard-legs", dict(archetype="standard")),
    ("standard-plinth", dict(archetype="standard", base_style="plinth")),
    ("standard-slim-arm", dict(archetype="standard", arm_width=0.14,
                               width=0.54 + 2 * 0.14)),
    ("lounge-legs", dict(archetype="lounge")),
    ("lounge-deep", dict(archetype="lounge", seat_depth=0.60, depth=1.01)),
    ("lounge-highback", dict(archetype="lounge", height=1.14)),
]


def build_matrix(out_dir):
    from tools.render_parts_iso import render_parts
    from tools.sofa_builder import build_sofa
    from tools.sofa_class_matrix import _grid_sheet
    import json as _json
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report, cells = [], []
    for name, kw in MATRIX:
        spec = derive_armchair_spec(**kw)
        cls = armchair_class_gate(spec)
        parts, meta = build_sofa(spec)
        png = out / f"cell_{name}.png"
        render_parts(parts, png, elev=22, azim=-55,
                     title=f"{name}  W={spec.width:.2f}m")
        report.append({"cell": name, "params": kw, "width_m": spec.width,
                       "bbox_m": meta["bbox_m"], "class_gate": cls["result"],
                       "class_errors": cls["errors"], "n_parts": meta["n_parts"]})
        cells.append((name, png, cls["result"], "-"))
    sheet = _grid_sheet(cells, out / "armchair_class_matrix.png",
                        "CLASSE POLTRONA — matriz de generalizacao (derivada por "
                        "arquetipo, builder do sofa com seats=1)")
    (out / "matrix_report.json").write_text(
        _json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"sheet": sheet, "report": report}


if __name__ == "__main__":
    if "--matrix" in sys.argv:
        res = build_matrix(ROOT / "runs/armchair_class/matrix")
        print(f"=== matriz da classe poltrona: {len(res['report'])} celulas ===")
        for r in res["report"]:
            print(f"  {r['cell']:20} W={r['width_m']:.2f} class={r['class_gate']:4} "
                  f"parts={r['n_parts']} {r['class_errors'][:1]}")
        print(f"  -> {res['sheet']}")
        sys.exit(1 if any(r["class_gate"] == "FAIL" for r in res["report"]) else 0)
    print("=== armchair_class: arquetipos x bases ===")
    bad = 0
    for arch in ARCHETYPES:
        for base in ("legs", "plinth"):
            s = derive_armchair_spec(arch, base)
            r = armchair_class_gate(s)
            if r["result"] == "FAIL":
                bad += 1
                print(f"  XXX {arch:9} {base:6} W={s.width:.2f} -> {r['errors'][:2]}")
    print(f"  derivados validos: {6 - bad}/6")
    print("=== sabotagens (devem FALHAR) ===")
    ok = bad == 0
    for name, mk in _sabotages():
        r = armchair_class_gate(mk())
        hit = r["result"] == "FAIL"
        ok = ok and hit
        print(f"  {'XXX' if hit else '!!! PASSOU'} {name} -> {r['result']}")
    print("TODOS OK" if ok else "FALHOU")
    sys.exit(0 if ok else 1)
