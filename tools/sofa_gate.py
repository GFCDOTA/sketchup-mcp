"""sofa_gate.py — slice 5: GATE de validacao do sofa parametrico. Recebe o spec + as
pecas do SofaBuilder e responde PASS / WARN / FAIL + lista objetiva de correcoes.
Deterministico (Python, sem SU). Criterios (Felipe):
  HARD (qualquer falha -> FAIL):
    - NAO e bloco unico (varias pecas + varios tipos)
    - pecas obrigatorias presentes (base, seat_cushion, back_cushion, arm, foot)
    - orientacao frontal detectavel (encosto ATRAS dos assentos; frente -Y)
    - materiais aplicados (toda peca tem rgb)
  SOFT (falha -> no maximo WARN):
    - bbox bate com o esperado (tol 5 cm)
    - sem peca solta (conjunto conectado)
Uso (cross-check da planta tb): from tools.sofa_gate import gate
"""
from __future__ import annotations

from shapely.geometry import box
from shapely.ops import unary_union

from tools.furniture_anatomy_spec import SOFA_REQUIRED_PARTS


def _all_connected(parts):
    rects = [box(p["x0"], p["y0"], p["x1"], p["y1"]).buffer(0.02) for p in parts]
    return unary_union(rects).geom_type == "Polygon" if rects else False


def gate(spec, parts):
    checks, corr = {}, []
    kinds = {p["kind"] for p in parts}

    checks["nao_bloco_unico"] = len(parts) > 1 and len(kinds) >= 3
    if not checks["nao_bloco_unico"]:
        corr.append("e bloco unico (poucas pecas/tipos) — separar em pecas semanticas")

    missing = [k for k in SOFA_REQUIRED_PARTS if k not in kinds]
    checks["pecas_obrigatorias"] = not missing
    if missing:
        corr.append(f"faltam pecas obrigatorias: {missing}")

    xs = [p["x0"] for p in parts] + [p["x1"] for p in parts]
    ys = [p["y0"] for p in parts] + [p["y1"] for p in parts]
    zs = [p["z0"] for p in parts] + [p["z1"] for p in parts]
    got = (round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3), round(max(zs) - min(zs), 3))
    exp = spec.bbox_m()
    tol = 0.05
    checks["bbox_ok"] = all(abs(got[i] - exp[i]) <= tol for i in range(3))
    if not checks["bbox_ok"]:
        corr.append(f"bbox {got} != esperado {exp} (tol {tol})")

    backs = [p for p in parts if p["kind"] == "back_cushion"]
    seats = [p for p in parts if p["kind"] == "seat_cushion"]
    if backs and seats:
        bcy = sum((p["y0"] + p["y1"]) / 2 for p in backs) / len(backs)
        scy = sum((p["y0"] + p["y1"]) / 2 for p in seats) / len(seats)
        checks["orientacao_frontal"] = bcy > scy   # encosto atras (Y maior); frente = -Y
    else:
        checks["orientacao_frontal"] = False
    if not checks["orientacao_frontal"]:
        corr.append("orientacao nao detectavel: encosto deve ficar ATRAS dos assentos (Y maior)")

    checks["sem_peca_solta"] = _all_connected(parts)
    if not checks["sem_peca_solta"]:
        corr.append("ha peca solta (conjunto desconectado)")

    checks["materiais"] = all(p.get("rgb") and len(p["rgb"]) == 3 for p in parts)
    if not checks["materiais"]:
        corr.append("peca sem material (rgb)")

    HARD = ("nao_bloco_unico", "pecas_obrigatorias", "orientacao_frontal", "materiais")
    SOFT = ("bbox_ok", "sem_peca_solta")
    if not all(checks[k] for k in HARD):
        result = "FAIL"
    elif all(checks[k] for k in SOFT):
        result = "PASS"
    else:
        result = "WARN"
    return {"result": result, "bbox_got": got, "bbox_exp": exp,
            "kinds": sorted(kinds), "n_parts": len(parts),
            "checks": checks, "corrections": corr}


if __name__ == "__main__":
    import json
    from pathlib import Path
    from tools.sofa_builder import build_sofa, sofa_spec
    rows = []
    for v in ("straight", "chaise_right", "chaise_left"):
        s = sofa_spec(v)
        parts, _ = build_sofa(s)
        r = gate(s, parts)
        rows.append({"variant": v, **r})
        flag = {"PASS": "OK ", "WARN": "/!\\", "FAIL": "XXX"}[r["result"]]
        print(f"{flag} {v:13} {r['result']:4} | {r['n_parts']}p {r['kinds']}"
              + (f" | corrigir: {r['corrections']}" if r['corrections'] else ""))
    out = Path("artifacts/review/furniture/sofa/sofa_gate_report.json")
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out}")
