"""nightstand_gate.py — GATE de ANATOMIA do CRIADO-MUDO (espelha wardrobe_gate/bed_gate).
Regra Felipe: criado NAO pode ser bloco unico/solto. Valida o COMPONENTE (build_nightstand):
  HARD: nao_bloco_unico (>=4 pecas), pecas_obrigatorias (corpo/tampo/gaveta/pe),
        materiais_multiplos (>=3 cores).
  SOFT: pes (>=3), tampo presente, gaveta presente, knob presente.
-> PASS / WARN / FAIL. Deterministico, sem SU.

Uso: python -m interior.validators.nightstand_gate
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.furniture_anatomy_spec import NIGHTSTAND_REQUIRED_PARTS   # noqa: E402


def nightstand_gate(spec, parts):
    checks, corr = {}, []
    kinds = [p["kind"] for p in parts]
    kset = set(kinds)
    colors = {tuple(p["rgb"]) for p in parts}

    checks["nao_bloco_unico"] = len(parts) >= 4
    if not checks["nao_bloco_unico"]:
        corr.append(f"poucas pecas ({len(parts)})")
    missing = [k for k in NIGHTSTAND_REQUIRED_PARTS if k not in kset]
    checks["pecas_obrigatorias"] = not missing
    if missing:
        corr.append(f"faltam pecas: {missing}")
    checks["materiais_multiplos"] = len(colors) >= 3
    if not checks["materiais_multiplos"]:
        corr.append(f"poucos materiais ({len(colors)})")
    checks["pes"] = kinds.count("pe") >= 3
    checks["tampo"] = "tampo" in kset
    checks["gaveta"] = "gaveta" in kset
    checks["knob"] = "puxador" in kset

    HARD = ("nao_bloco_unico", "pecas_obrigatorias", "materiais_multiplos")
    SOFT = ("pes", "tampo", "gaveta", "knob")
    if not all(checks[k] for k in HARD):
        result = "FAIL"
    elif all(checks[k] for k in SOFT):
        result = "PASS"
    else:
        result = "WARN"
    return {"result": result, "n_parts": len(parts), "n_colors": len(colors),
            "kinds": sorted(kset), "checks": checks, "corrections": corr}


if __name__ == "__main__":
    from tools.furniture_anatomy_spec import nightstand_spec
    from tools.nightstand_builder import build_nightstand
    s = nightstand_spec()
    parts, _ = build_nightstand(s)
    r = nightstand_gate(s, parts)
    flag = {"PASS": "OK ", "WARN": "/!\\", "FAIL": "XXX"}[r["result"]]
    print(f"{flag} criado {r['result']} | pecas={r['n_parts']} cores={r['n_colors']} kinds={r['kinds']}"
          + (f" | corrigir: {r['corrections']}" if r["corrections"] else ""))
    sys.exit(0 if r["result"] == "PASS" else 1)
