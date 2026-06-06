"""validation_report.py — agrega os GATES deterministicos de mobiliario + inventario
de ARTIFACTS canonicos num validation_report.json (+ resumo .md). Reusado em cada fase
do plano de interiores (Fase 0 baseline em diante). Sem SU; so logica + checagem de
arquivos. Verdict GREEN se todos os gates PASS e os artifacts obrigatorios existem.

Uso: python -m interior.validators.validation_report [phase_tag]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

CONS = ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
FURN = ROOT / "artifacts/planta_74/furnished"
OUT = ROOT / "artifacts/review/interior"


def _placement():
    from interior.validators.sofa_placement_gate import _fixtures, placement_gate
    con = json.loads(CONS.read_text("utf-8"))
    rows, ok = [], True
    for name, c_in, face, just, expect in _fixtures(con, "r002"):
        r = placement_gate(con, "r002", c_in, face, justification=just)
        hit = r["result"] == expect
        ok = ok and hit
        rows.append({"fixture": name, "expected": expect, "got": r["result"], "ok": hit})
    return {"gate": "SofaPlacementGate", "pass": ok, "fixtures": rows}


def _sofa_anatomy_visual():
    from interior.validators.furniture_visual_gate import visual_gate
    from tools.sofa_builder import build_sofa, sofa_spec
    from tools.sofa_gate import gate as anat
    rows, ok = [], True
    for v in ("straight", "chaise_right", "chaise_left"):
        s = sofa_spec(v)
        parts, _ = build_sofa(s)
        a, vis = anat(s, parts), visual_gate(s, parts)
        p = a["result"] == "PASS" and vis["result"] == "PASS"
        ok = ok and p
        rows.append({"variant": v, "anatomy": a["result"], "visual": vis["result"]})
    return {"gate": "Sofa anatomy+visual", "pass": ok, "variants": rows}


def _bed():
    from interior.validators.bed_gate import bed_gate
    from tools.bed_builder import build_bed
    from tools.furniture_anatomy_spec import bed_spec
    rows, ok = [], True
    for sz in ("king", "queen", "casal", "solteiro"):
        s = bed_spec(sz)
        parts, _ = build_bed(s)
        r = bed_gate(s, parts)
        ok = ok and r["result"] == "PASS"
        rows.append({"size": sz, "result": r["result"], "n_parts": r["n_parts"], "n_colors": r["n_colors"]})
    return {"gate": "BedGate (anatomy+visual)", "pass": ok, "sizes": rows}


def _artifacts():
    items = {
        "planta_74_furnished.skp": FURN / "planta_74_furnished.skp",
        "apartment_after_top.png": FURN / "planta_74_furnished_after_top.png",
        "apartment_after_iso.png": FURN / "planta_74_furnished_after_iso.png",
        "sala_solver_top.png": FURN / "sala_solver_top.png",
        "sofa_arms_iso.png": ROOT / "artifacts/review/furniture/sofa/sofa_arms_iso.png",
        "bed_iso.png": ROOT / "artifacts/review/furniture/bed/bed_iso.png",
    }
    return {k: {"exists": p.exists(), "bytes": (p.stat().st_size if p.exists() else 0)}
            for k, p in items.items()}


def build_report(phase="phase0_baseline"):
    gates = [_placement(), _sofa_anatomy_visual(), _bed()]
    arts = _artifacts()
    all_pass = all(g["pass"] for g in gates)
    arts_ok = all(a["exists"] for a in arts.values())
    rep = {"phase": phase, "gates": gates, "all_gates_pass": all_pass,
           "artifacts": arts, "artifacts_ok": arts_ok,
           "verdict": "GREEN" if (all_pass and arts_ok) else "YELLOW"}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "validation_report.json").write_text(
        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"# validation_report — {phase}", "", f"**VERDICT: {rep['verdict']}**", "",
             "## Gates determinísticos"]
    for g in gates:
        lines.append(f"- {'PASS' if g['pass'] else 'FAIL'} — {g['gate']}")
    lines += ["", "## Artifacts canônicos"]
    for k, a in arts.items():
        lines.append(f"- {'OK' if a['exists'] else 'FALTA'} — {k} ({a['bytes']}b)")
    (OUT / "validation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rep


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "phase0_baseline"
    rep = build_report(phase)
    print(f"=== validation_report ({phase}) -> {rep['verdict']} ===")
    for g in rep["gates"]:
        print(f"  {'PASS' if g['pass'] else 'FAIL':4} {g['gate']}")
    miss = [k for k, a in rep["artifacts"].items() if not a["exists"]]
    print(f"  artifacts_ok={rep['artifacts_ok']}" + (f" (falta: {miss})" if miss else ""))
    print(f"  -> artifacts/review/interior/validation_report.json + .md")
    sys.exit(0 if rep["verdict"] == "GREEN" else 1)
