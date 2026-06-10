"""furniture_visual_gate.py — GATE VISUAL do mobiliario (Visual Furniture Quality Layer,
prioridade do GPT). Alem do sofa_gate (anatomia), valida o ACABAMENTO: "nao parece
caixa/game asset bruto". Deterministico, sem SU. Criterios (do veredito do GPT):
  HARD: materiais distintos (tecido != base != pes), tecido NAO-cinza (neutro quente),
        almofadas com bevel (menos cubicas).
  SOFT: vinco/costura visivel, variacao de altura base<assento<encosto, pes com contraste.
-> PASS / WARN / FAIL + correcoes.

Uso: python interior/validators/furniture_visual_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def visual_gate(spec, parts):
    checks, corr = {}, []
    colors = {tuple(p["rgb"]) for p in parts}
    fab = tuple(spec.fabric_rgb)
    feet = tuple(spec.feet_rgb)

    checks["materiais_multiplos"] = len(colors) >= 3      # tecido + base/estrutura + pes
    if not checks["materiais_multiplos"]:
        corr.append(f"poucos materiais ({len(colors)}) — diferenciar tecido/base/pes")

    is_gray = max(fab) - min(fab) < 12                    # cinza: R~G~B
    checks["tecido_nao_cinza"] = not is_gray
    if is_gray:
        corr.append("tecido cinza chapado — usar neutro QUENTE (linho/bege)")

    checks["almofadas_beveled"] = getattr(spec, "cushion_bevel", 0.0) > 0
    if not checks["almofadas_beveled"]:
        corr.append("almofadas cubicas — aplicar chanfro/topo inset")

    checks["vinco_visivel"] = spec.cushion_gap >= 0.04
    if not checks["vinco_visivel"]:
        corr.append("vinco raso — aumentar gap entre almofadas")

    checks["variacao_altura"] = spec.foot_height < spec.seat_height < spec.height
    checks["pes_contraste"] = sum(feet) < sum(fab) - 90
    if not checks["pes_contraste"]:
        corr.append("pes sem contraste com o tecido")

    HARD = ("materiais_multiplos", "tecido_nao_cinza", "almofadas_beveled")
    SOFT = ("vinco_visivel", "variacao_altura", "pes_contraste")
    if not all(checks[k] for k in HARD):
        result = "FAIL"
    elif all(checks[k] for k in SOFT):
        result = "PASS"
    else:
        result = "WARN"
    return {"result": result, "n_colors": len(colors), "fabric_rgb": list(fab),
            "checks": checks, "corrections": corr}


if __name__ == "__main__":
    from tools.sofa_builder import build_sofa, sofa_spec
    for v in ("straight", "chaise_right", "chaise_left"):
        s = sofa_spec(v)
        parts, _ = build_sofa(s)
        r = visual_gate(s, parts)
        flag = {"PASS": "OK ", "WARN": "/!\\", "FAIL": "XXX"}[r["result"]]
        print(f"{flag} {v:13} {r['result']:4} | cores={r['n_colors']} tecido={r['fabric_rgb']}"
              + (f" | corrigir: {r['corrections']}" if r["corrections"] else ""))
