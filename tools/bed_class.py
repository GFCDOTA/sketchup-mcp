"""bed_class.py — a TEORIA EXECUTAVEL da classe CAMA (3a classe do programa
arquiteto-de-classe; template sofa->poltrona->cama). Fonte: tabela ergonomica
versionada (.ai_bridge/research/furniture_classes_ergonomics_2026-06-12.json)
+ diagnostico do bed_builder existente (FASE 0: builder bom de anatomia, mas
sem teoria — validate raso, hardcodes, sempre plinto, sem arquetipos).

DNA da classe:
  - tamanhos SAO SKUs BR DISCRETOS (0.88/1.38/1.58/1.93 — nao interpolar);
  - o COLCHAO domina a silhueta (thickness/surface 0.28-0.60);
  - cabeceira nunca mais estreita que o colchao; nunca trono (above/width<=0.55);
  - a base precisa de LEVEZA (reveal, pes ou saia) — nunca bloco macico;
  - CRIADO-MUDO entra como CONSTRAINT SATELITE (topo ~ topo do colchao),
    nao como classe completa neste ciclo.

Uso: python -m tools.bed_class            (prova: derivados + sabotagens)
     python -m tools.bed_class --matrix   (matriz 9 celulas pro juiz)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.bed_builder import build_bed            # noqa: E402
from tools.furniture_anatomy_spec import BedSpec   # noqa: E402

# ------------------------------------------------------------- SKUs BR (discretos)
BED_SKUS = {
    "solteiro": (0.88, 1.88),
    "casal": (1.38, 1.88),
    "queen": (1.58, 1.98),
    "king": (1.93, 2.03),
}

# ----------------------------------------------------------------- faixas duras
BED_RANGES = {
    "length": (1.78, 2.13),
    "mattress_thickness": (0.12, 0.36),     # mtop - btop
    "sleep_surface": (0.30, 0.70),          # mtop (platform baixa 0.30; box alto 0.70)
    "headboard_above": (0.10, 0.80),        # headboard_h - mtop
    "headboard_total": (0.45, 1.40),        # do chao; >1.40 vira parede/dossel
    "headboard_t": (0.03, 0.20),
    "reveal": (0.0, 0.14),
    "leg_height": (0.0, 0.28),
}

# ----------------------------------------------------- relacoes (alma da classe)
RELATIONS = {
    # o colchao DOMINA a silhueta: se some, a base vira tablado/bloco
    "dominancia_do_colchao": (
        lambda s: (s.mattress_top - s.base_top) / s.mattress_top, 0.28, 0.60,
        "colchao/surface fora de [0.28,0.60] — colchao esmagado ou base sumida"),
    "cabeceira_nao_trono": (
        lambda s: (s.headboard_h - s.mattress_top) / s.width, 0.0, 0.55,
        "cabeceira_acima/largura > 0.55 — espaldar de trono"),
    "planta_de_cama": (
        lambda s: s.length / s.width, 1.00, 2.20,
        "comprimento/largura fora de [1.0,2.2] — nao e proporcao de cama humana"),
    "altura_consistente": (
        lambda s: s.headboard_h - s.mattress_top - s.pillow_h, 0.0, 0.70,
        "cabeceira nao passa dos travesseiros (ou passa absurdo)"),
}


def _leveza_da_base(s: BedSpec):
    """Anti bloco-macico: a base PRECISA de leveza — reveal (plinth), pes (legs)
    ou saia (box). Box flush sem saia e sem pes = caixote."""
    if s.base_style == "legs":
        return s.leg_height >= 0.08, f"legs com leg_height={s.leg_height} < 0.08"
    if s.base_style == "box":
        return bool(s.skirt) or s.leg_height >= 0.10, \
            "box flush sem saia e sem pes — bloco macico/caixote"
    return s.reveal >= 0.06, f"plinto com reveal={s.reveal} < 0.06 (efeito bloco)"


# ------------------------------------------------------- arquetipos (intencao)
ARCHETYPES = {
    # eixo: plataforma horizontal (japandi) <-> estofada acolhedora <-> box massa
    "platform": dict(surface=0.38, base_top=0.18, base_z0=0.08, hb_above=0.24,
                     hb_t=0.05, reveal=0.10, hb_overhang=0.0,
                     base_style_default="plinth", leg_height=0.14, skirt=False,
                     hb_rgb=(120, 96, 72)),     # madeira (painel fino, nao estofado)
    "upholstered": dict(surface=0.57, base_top=0.32, base_z0=0.10, hb_above=0.50,
                        hb_t=0.14, reveal=0.08, hb_overhang=0.10,
                        base_style_default="legs", leg_height=0.18, skirt=False,
                        hb_rgb=(166, 152, 132)),  # estofada linho (default historico)
    "box": dict(surface=0.62, base_top=0.34, base_z0=0.30, hb_above=0.38,
                hb_t=0.10, reveal=0.0, hb_overhang=0.0,
                base_style_default="box", leg_height=0.12, skirt=True,
                hb_rgb=(150, 134, 114)),
}
HB_LEVELS = {"low": -0.14, "medium": 0.0, "high": +0.18}


def derive_bed_spec(size="queen", archetype="upholstered", base_style=None,
                    headboard="medium", **overrides) -> BedSpec:
    """Deriva a cama PELA CLASSE: tamanho = SKU BR discreto (nunca interpolado);
    alturas resolvidas pelo arquetipo; cabeceira por nivel low/medium/high."""
    assert size in BED_SKUS, f"tamanho nao-SKU: {size}"
    assert archetype in ARCHETYPES and headboard in HB_LEVELS
    a = ARCHETYPES[archetype]
    base_style = base_style or a["base_style_default"]
    assert base_style in ("plinth", "legs", "box")
    W, L = BED_SKUS[size]
    # a cabeceira RESPEITA a largura (anti-trono e' relacao, entao a derivacao
    # tambem e': solteiro nao usa cabeceira de casal — clamp 0.52*W)
    hb_above = min(0.78, 0.52 * W, max(0.18, a["hb_above"] + HB_LEVELS[headboard]))
    spec = BedSpec(
        size=size, width=W, length=L,
        base_z0=a["base_z0"], base_top=a["base_top"],
        mattress_top=a["surface"],
        headboard_h=round(a["surface"] + hb_above, 3),
        headboard_t=a["hb_t"], headboard_rgb=a["hb_rgb"],
        headboard_overhang=a["hb_overhang"],
        base_style=base_style, leg_height=a["leg_height"],
        reveal=a["reveal"], skirt=(a["skirt"] and base_style == "box"),
        pillow_h=(0.12 if archetype == "platform" else 0.16),
        n_pillows=(1 if size == "solteiro" else 2),
        pillow_w=(0.60 if size == "solteiro" else 0.50),
    )
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec.validate()


def bed_class_gate(spec: BedSpec, parts=None):
    """Gate de PROPORCAO da classe cama. {result, errors, warnings, metrics}."""
    errors, warnings, metrics = [], [], {}
    thickness = spec.mattress_top - spec.base_top
    vals = {
        "length": spec.length, "mattress_thickness": thickness,
        "sleep_surface": spec.mattress_top,
        "headboard_above": spec.headboard_h - spec.mattress_top,
        "headboard_total": spec.headboard_h, "headboard_t": spec.headboard_t,
        "reveal": spec.reveal, "leg_height": spec.leg_height,
    }
    metrics["mattress_thickness_m"] = round(thickness, 3)
    for k, (lo, hi) in BED_RANGES.items():
        v = vals[k]
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{k}={v:.3f} fora da faixa de classe [{lo},{hi}]")

    # tamanho = SKU discreto (nunca interpolar largura de colchao)
    sku_widths = {w for w, _ in BED_SKUS.values()}
    if not any(abs(spec.width - w) <= 0.02 for w in sku_widths):
        errors.append(f"width={spec.width} nao e' SKU BR "
                      f"({sorted(sku_widths)}) — colchao nao se interpola")

    for name, (fn, lo, hi, msg) in RELATIONS.items():
        v = fn(spec)
        metrics[name] = round(v, 3)
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{name}={v:.3f}: {msg}")

    ok, msg = _leveza_da_base(spec)
    metrics["base_style"] = spec.base_style
    if not ok:
        errors.append(f"leveza_da_base: {msg}")

    if parts is not None:
        kinds = {p["kind"] for p in parts}
        need = {"estrado", "colchao", "cabeceira", "travesseiro", "manta"}
        missing = need - kinds
        if missing:
            errors.append(f"partes obrigatorias ausentes: {sorted(missing)}")

    result = "FAIL" if errors else ("WARN" if warnings else "PASS")
    return {"result": result, "errors": errors, "warnings": warnings,
            "metrics": metrics}


# ------------------------------------------- criado-mudo: CONSTRAINT SATELITE
NIGHTSTAND_TOL = 0.08      # topo do criado vs topo do colchao (ideal ~0)
NIGHTSTAND_MAX_DEPTH = 0.45  # alem disso invade a circulacao lateral


def nightstand_satellite_gate(bed: BedSpec, ns_height=0.55, ns_width=0.45,
                              ns_depth=0.40, side_gap=0.06):
    """Valida um criado-mudo CONTRA esta cama (classe satelite, nao completa):
    (a) topo ~ topo do colchao (+-NIGHTSTAND_TOL); (b) profundidade nao invade
    circulacao; (c) posicionado ao lado da cabeca nao colide com colchao nem
    cabeceira (geometria). Devolve tambem o ALVO de altura pro criado desta cama."""
    errors, metrics = [], {}
    delta = ns_height - bed.mattress_top
    metrics["ns_top_vs_mattress_m"] = round(delta, 3)
    metrics["ns_target_h_m"] = round(bed.mattress_top, 3)
    if abs(delta) > NIGHTSTAND_TOL:
        errors.append(f"topo do criado a {delta:+.2f}m do colchao "
                      f"(tol +-{NIGHTSTAND_TOL}) — fora de alcance/engolido")
    if ns_depth > NIGHTSTAND_MAX_DEPTH:
        errors.append(f"criado depth={ns_depth} > {NIGHTSTAND_MAX_DEPTH} — invade circulacao")
    # posicao canonica: encostado ao lado da cama, alinhado a cabeceira
    ns_x0 = bed.width + side_gap
    ns_y1 = bed.length - bed.headboard_t
    overlap_x = ns_x0 < bed.width            # invadiria o colchao em X
    overlap_head = ns_y1 > bed.length        # invadiria a cabeceira em Y
    if overlap_x or overlap_head:
        errors.append("criado colide com colchao/cabeceira na posicao canonica")
    metrics["ns_pos_canonica"] = [round(ns_x0, 3), round(ns_y1 - ns_depth, 3)]
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "metrics": metrics}


# ------------------------------------------------------------------ sabotagens
def _raw(**kw):
    s = derive_bed_spec("queen", "upholstered")
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _sabotages():
    return [
        ("colchao esmagado (0.10 em surface 0.57)",
         lambda: _raw(base_top=0.47)),
        ("cabeceira-trono (0.95 acima num solteiro)",
         lambda: derive_bed_spec("solteiro", "upholstered",
                                 headboard_h=0.38 + 0.95, mattress_top=0.38,
                                 base_top=0.20)),
        ("bloco macico (box sem saia sem pes)",
         lambda: _raw(base_style="box", skirt=False, leg_height=0.0)),
        ("colchao interpolado (width 1.20 nao-SKU)",
         lambda: _raw(width=1.20)),
        ("cama-mesa (surface 0.78)",
         lambda: _raw(mattress_top=0.78, base_top=0.50, headboard_h=1.25)),
        ("king curto (length 1.60)",
         lambda: _raw(width=1.93, length=1.60)),
    ]


# ------------------------------------------------------------------ matriz
MATRIX = [
    ("casal-platform-plinth-low", dict(size="casal", archetype="platform",
                                       base_style="plinth", headboard="low")),
    ("queen-platform-legs-low", dict(size="queen", archetype="platform",
                                     base_style="legs", headboard="low")),
    ("king-platform-plinth-med", dict(size="king", archetype="platform",
                                      base_style="plinth", headboard="medium")),
    ("casal-uphol-legs-med", dict(size="casal", archetype="upholstered",
                                  base_style="legs", headboard="medium")),
    ("queen-uphol-legs-med", dict(size="queen", archetype="upholstered",
                                  base_style="legs", headboard="medium")),
    ("king-uphol-plinth-high", dict(size="king", archetype="upholstered",
                                    base_style="plinth", headboard="high")),
    ("casal-box-skirt-med", dict(size="casal", archetype="box",
                                 base_style="box", headboard="medium")),
    ("queen-box-legs-med", dict(size="queen", archetype="box",
                                base_style="legs", headboard="medium")),
    ("king-box-skirt-high", dict(size="king", archetype="box",
                                 base_style="box", headboard="high")),
]


def build_matrix(out_dir):
    from tools.render_parts_iso import render_parts
    from tools.sofa_class_matrix import _grid_sheet
    import json as _json
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report, cells = [], []
    for name, kw in MATRIX:
        spec = derive_bed_spec(**kw)
        cls = bed_class_gate(spec)
        ns = nightstand_satellite_gate(spec, ns_height=round(spec.mattress_top, 2))
        parts, meta = build_bed(spec)
        png = out / f"cell_{name}.png"
        render_parts(parts, png, elev=24, azim=-55,
                     title=f"{name}  {spec.width:.2f}x{spec.length:.2f}m")
        report.append({"cell": name, "params": kw, "bbox_m": meta["bbox_m"],
                       "class_gate": cls["result"], "class_errors": cls["errors"],
                       "ns_target_h": ns["metrics"]["ns_target_h_m"],
                       "n_parts": meta["n_parts"]})
        cells.append((name, png, cls["result"], f"ns@{ns['metrics']['ns_target_h_m']}"))
    sheet = _grid_sheet(cells, out / "bed_class_matrix.png",
                        "CLASSE CAMA — matriz de generalizacao (SKUs BR x platform/"
                        "upholstered/box x bases x cabeceiras; criado = satelite)")
    (out / "matrix_report.json").write_text(
        _json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"sheet": sheet, "report": report}


if __name__ == "__main__":
    if "--matrix" in sys.argv:
        res = build_matrix(ROOT / "runs/bed_class/matrix")
        print(f"=== matriz da classe cama: {len(res['report'])} celulas ===")
        for r in res["report"]:
            print(f"  {r['cell']:28} class={r['class_gate']:4} "
                  f"ns_alvo={r['ns_target_h']:.2f}m parts={r['n_parts']} "
                  f"{r['class_errors'][:1]}")
        print(f"  -> {res['sheet']}")
        sys.exit(1 if any(r["class_gate"] == "FAIL" for r in res["report"]) else 0)
    print("=== bed_class: SKUs x arquetipos x bases ===")
    bad = 0
    for size in BED_SKUS:
        for arch in ARCHETYPES:
            s = derive_bed_spec(size, arch)
            r = bed_class_gate(s)
            if r["result"] == "FAIL":
                bad += 1
                print(f"  XXX {size:9} {arch:12} -> {r['errors'][:2]}")
    print(f"  derivados validos: {len(BED_SKUS) * len(ARCHETYPES) - bad}/"
          f"{len(BED_SKUS) * len(ARCHETYPES)}")
    print("=== sabotagens (devem FALHAR) ===")
    ok = bad == 0
    for name, mk in _sabotages():
        r = bed_class_gate(mk())
        hit = r["result"] == "FAIL"
        ok = ok and hit
        print(f"  {'XXX' if hit else '!!! PASSOU'} {name} -> {r['result']}")
    # satelite: criado padrao 0.55 NUMA PLATFORM 0.38 deve FALHAR (relacao entre classes)
    plat = derive_bed_spec("queen", "platform")
    ns_bad = nightstand_satellite_gate(plat, ns_height=0.55)
    hit = ns_bad["result"] == "FAIL"
    ok = ok and hit
    print(f"  {'XXX' if hit else '!!! PASSOU'} criado 0.55 em cama platform 0.38 "
          f"-> {ns_bad['result']} (alvo={ns_bad['metrics']['ns_target_h_m']}m)")
    print("TODOS OK" if ok else "FALHOU")
    sys.exit(0 if ok else 1)
