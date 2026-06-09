"""wardrobe_gate.py — GATE de ANATOMIA do GUARDA-ROUPA (espelha bed_gate/sofa_gate).
Regra Felipe: guarda-roupa NAO pode ser bloco unico/caixa lisa. Valida o COMPONENTE
(build_wardrobe):
  HARD: nao_bloco_unico (>=4 pecas), pecas_obrigatorias (corpo/porta/puxador/rodape),
        materiais_multiplos (>=3 cores), tem_portas (>=2 portas).
  SOFT: puxadores (>=1 por porta), frestas (gap>0 -> divisoes visiveis), rodape presente.
-> PASS / WARN / FAIL + correcoes. Deterministico, sem SU.

Uso: python -m interior.validators.wardrobe_gate
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.furniture_anatomy_spec import WARDROBE_REQUIRED_PARTS   # noqa: E402


def wardrobe_gate(spec, parts):
    checks, corr = {}, []
    kinds = [p["kind"] for p in parts]
    kset = set(kinds)
    colors = {tuple(p["rgb"]) for p in parts}

    checks["nao_bloco_unico"] = len(parts) >= 4
    if not checks["nao_bloco_unico"]:
        corr.append(f"poucas pecas ({len(parts)}) — guarda-roupa nao pode ser bloco unico")

    missing = [k for k in WARDROBE_REQUIRED_PARTS if k not in kset]
    checks["pecas_obrigatorias"] = not missing
    if missing:
        corr.append(f"faltam pecas: {missing}")

    checks["materiais_multiplos"] = len(colors) >= 3
    if not checks["materiais_multiplos"]:
        corr.append(f"poucos materiais ({len(colors)}) — corpo/porta/puxador/rodape distintos")

    n_doors = kinds.count("porta")
    checks["tem_portas"] = n_doors >= 2
    if not checks["tem_portas"]:
        corr.append(f"poucas portas ({n_doors})")

    checks["puxadores"] = kinds.count("puxador") >= max(1, n_doors)
    checks["frestas"] = getattr(spec, "door_gap", 0.0) > 0
    if not checks["frestas"]:
        corr.append("portas sem fresta — adicionar divisao vertical")
    checks["rodape"] = "rodape" in kset

    HARD = ("nao_bloco_unico", "pecas_obrigatorias", "materiais_multiplos", "tem_portas")
    SOFT = ("puxadores", "frestas", "rodape")
    if not all(checks[k] for k in HARD):
        result = "FAIL"
    elif all(checks[k] for k in SOFT):
        result = "PASS"
    else:
        result = "WARN"
    return {"result": result, "n_parts": len(parts), "n_doors": n_doors, "n_colors": len(colors),
            "kinds": sorted(kset), "checks": checks, "corrections": corr}


if __name__ == "__main__":
    from tools.wardrobe_builder import build_wardrobe
    from tools.furniture_anatomy_spec import wardrobe_spec
    ok = True
    for w in (1.2, 1.8, 2.4):
        s = wardrobe_spec(width=w)
        parts, _ = build_wardrobe(s)
        r = wardrobe_gate(s, parts)
        ok = ok and r["result"] == "PASS"
        flag = {"PASS": "OK ", "WARN": "/!\\", "FAIL": "XXX"}[r["result"]]
        print(f"{flag} W={w} {r['result']:4} | pecas={r['n_parts']} portas={r['n_doors']} cores={r['n_colors']}"
              + (f" | corrigir: {r['corrections']}" if r["corrections"] else ""))
    sys.exit(0 if ok else 1)
