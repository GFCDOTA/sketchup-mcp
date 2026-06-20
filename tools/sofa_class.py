"""sofa_class.py — a TEORIA EXECUTÁVEL da classe SOFÁ (FASE 1-2 do programa
"arquiteto de classe"). Três pecas:

  CLASS_RANGES / RELATIONS / ANTI_REGRESSION — constraints da classe (fonte:
      interior/class_specs/SOFA_CLASS_SPEC.md; base empirica = 4 ciclos GPT do
      exemplar + tabela ergonomica de referencia)
  derive_spec(seats, archetype, ...) — GERA um SofaSpec por intencao (arquetipo
      formal|standard|lounge + n de lugares + estilo de base), com a LARGURA
      DERIVADA (width = N*per_seat + 2*arm) e todas as relacoes garantidas
  sofa_class_gate(spec, parts=None) — gate de PROPORCAO da classe: valida
      qualquer SofaSpec (derivado ou manual) contra faixas + relacoes +
      anti-regressao. Complementa (nao substitui) sofa_gate/visual_gate.

NAO toca tools/sofa_builder.py nem tools/furniture_anatomy_spec.py (geometria
provada nos cycles 1-4 + worktree sofa-skill ativo nos mesmos arquivos).
Uso: python -m tools.sofa_class   (valida arquetipos x lugares + sabotagens)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.furniture_anatomy_spec import SofaSpec   # noqa: E402

# ----------------------------------------------------------------- faixas duras
# (min, max) por parametro — fora disso e' ERRO de classe, nao estilo.
CLASS_RANGES = {
    "seat_height": (0.38, 0.48),
    "seat_depth": (0.50, 0.68),
    "depth": (0.80, 1.05),
    "height": (0.68, 0.98),
    "arm_width": (0.10, 0.42),
    "backrest_rake": (8.0, 22.0),
    "cushion_thickness": (0.10, 0.24),
    # NOTA de classe: junta REAL = 4-20mm; no low-poly atual o vinco so LE com
    # ~40-50mm (calibrado nos cycles 2-4, gate visual exige >=0.04). Faixa
    # acomoda a leitura provada; DIVIDA: quando houver costura/piping real,
    # apertar pra (0.004, 0.020).
    "cushion_gap": (0.010, 0.050),
    "per_seat": (0.52, 0.75),       # largura util por assento (derivada)
    "seats": (2, 4),
}
# pes: bimodal por estilo de base — o meio-termo e' anti-pattern ("sofa quebrado")
FOOT_EXPOSED = (0.06, 0.22)
FOOT_PLINTH = (0.0, 0.04)

# ----------------------------------------------------- relacoes (coracao da classe)
# nome -> (fn(spec)->valor, lo, hi, mensagem)
RELATIONS = {
    "altura_total_vs_assento": (
        lambda s: s.height / s.seat_height, 1.7, 2.1,
        "height/seat_height fora de [1.7,2.1] — encosto desproporcional ao assento"),
    "suporte_de_costas": (
        lambda s: s.height - s.seat_height, 0.32, 0.55,
        "encosto acima do assento fora de [0.32,0.55]m — sem apoio ou high-back"),
    "braco_na_silhueta": (
        lambda s: (s.arm_height - s.seat_height) / max(s.height - s.seat_height, 1e-9),
        0.30, 0.60,
        "braco vs encosto fora de [0.30,0.60] — braco no topo do encosto = caixa"),
    "bracos_nao_engolem": (
        lambda s: 2 * s.arm_width / s.width, 0.0, 0.35,
        "2*arm_width/width > 0.35 — bracos engolem o assento"),
    "assento_fundo_vs_alto": (
        lambda s: s.seat_depth / s.seat_height, 1.10, 1.55,
        "seat_depth/seat_height fora de [1.10,1.55]"),
    "profundidade_coerente": (
        lambda s: s.depth - (s.seat_depth + s.back_thickness), 0.0, 0.30,
        "seat_depth+back_thickness nao cabe em depth (ou sobra demais)"),
    "almofada_cabe_na_base": (
        lambda s: (s.seat_height - s.foot_height) - s.cushion_thickness, 0.005, 10.0,
        "cushion_thickness nao cabe entre pes e topo do assento"),
    # hard so pega ABERRACAO (poltrona-quadrada / parede-de-aeroporto); o
    # refinamento estetico da silhueta (formal 2.0-2.5, lounge 2.6-3.2) e'
    # julgamento VISUAL do juiz na matriz. Teto 4.8: lounge-4l "low & long"
    # e' intencao legitima (juiz cycle001 aceitou 4.05 como "esticado, ok";
    # cycle003 alargou o lounge de proposito — extremo chunky da 4.56).
    "silhueta_largura_altura": (
        lambda s: s.width / s.height, 1.4, 4.8,
        "width/height fora de [1.4,4.8] — quadrado-poltrona ou parede"),
}

# ------------------------------------------------- anti-regressao (cycles 1-4 GPT)
# nome -> (fn(spec)->bool ok, mensagem). Vale pra DEFAULTS/derivados (WARN se viola).
ANTI_REGRESSION = {
    "rake_minimo": (lambda s: s.backrest_rake >= 8.0,
                    "backrest_rake < 8 — encosto-placa reprovado no cycle 3"),
    "bevel_minimo": (lambda s: s.cushion_bevel >= 0.03,
                     "cushion_bevel < 0.03 — arestas duras reprovadas no cycle 2"),
    "almofada_minima": (lambda s: s.cushion_thickness >= 0.10,
                        "almofada chapada — reprovada nos cycles 1-4"),
    "encosto_acolchoado": (lambda s: s.back_thickness >= 0.16,
                           "back_thickness fino — encosto-placa (cycle 4 fixou 0.20)"),
}

# ------------------------------------------------------- arquetipos (intencao)
# eixo formal <-> lounge; dimensoes ligadas ao corpo NAO escalam com lugares.
# cycle002 (juiz: "arquetipos mudam dimensao mas nao LINGUAGEM"): cada arquetipo
# agora carrega tambem linguagem fisica — formal = braco com tampo proud + pes
# mais altos + chanfro crisp; lounge = almofada projetando sobre a base (sombra
# horizontal) + plinto mais recuado + chanfro macio; standard = neutro.
ARCHETYPES = {
    # cycle003 (juiz: "assinatura ainda timida"): silhuetas afastadas nos eixos —
    # formal MAIS ereto/alto (rake 8, braco alto), lounge MAIS baixo/horizontal
    # (rake 20, braco rente, assento largo). Relacoes conferidas contra RELATIONS.
    "formal": dict(seat_height=0.45, seat_depth=0.52, height=0.92, depth=0.88,
                   backrest_rake=8.0, arm_above_seat=0.26, cushion_thickness=0.13,
                   per_seat=0.56, back_thickness=0.19,
                   arm_cap=True, cushion_bevel=0.03, seat_overhang=0.0,
                   base_recess=0.05, foot_legs=0.14),
    "standard": dict(seat_height=0.43, seat_depth=0.56, height=0.84, depth=0.92,
                     backrest_rake=14.0, arm_above_seat=0.18, cushion_thickness=0.16,
                     per_seat=0.60, back_thickness=0.20,
                     arm_cap=False, cushion_bevel=0.04, seat_overhang=0.0,
                     base_recess=0.06, foot_legs=0.12),
    "lounge": dict(seat_height=0.40, seat_depth=0.62, height=0.72, depth=0.98,
                   backrest_rake=20.0, arm_above_seat=0.12, cushion_thickness=0.20,
                   per_seat=0.68, back_thickness=0.22,
                   arm_cap=False, cushion_bevel=0.05, seat_overhang=0.04,
                   base_recess=0.10, foot_legs=0.10),
}
ARM_STYLES = {"slim": 0.12, "medium": 0.18, "chunky": 0.28}   # m (FIXO entre lugares)
BASE_STYLES = ("legs", "plinth")
PLINTH_FOOT = 0.02
# regra ANTI-BUNKER (cycle002): braco >= este limiar EXIGE compensacao de massa
ARM_MASS_THRESHOLD = 0.22
ARM_RELIEF_STD = 0.05


def derive_spec(seats=3, archetype="standard", arm_style="medium",
                base_style="legs", variant="straight", **overrides) -> SofaSpec:
    """Deriva um SofaSpec PELA CLASSE: largura calculada (nunca chutada),
    alturas relativas resolvidas, arquetipo define o eixo formal<->lounge E a
    LINGUAGEM (arm_cap/overhang/recess/bevel — cycle002). Braco chunky ganha
    compensacao de massa automatica (arm_relief, regra anti-bunker).
    overrides aplicam DEPOIS (e o gate pega se sairem da classe)."""
    assert archetype in ARCHETYPES, f"arquetipo desconhecido: {archetype}"
    assert arm_style in ARM_STYLES and base_style in BASE_STYLES
    a = ARCHETYPES[archetype]
    arm_w = ARM_STYLES[arm_style]
    foot_h = a["foot_legs"] if base_style == "legs" else PLINTH_FOOT
    width = round(seats * a["per_seat"] + 2 * arm_w, 3)
    spec = SofaSpec(
        variant=variant, seats=seats, width=width,
        depth=a["depth"], height=a["height"],
        seat_height=a["seat_height"], seat_depth=a["seat_depth"],
        back_thickness=a["back_thickness"],
        arm_width=arm_w, arm_height=round(a["seat_height"] + a["arm_above_seat"], 3),
        foot_height=foot_h,
        cushion_thickness=a["cushion_thickness"],
        cushion_bevel=a["cushion_bevel"],
        backrest_rake=a["backrest_rake"],
        arm_cap=a["arm_cap"], seat_overhang=a["seat_overhang"],
        base_recess=a["base_recess"],
        arm_relief=(ARM_RELIEF_STD if arm_w >= ARM_MASS_THRESHOLD else 0.0),
        # cycle003: 2a compensacao do chunky — topo do braco afina (taper)
        arm_taper=(0.04 if arm_w >= ARM_MASS_THRESHOLD else 0.0),
    )
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec.validate()


def sofa_class_gate(spec: SofaSpec, parts=None):
    """Valida um SofaSpec contra a CLASSE. Devolve {result, errors, warnings,
    metrics}. ERRO = fora das faixas/relacoes (FAIL); WARNING = anti-regressao
    ou estilo ambiguo (WARN). parts (opcional) confere partes obrigatorias."""
    errors, warnings, metrics = [], [], {}

    per_seat = (spec.width - 2 * spec.arm_width) / max(spec.seats, 1)
    metrics["per_seat_m"] = round(per_seat, 3)
    checks = dict(CLASS_RANGES)
    vals = {
        "seat_height": spec.seat_height, "seat_depth": spec.seat_depth,
        "depth": spec.depth, "height": spec.height, "arm_width": spec.arm_width,
        "backrest_rake": spec.backrest_rake,
        "cushion_thickness": spec.cushion_thickness, "cushion_gap": spec.cushion_gap,
        "per_seat": per_seat, "seats": spec.seats,
    }
    for k, (lo, hi) in checks.items():
        v = vals[k]
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{k}={v:.3f} fora da faixa de classe [{lo},{hi}]")

    # pes: bimodal — dentro de UMA das modas; o vale entre elas e' anti-pattern
    fh = spec.foot_height
    in_exposed = FOOT_EXPOSED[0] - 1e-9 <= fh <= FOOT_EXPOSED[1] + 1e-9
    in_plinth = FOOT_PLINTH[0] - 1e-9 <= fh <= FOOT_PLINTH[1] + 1e-9
    metrics["base_style"] = "legs" if in_exposed else "plinth" if in_plinth else "ambiguo"
    if not (in_exposed or in_plinth):
        errors.append(f"foot_height={fh:.3f} no vale anti-pattern (nem plinto<=0.04 "
                      f"nem pes>=0.06) — 'sofa quebrado'")

    for name, (fn, lo, hi, msg) in RELATIONS.items():
        v = fn(spec)
        metrics[name] = round(v, 3)
        if not (lo - 1e-9 <= v <= hi + 1e-9):
            errors.append(f"{name}={v:.3f}: {msg}")

    # cycle002 — regra ANTI-BUNKER do juiz: braco com massa exige compensacao
    # (sapata recuada). "Hoje chunky + plinth vira bunker."
    if spec.arm_width >= ARM_MASS_THRESHOLD - 1e-9 and spec.arm_relief < 0.04:
        errors.append(f"compensacao_de_massa: arm_width={spec.arm_width:.2f} >= "
                      f"{ARM_MASS_THRESHOLD} sem arm_relief>=0.04 (bunker)")

    for name, (ok_fn, msg) in ANTI_REGRESSION.items():
        if not ok_fn(spec):
            warnings.append(f"{name}: {msg}")

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
def _sabotages():
    """Specs deliberadamente aberrantes que o gate de classe DEVE reprovar
    (todas passam no validate() raso do SofaSpec — e' essa a lacuna que a
    classe fecha)."""
    return [
        ("bracos engolem (0.5 cada em 2.2)", lambda: _raw(arm_width=0.50)),
        ("banco de igreja (rake 2, raso, fino)",
         lambda: _raw(backrest_rake=2.0, seat_depth=0.45, cushion_thickness=0.07)),
        ("cubo gigante (escalou profundidade junto)",
         lambda: _raw(seats=4, width=3.0, depth=1.5, height=1.3)),
        ("pe atarracado (0.05 no vale)", lambda: _raw(foot_height=0.05)),
        ("6 lugares em 1.5m", lambda: _raw(seats=6, width=1.5)),
        ("braco no topo do encosto (caixa)", lambda: _raw(arm_height=0.84)),
        ("bunker (chunky 0.28 sem compensacao)", lambda: _raw(arm_width=0.28)),
    ]


def _raw(**kw):
    s = SofaSpec()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


if __name__ == "__main__":
    print("=== sofa_class: arquetipos x lugares x estilos ===")
    bad = 0
    for arch in ARCHETYPES:
        for seats in (2, 3, 4):
            for arm in ARM_STYLES:
                for base in BASE_STYLES:
                    s = derive_spec(seats, arch, arm, base)
                    r = sofa_class_gate(s)
                    mark = "OK " if r["result"] in ("PASS", "WARN") else "XXX"
                    if r["result"] == "FAIL":
                        bad += 1
                        print(f"  {mark} {arch:8} {seats}l {arm:6} {base:6} "
                              f"W={s.width:.2f} -> {r['result']} {r['errors'][:2]}")
    n = len(ARCHETYPES) * 3 * len(ARM_STYLES) * len(BASE_STYLES)
    print(f"  derivados validos: {n - bad}/{n}")
    print("=== sabotagens (devem FALHAR) ===")
    sab_ok = True
    for name, mk in _sabotages():
        r = sofa_class_gate(mk())
        hit = r["result"] == "FAIL"
        sab_ok = sab_ok and hit
        print(f"  {'XXX' if hit else '!!! PASSOU'} {name} -> {r['result']}")
    ok = (bad == 0) and sab_ok
    print("TODOS OK" if ok else "FALHOU")
    sys.exit(0 if ok else 1)
