"""FP-043/P3: escala absoluta do shell ancorada no consensus, não no próprio report.

Não confundir consistência interna com escala correta: um .skp 0,74x gera
relatório e gates internos coerentes, mas não atende à cota independente.
PASS=0, FAIL=1, INCOMPLETE=3. Um relatório ausente nunca é PASS.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from core.scale import PLANT_PT_TO_M, expected_pt_to_m


def audit(consensus: dict, report: dict, *, consensus_path: Path | None = None,
          tolerance: float = 0.03) -> dict:
    """Confronta bbox físico do PlanShell do SketchUp com wall extents em pt.

    A origem é o consensus (fixture protegida/PDF); a saída é o relatório
    materializado pelo Ruby. Não inferimos a escala esperada do report,
    do env PT_TO_M nem das dimensões já escaladas do modelo.
    """
    if not math.isfinite(tolerance) or not 0 < tolerance <= 0.10:
        raise ValueError("tolerance must be in (0, 0.10]")
    try:
        walls = consensus["walls"]
        if not walls:
            raise ValueError("no walls in consensus")
        ext_x: list[float] = []
        ext_y: list[float] = []
        for wall in walls:
            t = float(wall.get("thickness", consensus.get("wall_thickness_pts")))
            if not math.isfinite(t) or t <= 0:
                raise ValueError("invalid wall thickness")
            for pt in (wall["start"], wall["end"]):
                x, y = float(pt[0]), float(pt[1])
                if not (math.isfinite(x) and math.isfinite(y)):
                    raise ValueError("nonfinite wall endpoint")
                ext_x.extend((x - t / 2, x + t / 2))
                ext_y.extend((y - t / 2, y + t / 2))
        spans_pt = (max(ext_x) - min(ext_x), max(ext_y) - min(ext_y))
        if min(spans_pt) <= 0:
            raise ValueError("degenerate wall bbox")
        target = expected_pt_to_m(
            source=consensus.get("source"), consensus_path=consensus_path
        )
        groups = [g for g in report["groups_diagnostic"]
                  if g.get("name") == "PlanShell_Group"]
        if len(groups) != 1:
            raise ValueError("expected exactly one PlanShell_Group")
        b = groups[0]["bbox_m"]
        observed = tuple(float(b["max"][i]) - float(b["min"][i]) for i in (0, 1))
        if any(not math.isfinite(v) or v <= 0 for v in observed):
            raise ValueError("invalid physical bbox")
        expected = tuple(v * target for v in spans_pt)
        ratio = tuple(observed[i] / expected[i] for i in (0, 1))
        errors = tuple(abs(v - 1) for v in ratio)
        ok = all(e <= tolerance for e in errors)
        source = str(consensus.get("source") or "")
        return {
            "overall": "PASS" if ok else "FAIL",
            "reason": "independent PDF/fixture anchor" if ok else "ABSOLUTE_SCALE_MISMATCH",
            "anchor": "PLANT_COTA" if Path(source).stem in PLANT_PT_TO_M else "SYNTHETIC_DEFAULT",
            "expected_pt_to_m": target,
            "expected_bbox_m": list(expected),
            "observed_bbox_m": list(observed),
            "inferred_pt_to_m_xy": [observed[i] / spans_pt[i] for i in (0, 1)],
            "relative_error_xy": list(errors),
            "tolerance": tolerance,
        }
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
        return {"overall": "INCOMPLETE", "reason": "INVALID_OR_MISSING_GEOMETRY",
                "detail": str(exc)}


def audit_paths(consensus_path: Path, report_path: Path, *,
                tolerance: float = 0.03) -> dict:
    try:
        consensus = json.loads(Path(consensus_path).read_text("utf-8"))
        report = json.loads(Path(report_path).read_text("utf-8"))
    except (OSError, ValueError) as exc:
        return {"overall": "INCOMPLETE", "reason": "INPUT_UNAVAILABLE", "detail": str(exc)}
    return audit(consensus, report, consensus_path=consensus_path, tolerance=tolerance)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="FP-043 independent absolute scale gate")
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--tolerance", type=float, default=0.03)
    args = ap.parse_args(argv)
    result = audit_paths(args.consensus, args.report, tolerance=args.tolerance)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 3}[result["overall"]]


if __name__ == "__main__":
    raise SystemExit(main())
