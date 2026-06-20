"""coffee_table_class.py — a TEORIA EXECUTAVEL da classe MESA DE CENTRO (4a classe
do programa arquiteto-de-classe). A novidade institucional: esta classe e' SATELITE
DO SOFA por construcao — a mesa NAO tem tamanho proprio, ela se DERIVA do sofa que
serve (comprimento = 0.5-0.66 do sofa; tampo NUNCA acima do assento; "classe
principal define a regua; classe satelite se adapta" — padrao oficial do juiz).

Geometria PROPRIA (autocontida — NAO toca decor_builders.coffee_table, que a cena
Intent-to-Scene PASS usa): 3 arquetipos com gramatica distinta:
  low_slab    — laje grossa proposital + base painel recuado (monolitica, rente)
  two_tier    — tampo fino + 4 pernas retas + prateleira inferior funcional
  organic     — tampo de cantos suavizados (racetrack low-poly) + pernas CONICAS
                (verts8 taper) com ar leve

Uso: python -m tools.coffee_table_class           (prova + sabotagens)
     python -m tools.coffee_table_class --matrix  (matriz 9 pro juiz)
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.sofa_builder import _darker, _p   # noqa: E402  (primitivas compartilhadas)

# ----------------------------------------------------------------- faixas duras
CT_RANGES = {
    "height": (0.30, 0.48),
    "length": (0.70, 1.40),
    "width": (0.45, 0.75),
    "top_t": (0.02, 0.10),
    "leg_t": (0.03, 0.09),
}

RELATIONS = {
    "aspecto_horizontal": (
        lambda s: s.length / s.width, 1.30, 2.20,
        "length/width fora de [1.3,2.2] — tabua estreita ou quase-quadrada"),
    "tampo_fino": (
        lambda s: s.top_t / s.length, 0.015, 0.105,
        "espessura/comprimento fora — tampo papel ou bloco"),
    "leveza_das_pernas": (
        lambda s: s.leg_inset / s.width, 0.04, 0.30,
        "inset/width fora — base estoura a borda ou encolhe demais"),
}

# --------------------------------------------- SATELITE DO SOFA (regua critica)
SOFA_DELTA = (-0.10, 0.0)      # tampo NUNCA acima do assento; otimo -0.03
SOFA_LEN_FRAC = (0.48, 0.68)   # comprimento = 1/2 a 2/3 do sofa
# SATURACAO (tensao de teoria do cycle001): o alcance humano e a circulacao
# central NAO escalam com o sofa — a mesa satura em ~1.40m. Em sofas XL
# (>=2.6m) a fracao minima relaxa: a mesa serve o CENTRO; pontas usam laterais.
SOFA_XL = 2.60
SOFA_LEN_FRAC_XL_LO = 0.44


def sofa_satellite_gate(spec, sofa_width, sofa_seat_height):
    """A mesa contra o SOFA que ela serve. {result, errors, metrics}."""
    errors, metrics = [], {}
    delta = spec.height - sofa_seat_height
    frac = spec.length / sofa_width
    lo = SOFA_LEN_FRAC_XL_LO if sofa_width >= SOFA_XL else SOFA_LEN_FRAC[0]
    metrics["delta_vs_assento_m"] = round(delta, 3)
    metrics["frac_do_sofa"] = round(frac, 3)
    metrics["alvo_height_m"] = round(sofa_seat_height - 0.03, 3)
    if not (SOFA_DELTA[0] - 1e-9 <= delta <= SOFA_DELTA[1] + 1e-9):
        errors.append(f"tampo a {delta:+.2f}m do assento do sofa "
                      f"(regra [{SOFA_DELTA[0]},{SOFA_DELTA[1]}]) — "
                      "tampo NUNCA acima do assento")
    if not (lo - 1e-9 <= frac <= SOFA_LEN_FRAC[1] + 1e-9):
        errors.append(f"comprimento = {frac:.2f} do sofa "
                      f"(regra dos 2/3: [{lo},{SOFA_LEN_FRAC[1]}]) "
                      "— ilha perdida ou pista de pouso")
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "metrics": metrics}


# ------------------------------------------------------------------ spec
@dataclass
class CoffeeTableClassSpec:
    """Mesa de centro da CLASSE (v2, autocontida). Metros; X=length (eixo do
    sofa), Y=width (profundidade), Z=altura; frente = -Y."""
    style: str = "two_tier"        # low_slab | two_tier | organic
    length: float = 1.20
    width: float = 0.62
    height: float = 0.40
    top_t: float = 0.04
    leg_t: float = 0.05
    leg_inset: float = 0.08
    leg_taper: float = 0.0         # organic: pernas conicas (fracao de afinamento)
    shelf: bool = False            # two_tier: prateleira inferior
    shelf_gap_floor: float = 0.12
    round_corners: bool = False    # organic: cantos suavizados (octogono via verts8)
    corner_ear_frac: float = 0.18  # organic: fracao do comprimento que vira chanfro
    corner_soft_frac: float = 0.30 # organic: reducao de largura na ponta (raio percebido)
    slab_reveal: float = 0.05      # low_slab: sombra/recuo no rodape do painel
    top_rgb: tuple = (206, 193, 171)
    leg_rgb: tuple = (38, 38, 40)

    def validate(self):
        assert self.style in ("low_slab", "two_tier", "organic")
        assert self.height > self.top_t
        assert self.length > self.width
        if self.shelf:
            shelf_top = self.shelf_gap_floor + 0.03
            assert (self.height - self.top_t) - shelf_top >= 0.18, \
                "vao prateleira->tampo < 0.18 (entupido)"
            assert self.shelf_gap_floor >= 0.06, "prateleira colada no chao"
        return self

    def bbox_m(self):
        return (round(self.length, 3), round(self.width, 3), round(self.height, 3))

    def to_dict(self):
        d = asdict(self)
        d["bbox_m"] = self.bbox_m()
        return d


def build_coffee_table_v2(spec: CoffeeTableClassSpec):
    """(parts, meta) no contrato padrao. Gramatica por arquetipo."""
    spec.validate()
    L, W, H, tt = spec.length, spec.width, spec.height, spec.top_t
    top, legc = tuple(spec.top_rgb), tuple(spec.leg_rgb)
    parts = []
    z_top0 = H - tt

    # tampo: reto OU OCTOGONO real (cycle002: alas TRAPEZOIDAIS verts8 — chanfro
    # amplo que le como raio, nao "retangulo com abas")
    if spec.round_corners:
        ear = spec.corner_ear_frac * L
        soft = spec.corner_soft_frac * W / 2.0
        parts.append(_p("top_center", "top", ear, 0.0, L - ear, W, z_top0, H, top))
        for tag, (xa, xb) in (("l", (ear, 0.0)), ("r", (L - ear, L))):
            pa = _p(f"top_{tag}", "top", min(xa, xb), 0.0, max(xa, xb), W,
                    z_top0, H, top)
            pa["verts8"] = [
                (xa, 0.0, z_top0), (xb, soft, z_top0),
                (xb, W - soft, z_top0), (xa, W, z_top0),
                (xa, 0.0, H), (xb, soft, H), (xb, W - soft, H), (xa, W, H)]
            parts.append(pa)
    else:
        parts.append(_p("top", "top", 0.0, 0.0, L, W, z_top0, H, top))

    ins = spec.leg_inset
    if spec.style == "low_slab":
        # base painel recuado COM REVEAL no rodape (cycle002: sombra inferior —
        # "desenhada, nao bloco extrudado"; mesma familia da regra da cama)
        rv = spec.slab_reveal
        parts.append(_p("base_shadow", "leg", ins + 0.04, ins * 0.7 + 0.03,
                        L - ins - 0.04, W - ins * 0.7 - 0.03, 0.0, rv,
                        _darker(top, 0.5)))
        parts.append(_p("base_panel", "leg", ins, ins * 0.7, L - ins, W - ins * 0.7,
                        rv, z_top0, _darker(top, 0.8)))
    else:
        lt = spec.leg_t
        for tag, (x0, y0) in (("fl", (ins, ins)), ("fr", (L - ins - lt, ins)),
                              ("bl", (ins, W - ins - lt)),
                              ("br", (L - ins - lt, W - ins - lt))):
            p = _p(f"leg_{tag}", "leg", x0, y0, x0 + lt, y0 + lt, 0.0, z_top0, legc)
            if spec.leg_taper > 0:   # conica: base mais fina (verts8 taper)
                sh = lt * spec.leg_taper / 2.0
                p["verts8"] = [
                    (x0 + sh, y0 + sh, 0.0), (x0 + lt - sh, y0 + sh, 0.0),
                    (x0 + lt - sh, y0 + lt - sh, 0.0), (x0 + sh, y0 + lt - sh, 0.0),
                    (x0, y0, z_top0), (x0 + lt, y0, z_top0),
                    (x0 + lt, y0 + lt, z_top0), (x0, y0 + lt, z_top0)]
            parts.append(p)
        if spec.shelf:
            sz0 = spec.shelf_gap_floor
            parts.append(_p("shelf", "top", ins + 0.02, ins * 0.8, L - ins - 0.02,
                            W - ins * 0.8, sz0, sz0 + 0.03, _darker(top, 0.9)))
    meta = {"type": "coffee_table_v2", "style": spec.style, "n_parts": len(parts),
            "bbox_m": spec.bbox_m(), "front_axis": "-Y",
            "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


# ------------------------------------------------------- arquetipos + derive
ARCHETYPES = {
    "low_slab": dict(aspect=1.85, top_t=0.08, leg_inset_ratio=0.22,
                     height_drop=0.07, leg_t=0.05, taper=0.0,
                     shelf=False, round_corners=False,
                     leg_rgb=(38, 38, 40)),
    "two_tier": dict(aspect=1.80, top_t=0.04, leg_inset_ratio=0.12,
                     height_drop=0.02, leg_t=0.045, taper=0.0,
                     shelf=True, round_corners=False,
                     leg_rgb=(110, 86, 64)),    # madeira clara (juiz: pretas pesavam)
    "organic": dict(aspect=1.55, top_t=0.03, leg_inset_ratio=0.17,
                    height_drop=0.03, leg_t=0.045, taper=0.55,
                    shelf=False, round_corners=True,
                    leg_rgb=(110, 86, 64)),
}


def derive_coffee_spec(sofa_width=2.16, sofa_seat_height=0.43,
                       archetype="two_tier", **overrides) -> CoffeeTableClassSpec:
    """A mesa se DERIVA do sofa que serve (satelite por construcao):
    comprimento = 0.58 do sofa; tampo = assento - height_drop do arquetipo."""
    assert archetype in ARCHETYPES
    a = ARCHETYPES[archetype]
    length = round(min(1.40, max(0.70, 0.58 * sofa_width)), 3)
    width = round(min(0.75, max(0.45, length / a["aspect"])), 3)
    spec = CoffeeTableClassSpec(
        style=archetype if archetype != "two_tier" else "two_tier",
        length=length, width=width,
        height=round(sofa_seat_height - a["height_drop"], 3),
        top_t=a["top_t"], leg_t=a["leg_t"],
        leg_inset=round(a["leg_inset_ratio"] * width, 3),
        leg_taper=a["taper"], shelf=a["shelf"],
        round_corners=a["round_corners"], leg_rgb=a["leg_rgb"],
    )
    spec.style = "low_slab" if archetype == "low_slab" else \
        "organic" if archetype == "organic" else "two_tier"
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec.validate()


def coffee_table_class_gate(spec: CoffeeTableClassSpec, parts=None):
    errors, warnings, metrics = [], [], {}
    vals = {"height": spec.height, "length": spec.length, "width": spec.width,
            "top_t": spec.top_t, "leg_t": spec.leg_t}
    for k, (lo, hi) in CT_RANGES.items():
        v = vals[k]
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{k}={v:.3f} fora da faixa de classe [{lo},{hi}]")
    for name, (fn, lo, hi, msg) in RELATIONS.items():
        v = fn(spec)
        metrics[name] = round(v, 3)
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{name}={v:.3f}: {msg}")
    # coerencia estilo<->geometria (mesma disciplina das outras classes)
    if spec.style == "low_slab" and spec.top_t < 0.06:
        errors.append("low_slab exige laje (top_t>=0.06)")
    if spec.style != "low_slab" and spec.top_t > 0.06:
        errors.append("tampo grosso fora do slab — bloco sem intencao")
    if spec.style == "organic" and spec.leg_taper <= 0:
        errors.append("organic exige perna conica (taper>0)")
    if spec.style == "organic":
        if not spec.round_corners or spec.corner_ear_frac < 0.12                 or spec.corner_soft_frac < 0.20:
            errors.append("silhueta organica imperceptivel (ear>=0.12L e "
                          "soft>=0.20W — chanfro deve ler como raio)")
    if spec.style == "low_slab" and spec.slab_reveal < 0.03:
        errors.append("low_slab sem reveal no rodape — caixa com tampo")
    if parts is not None:
        kinds = {p["kind"] for p in parts}
        if not {"top", "leg"} <= kinds:
            errors.append(f"partes obrigatorias ausentes: {sorted({'top','leg'} - kinds)}")
    result = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {"result": result, "errors": errors, "warnings": warnings,
            "metrics": metrics}


# ------------------------------------------------------------------ sabotagens
def _sabotages():
    return [
        ("tampo ACIMA do assento (anti-pattern n.1)",
         lambda: (derive_coffee_spec(2.16, 0.43), 2.16, 0.43, dict(height=0.48))),
        ("ilha pequena (0.35 do sofa)",
         lambda: (derive_coffee_spec(2.16, 0.43), 2.16, 0.43, dict(length=0.75))),
        ("tabua (aspect 2.6)",
         lambda: (derive_coffee_spec(2.16, 0.43), 2.16, 0.43,
                  dict(length=1.30, width=0.50))),
        ("bloco (tampo 0.12 fora do slab)",
         lambda: (derive_coffee_spec(2.16, 0.43), 2.16, 0.43, dict(top_t=0.12))),
        ("base caixote (sem inset)",
         lambda: (derive_coffee_spec(2.16, 0.43), 2.16, 0.43, dict(leg_inset=0.01))),
        ("prateleira colada no chao",
         lambda: (derive_coffee_spec(2.16, 0.43, "two_tier"), 2.16, 0.43,
                  dict(shelf_gap_floor=0.03))),
        ("organic de mentira (chanfro imperceptivel)",
         lambda: (derive_coffee_spec(2.16, 0.43, "organic"), 2.16, 0.43,
                  dict(corner_ear_frac=0.06, corner_soft_frac=0.10))),
        ("slab caixa-com-tampo (sem reveal)",
         lambda: (derive_coffee_spec(2.16, 0.43, "low_slab"), 2.16, 0.43,
                  dict(slab_reveal=0.0))),
    ]


def _apply_sab(mk):
    spec, sw, ssh, over = mk()
    bad_validate = False
    for k, v in over.items():
        setattr(spec, k, v)
    try:
        spec.validate()
    except AssertionError:
        bad_validate = True
    g = coffee_table_class_gate(spec)
    s = sofa_satellite_gate(spec, sw, ssh)
    fail = bad_validate or g["result"] == "FAIL" or s["result"] == "FAIL"
    return fail


# ------------------------------------------------------------------ matriz
# o EIXO da matriz e' o SOFA SERVIDO (a regua satelite e' a derivacao):
# formal-2l (W=1.48, seat 0.45) / standard-3l (2.16, 0.43) / lounge-4l (3.00, 0.40)
SOFAS_REF = [("sofa-formal-2l", 1.48, 0.45), ("sofa-std-3l", 2.16, 0.43),
             ("sofa-lounge-4l", 3.00, 0.40)]
MATRIX = [(f"{arch}@{sname}", arch, sw, ssh)
          for arch in ARCHETYPES for sname, sw, ssh in SOFAS_REF]


def build_matrix(out_dir):
    from tools.render_parts_iso import render_parts
    from tools.sofa_class_matrix import _grid_sheet
    import json as _json
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report, cells = [], []
    for name, arch, sw, ssh in MATRIX:
        spec = derive_coffee_spec(sw, ssh, arch)
        cls = coffee_table_class_gate(spec)
        sat = sofa_satellite_gate(spec, sw, ssh)
        parts, meta = build_coffee_table_v2(spec)
        png = out / f"cell_{name.replace('@', '_')}.png"
        render_parts(parts, png, elev=22, azim=-55,
                     title=f"{name}  {spec.length:.2f}x{spec.width:.2f}x{spec.height:.2f}")
        report.append({"cell": name, "bbox_m": meta["bbox_m"],
                       "class_gate": cls["result"], "class_errors": cls["errors"],
                       "satellite": sat["result"], "sat_metrics": sat["metrics"],
                       "n_parts": meta["n_parts"]})
        cells.append((name, png, cls["result"], sat["result"]))
    sheet = _grid_sheet(cells, out / "coffee_table_class_matrix.png",
                        "CLASSE MESA DE CENTRO — derivada DO SOFA que serve "
                        "(satelite por construcao; linhas=arquetipo, colunas=sofa)")
    (out / "matrix_report.json").write_text(
        _json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"sheet": sheet, "report": report}


if __name__ == "__main__":
    if "--matrix" in sys.argv:
        res = build_matrix(ROOT / "runs/coffee_table_class/matrix")
        print(f"=== matriz da classe mesa de centro: {len(res['report'])} ===")
        for r in res["report"]:
            print(f"  {r['cell']:26} class={r['class_gate']:4} sat={r['satellite']:4} "
                  f"delta={r['sat_metrics']['delta_vs_assento_m']:+.2f} "
                  f"frac={r['sat_metrics']['frac_do_sofa']:.2f}")
        print(f"  -> {res['sheet']}")
        bad = [r for r in res["report"]
               if r["class_gate"] == "FAIL" or r["satellite"] == "FAIL"]
        sys.exit(1 if bad else 0)
    print("=== coffee_table_class: arquetipos x sofas ===")
    bad = 0
    for arch in ARCHETYPES:
        for sname, sw, ssh in SOFAS_REF:
            spec = derive_coffee_spec(sw, ssh, arch)
            g = coffee_table_class_gate(spec)
            s = sofa_satellite_gate(spec, sw, ssh)
            if g["result"] == "FAIL" or s["result"] == "FAIL":
                bad += 1
                print(f"  XXX {arch:10} {sname:16} {g['errors'][:1]} {s['errors'][:1]}")
    print(f"  derivados validos: {9 - bad}/9")
    print("=== sabotagens (devem FALHAR) ===")
    ok = bad == 0
    for name, mk in _sabotages():
        hit = _apply_sab(mk)
        ok = ok and hit
        print(f"  {'XXX' if hit else '!!! PASSOU'} {name}")
    print("TODOS OK" if ok else "FALHOU")
    sys.exit(0 if ok else 1)
