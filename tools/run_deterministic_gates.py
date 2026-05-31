#!/usr/bin/env python3
"""FP-031 — single runnable deterministic gate suite (CI / pre-commit).

Runs the consensus-only detectors always, plus the render wall-presence gate
when a top render + projection sidecar are available, and emits ONE combined
verdict + exit code. No SU build, no PDF, no network — pure + fast.

  - opening_host  : opening<->host-wall consistency (tools/opening_host_audit)
  - wall_overlap  : duplicate/overlapping walls   (tools/wall_overlap_audit)
  - wall_presence : consensus walls present in the SKP top render
                    (tools/overlay_diff, only if --render + <png>.proj.json)

Deterministic only. Visual/fixture judgement is NOT done here (it self-PASSes);
those stay NEEDS-HUMAN.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.opening_host_audit import audit_opening_hosts
from tools.wall_overlap_audit import audit_wall_overlaps

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_consensus(fixture: str | None, consensus_path: str | None) -> dict:
    if consensus_path:
        return json.loads(Path(consensus_path).read_text("utf-8"))
    p = (REPO_ROOT / "fixtures" / fixture
         / "consensus_with_human_walls_and_soft_barriers.json")
    if not p.exists():
        cands = sorted((REPO_ROOT / "fixtures" / fixture).glob("consensus*.json"))
        if not cands:
            raise FileNotFoundError(f"no consensus json for fixture {fixture}")
        p = cands[0]
    return json.loads(p.read_text("utf-8"))


def run_all(
    *,
    fixture: str | None = None,
    consensus_path: str | None = None,
    render_path: str | None = None,
) -> dict:
    con = _load_consensus(fixture, consensus_path)
    gates: dict[str, dict] = {
        "opening_host": audit_opening_hosts(con),
        "wall_overlap": audit_wall_overlaps(con),
    }
    if render_path and (Path(str(render_path) + ".proj.json").exists()):
        from tools.overlay_diff import run_gate
        cp = consensus_path or ""
        if not cp and fixture:
            cp = str(REPO_ROOT / "fixtures" / fixture
                     / "consensus_with_human_walls_and_soft_barriers.json")
        gates["wall_presence"] = run_gate(str(render_path), cp)

    def _ok(g: dict) -> bool:
        return g.get("overall", g.get("verdict")) == "PASS"

    overall = "PASS" if all(_ok(g) for g in gates.values()) else "FAIL"
    return {"overall": overall, "gates": gates}


def _summary_line(name: str, g: dict) -> str:
    v = g.get("overall", g.get("verdict"))
    if name == "opening_host":
        return f"  opening_host : {v} ({g['n_fail']}/{g['n_openings']} openings)"
    if name == "wall_overlap":
        return f"  wall_overlap : {v} ({g['n_overlaps']} overlapping pairs)"
    if name == "wall_presence":
        return (f"  wall_presence: {v} ({len(g['findings'])} flagged, "
                f"calib={g.get('calibration')})")
    return f"  {name}: {v}"


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="deterministic gate suite")
    ap.add_argument("--fixture", default="planta_74")
    ap.add_argument("--consensus", default=None)
    ap.add_argument("--render", default=None,
                    help="SKP top render PNG (needs sibling .proj.json)")
    a = ap.parse_args()
    res = run_all(fixture=a.fixture, consensus_path=a.consensus,
                  render_path=a.render)
    print(f"[deterministic-gates] overall={res['overall']}")
    for name, g in res["gates"].items():
        print(_summary_line(name, g))
    raise SystemExit(0 if res["overall"] == "PASS" else 1)
