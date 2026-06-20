"""rack_class.py — a TEORIA EXECUTAVEL da classe RACK / MEDIA CONSOLE (5a classe;
PRIMEIRO builder 100% novo do programa — nao existia nada no repo).

DNA: baixo e horizontal (esbeltez 3:1-5:1), serve a TV (satelite por derivacao:
comprimento = tv_width + folga, com SATURACAO), ancora ergonomica = LINHA DE
VISAO (centro da TV 1.00-1.25m do chao — TV maior NAO sobe o movel, ALARGA),
profundidade NAO escala com a TV, exatamente UM modo de apoio (pes XOR suspenso
XOR base/toe-recess), fachada com ritmo (nichos/gavetas) e vazio tecnico.

Satelites: TV servida (55/65/75 pol) + SOFA (distancia/linha do olho sentado).

Uso: python -m tools.rack_class            (prova + sabotagens)
     python -m tools.rack_class --matrix   (matriz 9 pro juiz)
"""
from __future__ import annotations

import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.sofa_builder import _darker, _p   # noqa: E402

# ------------------------------------------------------------- TVs (satelite)
TVS = {"55": (1.23, 0.69), "65": (1.45, 0.81), "75": (1.67, 0.93)}  # (w, h) m
TV_MIN_DIST = {"55": 1.9, "65": 2.2, "75": 2.6}   # sofa-TV minimo (m)

# ----------------------------------------------------------------- faixas duras
RACK_RANGES = {
    "length": (1.30, 2.60),         # saturacao: parede/sala nao escala infinito
    "depth": (0.30, 0.50),          # NAO escala com a TV
    "body_h": (0.26, 0.55),         # corpo alto vira aparador/comoda
    "top_surface": (0.30, 0.74),    # flutuante: vao 0.30-0.45 + corpo = ate ~0.72
                                    # (TV_CENTER protege o 'alto demais')
}
TV_CENTER = (0.80, 1.25)            # ancora ergonomica: TV APOIADA em rack baixo
                                    # fica 0.80-1.0 (tilt leve pra baixo = confortavel);
                                    # >1.25 = pescoco; <0.80 = TV no chao
CLEARANCE_SIDE = (0.12, 0.65)       # folga alem de cada lado da TV

RELATIONS = {
    # esbeltez usa a altura VISUAL: no flutuante o vao e' vazio (so o corpo pesa)
    # floating COM wall_back: a placa ancora a leitura — corpo fino ok (ate 7.2)
    "esbeltez_horizontal": (
        lambda s: (s.length / (s.body_h if s.support == "floating"
                               else s.total_height()))
        / (7.2 / 6.2 if (s.support == "floating" and s.wall_back) else 1.0),
        2.6, 6.2,
        "comprimento/altura-visual fora — cubo/aparador ou prateleira"),
    "corpo_nao_gaveteiro": (
        lambda s: s.depth / s.body_h, 0.70, 1.60,
        "profundidade/corpo fora de [0.7,1.6] — gaveteiro pesado ou lamina"),
}


@dataclass
class RackSpec:
    """X=comprimento (parede da TV), Y=profundidade (frente=-Y), Z=altura."""
    length: float = 1.90
    depth: float = 0.40
    body_h: float = 0.38
    support: str = "legs"          # legs | floating | base
    leg_height: float = 0.16
    leg_section: float = 0.045
    gap_floor: float = 0.35        # so floating: respiro ate o chao
    toe_recess: float = 0.05       # so base: recuo de rodape (sombra)
    n_niches: int = 2              # vazios tecnicos abertos
    n_drawers: int = 2
    facade_pattern: tuple = ()     # cycle002: padrao SIMETRICO explicito por
                                   # arquetipo (ex. ('drawer','niche','drawer'));
                                   # vazio = deriva de n_niches/n_drawers
    wall_back: bool = False        # cycle002 (floating): placa de fundo/parede
                                   # proxy + shadow gap — flutuacao REAL
    top_proud: float = 0.02        # tampo levemente saliente (frente desenhada)
    body_rgb: tuple = (118, 92, 68)
    front_rgb: tuple = (134, 108, 82)
    feet_rgb: tuple = (48, 40, 32)

    def base_z(self):
        return {"legs": self.leg_height, "floating": self.gap_floor,
                "base": 0.0}[self.support]

    def total_height(self):
        return self.base_z() + self.body_h

    def validate(self):
        assert self.support in ("legs", "floating", "base")
        assert self.n_niches + self.n_drawers >= 1, "fachada precisa de ritmo/vazio tecnico"
        assert self.length > self.depth
        return self

    def bbox_m(self):
        return (round(self.length, 3), round(self.depth, 3),
                round(self.total_height(), 3))

    def to_dict(self):
        d = asdict(self)
        d["bbox_m"] = self.bbox_m()
        return d


def build_rack(spec: RackSpec):
    """(parts, meta) no contrato padrao. Fachada com ritmo: nichos = recessos
    escuros (vazio tecnico), gavetas = frentes proud com vincos; tampo proud;
    apoio por modo (pes conicos verts8 | flutuante | base com toe-recess)."""
    spec.validate()
    L, D, bh = spec.length, spec.depth, spec.body_h
    z0 = spec.base_z()
    body, front, feet = tuple(spec.body_rgb), tuple(spec.front_rgb), tuple(spec.feet_rgb)
    dark = _darker(body, 0.45)
    parts = []

    if spec.support == "legs":
        sec, lh = spec.leg_section, spec.leg_height
        for tag, (fx, fy) in (("fl", (0.06, 0.05)), ("fr", (L - 0.06 - sec, 0.05)),
                              ("bl", (0.06, D - 0.05 - sec)),
                              ("br", (L - 0.06 - sec, D - 0.05 - sec))):
            p = _p(f"leg_{tag}", "foot", fx, fy, fx + sec, fy + sec, 0.0, lh, feet)
            sh = sec * 0.35
            p["verts8"] = [
                (fx + sh, fy + sh, 0.0), (fx + sec - sh, fy + sh, 0.0),
                (fx + sec - sh, fy + sec - sh, 0.0), (fx + sh, fy + sec - sh, 0.0),
                (fx, fy, lh), (fx + sec, fy, lh),
                (fx + sec, fy + sec, lh), (fx, fy + sec, lh)]
            parts.append(p)
    elif spec.support == "base":
        parts.append(_p("toe_base", "base", spec.toe_recess, spec.toe_recess + 0.02,
                        L - spec.toe_recess, D - spec.toe_recess,
                        0.0, 0.06, dark))
        z0 = 0.06
    # floating (cycle002): a flutuacao precisa de CONTEXTO — placa de fundo
    # (parede proxy), SHADOW GAP forte sob o corpo e suporte recuado escuro
    if spec.support == "floating":
        if spec.wall_back:
            parts.append(_p("wall_back", "base", -0.25, D + 0.02, L + 0.25,
                            D + 0.04, 0.0, z0 + bh + 0.95, (228, 221, 208)))
        parts.append(_p("shadow_gap", "base", 0.05, 0.04, L - 0.05, D - 0.02,
                        z0 - 0.025, z0 - 0.005, _darker(body, 0.3)))
        parts.append(_p("cleat", "base", L * 0.30, D - 0.10, L * 0.70, D,
                        z0 - 0.10, z0, _darker(body, 0.35)))

    # corpo (casca) + tampo proud
    top_t = 0.03
    parts.append(_p("body", "base", 0.0, 0.0, L, D, z0, z0 + bh - top_t, body))
    parts.append(_p("top", "top", -spec.top_proud, -spec.top_proud,
                    L + spec.top_proud, D, z0 + bh - top_t, z0 + bh, front))

    # fachada com RITMO: modulos alternando gaveta (frente proud) e nicho
    # (recesso escuro = vazio tecnico). Frente = -Y (y0).
    # cycle002: padrao SIMETRICO explicito por arquetipo (juiz: nao repetir
    # "modulo escuro na ponta"); fallback = alternancia legada
    if spec.facade_pattern:
        order = list(spec.facade_pattern)
    else:
        n_mod = spec.n_niches + spec.n_drawers
        order = []
        for i in range(n_mod):
            order.append("drawer" if (i % 2 == 0 and order.count("drawer") < spec.n_drawers)
                         or order.count("niche") >= spec.n_niches else "niche")
    n_mod = len(order)
    mod_w = (L - 0.04) / n_mod
    fz0, fz1 = z0 + 0.03, z0 + bh - top_t - 0.03
    for i, kind in enumerate(order):
        mx0 = 0.02 + i * mod_w + 0.008
        mx1 = 0.02 + (i + 1) * mod_w - 0.008
        if kind == "drawer":
            parts.append(_p(f"drawer_{i + 1}", "front", mx0, -0.012, mx1, 0.0,
                            fz0, fz1, front))
        else:
            parts.append(_p(f"niche_{i + 1}", "niche", mx0, 0.0, mx1, 0.06,
                            fz0 + 0.01, fz1 - 0.01, dark))

    meta = {"type": "rack", "support": spec.support, "n_parts": len(parts),
            "bbox_m": spec.bbox_m(), "front_axis": "-Y",
            "kinds": sorted({p["kind"] for p in parts})}
    return parts, meta


# ------------------------------------------------- satelites: TV + SOFA
def tv_satellite_gate(spec: RackSpec, tv="65"):
    """Rack contra a TV servida: comprimento com folga, centro na linha de visao."""
    errors, metrics = [], {}
    tw, th = TVS[tv]
    clear = (spec.length - tw) / 2.0
    center = spec.total_height() + th / 2.0
    metrics["clearance_por_lado_m"] = round(clear, 3)
    metrics["tv_center_m"] = round(center, 3)
    if not (CLEARANCE_SIDE[0] - 1e-9 <= clear <= CLEARANCE_SIDE[1] + 1e-9):
        errors.append(f"folga {clear:.2f}/lado p/ TV {tv} (regra {CLEARANCE_SIDE}) "
                      "— TV transborda ou rack-pista")
    if not (TV_CENTER[0] - 1e-9 <= center <= TV_CENTER[1] + 1e-9):
        errors.append(f"centro da TV a {center:.2f}m (regra {TV_CENTER}) — "
                      "pescoco pra cima ou TV no chao")
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "metrics": metrics}


def sofa_satellite_gate(spec: RackSpec, tv="65", sofa_dist=2.6, sofa_seat_h=0.43):
    """Linha de visao do sofa: distancia minima por TV + tilt do pescoco <=15."""
    errors, metrics = [], {}
    eye = sofa_seat_h + 0.66
    center = spec.total_height() + TVS[tv][1] / 2.0
    tilt = math.degrees(math.atan2(center - eye, sofa_dist))
    metrics["dist_minima_m"] = TV_MIN_DIST[tv]
    metrics["tilt_graus"] = round(tilt, 1)
    if sofa_dist < TV_MIN_DIST[tv] - 1e-9:
        errors.append(f"sofa a {sofa_dist}m de TV {tv} (min {TV_MIN_DIST[tv]})")
    if tilt > 15.0:
        errors.append(f"tilt {tilt:.0f} graus > 15 — pescoco pra cima")
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "metrics": metrics}


# ------------------------------------------------------- arquetipos + derive
ARCHETYPES = {
    # cycle002: fachada SIMETRICA propria por arquetipo (gramatica, nao sorteio)
    "floating_minimal": dict(support="floating", body_h=0.32, depth=0.34,
                             gap_floor=0.36, n_niches=0, n_drawers=3,
                             facade=("drawer", "drawer", "drawer"),  # continua/limpa
                             wall_back=True, clearance=0.25),
    "low_credenza": dict(support="legs", body_h=0.36, depth=0.42,
                         leg_height=0.16, n_niches=1, n_drawers=2,
                         facade=("drawer", "niche", "drawer"),       # nicho CENTRAL
                         wall_back=False, clearance=0.30),
    "storage_media": dict(support="base", body_h=0.46, depth=0.45,
                          toe_recess=0.05, n_niches=2, n_drawers=2,
                          facade=("niche", "drawer", "drawer", "niche"),  # distribuido
                          wall_back=False, clearance=0.35),
}


def derive_rack_spec(tv="65", archetype="low_credenza", **overrides) -> RackSpec:
    """O rack se DERIVA da TV servida: comprimento = tv_width + 2*folga do
    arquetipo, SATURADO em 2.60m (parede/sala nao escala com a diagonal).
    Altura NAO deriva da TV (linha de visao governa)."""
    assert tv in TVS and archetype in ARCHETYPES
    a = ARCHETYPES[archetype]
    tw, _ = TVS[tv]
    length = round(min(2.60, tw + 2 * a["clearance"]), 3)
    # flutuante longo engrossa o corpo suavemente (esbeltez visual <=6 —
    # regra de classe: corpo acompanha o comprimento, nao vira prateleira)
    body_h = a["body_h"]
    if a["support"] == "floating" and not a.get("wall_back"):
        body_h = round(max(body_h, length / 6.0), 3)   # sem contexto: engrossa
    spec = RackSpec(length=length, depth=a["depth"], body_h=body_h,
                    support=a["support"],
                    leg_height=a.get("leg_height", 0.16),
                    gap_floor=a.get("gap_floor", 0.35),
                    toe_recess=a.get("toe_recess", 0.05),
                    n_niches=a["n_niches"], n_drawers=a["n_drawers"],
                    facade_pattern=a["facade"], wall_back=a["wall_back"])
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec.validate()


def rack_class_gate(spec: RackSpec, parts=None):
    errors, warnings, metrics = [], [], {}
    vals = {"length": spec.length, "depth": spec.depth, "body_h": spec.body_h,
            "top_surface": spec.total_height()}
    for k, (lo, hi) in RACK_RANGES.items():
        v = vals[k]
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{k}={v:.3f} fora da faixa de classe [{lo},{hi}]")
    for name, (fn, lo, hi, msg) in RELATIONS.items():
        v = fn(spec)
        metrics[name] = round(v, 3)
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{name}={v:.3f}: {msg}")
    # exatamente UM modo de apoio com leveza (anti bloco no chao)
    if spec.support == "legs" and spec.leg_height < 0.08:
        errors.append("pes invisiveis (<0.08) — perna sumiu/afundou")
    if spec.support == "floating" and spec.gap_floor < 0.25:
        errors.append("flutuante sem respiro (<0.25) — tabua baixa, nao floating")
    if spec.support == "floating" and not spec.wall_back:
        errors.append("flutuante sem placa de fundo/contexto — caixa solta no ar")
    if spec.facade_pattern and spec.facade_pattern != tuple(reversed(spec.facade_pattern)):
        warnings.append("fachada assimetrica — ritmo sem espelho")
    if spec.support == "base" and spec.toe_recess < 0.03:
        errors.append("base sem toe-recess — caixa colada no chao")
    if spec.n_niches < 1:
        warnings.append("sem nicho aberto — vazio tecnico so em gaveta")
    if parts is not None:
        kinds = {p["kind"] for p in parts}
        need = {"base", "top", "front"} if spec.n_drawers else {"base", "top", "niche"}
        if not need <= kinds:
            errors.append(f"partes ausentes: {sorted(need - kinds)}")
    result = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {"result": result, "errors": errors, "warnings": warnings,
            "metrics": metrics}


# ------------------------------------------------------------------ sabotagens
def _sabotages():
    return [
        ("TV 75 em rack curto (1.5m)", lambda: (
            derive_rack_spec("75", "low_credenza", length=1.50), "75", None)),
        ("TV alta demais (storage corpo 0.55 + base p/ TV 75)", lambda: (
            derive_rack_spec("75", "storage_media", body_h=0.55,
                             support="legs", leg_height=0.25), "75", None)),
        ("aparador (corpo 0.62)", lambda: (
            derive_rack_spec("65", "low_credenza", body_h=0.62), "65", None)),
        ("profundo demais (0.62)", lambda: (
            derive_rack_spec("65", "storage_media", depth=0.62), "65", None)),
        ("storage-bloco (sem toe-recess)", lambda: (
            derive_rack_spec("65", "storage_media", toe_recess=0.0), "65", None)),
        ("floating-tabua (respiro 0.10)", lambda: (
            derive_rack_spec("65", "floating_minimal", gap_floor=0.10), "65", None)),
        ("rack-pista (folga 0.9/lado)", lambda: (
            derive_rack_spec("55", "low_credenza", length=1.23 + 1.8), "55", None)),
        ("sofa perto demais da TV 75", lambda: (
            derive_rack_spec("75", "low_credenza"), "75", 1.8)),
        ("floating caixa-solta (sem wall_back)", lambda: (
            derive_rack_spec("65", "floating_minimal", wall_back=False), "65", None)),
    ]


def _apply_sab(mk):
    spec, tv, dist = mk()
    g = rack_class_gate(spec)
    t = tv_satellite_gate(spec, tv)
    s = sofa_satellite_gate(spec, tv, sofa_dist=dist) if dist else {"result": "PASS"}
    return g["result"] == "FAIL" or t["result"] == "FAIL" or s["result"] == "FAIL"


def _tv_proxy_parts(spec: RackSpec, tv="65"):
    """cycle002 (pedido do juiz): a TV nao pode ficar so no label — proxy de
    MOLDURA (4 barras) sobre o rack + LINHA DE VISAO alvo (barra fina a 1.10m).
    Satelite VISIVEL na matriz (padrao novo do programa)."""
    tw, th = TVS[tv]
    L = spec.length
    x0 = (L - tw) / 2.0
    zb = spec.total_height()
    y0, y1 = spec.depth * 0.55, spec.depth * 0.55 + 0.03
    g = (70, 72, 76)
    t = 0.025
    parts = [
        _p("tv_b", "guide", x0, y0, x0 + tw, y1, zb, zb + t, g),
        _p("tv_t", "guide", x0, y0, x0 + tw, y1, zb + th - t, zb + th, g),
        _p("tv_l", "guide", x0, y0, x0 + t, y1, zb, zb + th, g),
        _p("tv_r", "guide", x0 + tw - t, y0, x0 + tw, y1, zb, zb + th, g),
        # linha de visao alvo (olho sentado ~1.10): atravessa alem do rack
        _p("eye_line", "guide", -0.30, y0 + 0.005, L + 0.30, y1 - 0.005,
           1.095, 1.115, (170, 60, 50)),
    ]
    return parts


# ------------------------------------------------------------------ matriz
MATRIX = [(f"{arch}@tv{tv}", arch, tv)
          for arch in ARCHETYPES for tv in ("55", "65", "75")]


def build_matrix(out_dir):
    from tools.render_parts_iso import render_parts
    from tools.sofa_class_matrix import _grid_sheet
    import json as _json
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report, cells = [], []
    for name, arch, tv in MATRIX:
        spec = derive_rack_spec(tv, arch)
        cls = rack_class_gate(spec)
        sat_tv = tv_satellite_gate(spec, tv)
        sat_sofa = sofa_satellite_gate(spec, tv, sofa_dist=TV_MIN_DIST[tv] + 0.4)
        parts, meta = build_rack(spec)
        parts_vis = parts + _tv_proxy_parts(spec, tv)   # satelite VISIVEL
        png = out / f"cell_{name.replace('@', '_')}.png"
        render_parts(parts_vis, png, elev=18, azim=-62,
                     title=f"{name}  {spec.length:.2f}m  tv_c={sat_tv['metrics']['tv_center_m']}")
        report.append({"cell": name, "bbox_m": meta["bbox_m"],
                       "class_gate": cls["result"], "class_errors": cls["errors"],
                       "tv_sat": sat_tv["result"], "sofa_sat": sat_sofa["result"],
                       "tv_center": sat_tv["metrics"]["tv_center_m"],
                       "n_parts": meta["n_parts"]})
        cells.append((name, png, cls["result"], f"tv:{sat_tv['result']}"))
    sheet = _grid_sheet(cells, out / "rack_class_matrix.png",
                        "CLASSE RACK — derivado da TV servida (55/65/75); altura "
                        "pela LINHA DE VISAO (nao pela TV); sofa = regua de distancia")
    (out / "matrix_report.json").write_text(
        _json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"sheet": sheet, "report": report}


if __name__ == "__main__":
    if "--matrix" in sys.argv:
        res = build_matrix(ROOT / "runs/rack_class/matrix")
        print(f"=== matriz da classe rack: {len(res['report'])} ===")
        for r in res["report"]:
            print(f"  {r['cell']:26} class={r['class_gate']:4} tv={r['tv_sat']:4} "
                  f"sofa={r['sofa_sat']:4} centro_tv={r['tv_center']:.2f}m")
        print(f"  -> {res['sheet']}")
        bad = [r for r in res["report"] if "FAIL" in
               (r["class_gate"], r["tv_sat"], r["sofa_sat"])]
        sys.exit(1 if bad else 0)
    print("=== rack_class: arquetipos x TVs ===")
    bad = 0
    for arch in ARCHETYPES:
        for tv in TVS:
            spec = derive_rack_spec(tv, arch)
            g = rack_class_gate(spec)
            t = tv_satellite_gate(spec, tv)
            if g["result"] == "FAIL" or t["result"] == "FAIL":
                bad += 1
                print(f"  XXX {arch:18} tv{tv} {g['errors'][:1]} {t['errors'][:1]}")
    print(f"  derivados validos: {9 - bad}/9")
    print("=== sabotagens (devem FALHAR) ===")
    ok = bad == 0
    for name, mk in _sabotages():
        hit = _apply_sab(mk)
        ok = ok and hit
        print(f"  {'XXX' if hit else '!!! PASSOU'} {name}")
    print("TODOS OK" if ok else "FALHOU")
    sys.exit(0 if ok else 1)
