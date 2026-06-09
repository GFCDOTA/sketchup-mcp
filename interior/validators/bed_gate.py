"""bed_gate.py — GATE de ANATOMIA + VISUAL da CAMA (espelha sofa_gate + furniture_visual_gate).
Regra Felipe: cama NAO pode ser bloco unico. Valida o COMPONENTE (build_bed):
  HARD: nao_bloco_unico (>=4 pecas), pecas_obrigatorias (estrado/colchao/travesseiro/manta),
        materiais_multiplos (>=3 cores: madeira/linho/manta), roupa_nao_cinza (colchao neutro quente).
  SOFT: bevel_macias (colchao/travesseiro/manta com chanfro), >=2 travesseiros, manta no pe.
-> PASS / WARN / FAIL + correcoes. Deterministico, sem SU.

Uso: python interior/validators/bed_gate.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.furniture_anatomy_spec import BED_REQUIRED_PARTS   # noqa: E402


def bed_gate(spec, parts):
    checks, corr = {}, []
    kinds = [p["kind"] for p in parts]
    kset = set(kinds)
    colors = {tuple(p["rgb"]) for p in parts}
    matt = tuple(spec.mattress_rgb)

    checks["nao_bloco_unico"] = len(parts) >= 4
    if not checks["nao_bloco_unico"]:
        corr.append(f"poucas pecas ({len(parts)}) — cama nao pode ser bloco unico")

    missing = [k for k in BED_REQUIRED_PARTS if k not in kset]
    checks["pecas_obrigatorias"] = not missing
    if missing:
        corr.append(f"faltam pecas: {missing}")

    checks["materiais_multiplos"] = len(colors) >= 3
    if not checks["materiais_multiplos"]:
        corr.append(f"poucos materiais ({len(colors)}) — madeira/linho/manta distintos")

    is_gray = max(matt) - min(matt) < 12
    checks["roupa_nao_cinza"] = not is_gray
    if is_gray:
        corr.append("roupa de cama cinza chapada — usar neutro QUENTE (linho)")

    checks["bevel_macias"] = getattr(spec, "bevel", 0.0) > 0
    if not checks["bevel_macias"]:
        corr.append("pecas macias cubicas — aplicar chanfro/inset")

    checks["dois_travesseiros"] = kinds.count("travesseiro") >= 2
    checks["manta_no_pe"] = "manta" in kset

    HARD = ("nao_bloco_unico", "pecas_obrigatorias", "materiais_multiplos", "roupa_nao_cinza")
    SOFT = ("bevel_macias", "dois_travesseiros", "manta_no_pe")
    if not all(checks[k] for k in HARD):
        result = "FAIL"
    elif all(checks[k] for k in SOFT):
        result = "PASS"
    else:
        result = "WARN"
    return {"result": result, "n_parts": len(parts), "n_colors": len(colors),
            "kinds": sorted(kset), "checks": checks, "corrections": corr}


if __name__ == "__main__":
    from tools.bed_builder import build_bed
    from tools.furniture_anatomy_spec import bed_spec
    ok = True
    for sz in ("king", "queen", "casal", "solteiro"):
        s = bed_spec(sz)
        parts, _ = build_bed(s)
        r = bed_gate(s, parts)
        ok = ok and r["result"] == "PASS"
        flag = {"PASS": "OK ", "WARN": "/!\\", "FAIL": "XXX"}[r["result"]]
        print(f"{flag} {sz:10} {r['result']:4} | pecas={r['n_parts']} cores={r['n_colors']}"
              + (f" | corrigir: {r['corrections']}" if r["corrections"] else ""))
    sys.exit(0 if ok else 1)
