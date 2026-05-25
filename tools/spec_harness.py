"""SDD harness — evaluate spec YAMLs against pipeline artefacts.

See ``docs/engineering/spec_driven_development.md`` for the framework,
``docs/engineering/harness_engineering.md`` for the rule-type
reference. This file is the executable side of the contract.

The harness is fixture-driven: every input is an explicit CLI
argument, so the same code runs from CI, from a pytest test, and from
an operator's terminal.

Exit code contract:

  0  every ``critical`` contract passed (warns may have surfaced but
     they don't break the build)
  1  at least one ``critical`` contract FAILED or ERRORED, OR a spec
     file is malformed / references an unknown rule type
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

PT_TO_M = 0.19 / 5.4
PT_TO_M2 = PT_TO_M ** 2


# ---- data types -----------------------------------------------------


@dataclass
class RuleResult:
    """Outcome of one rule evaluation."""

    verdict: str  # pass | warn | fail | skip | error
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class HarnessContext:
    """Bundle of inputs available to rule evaluators. Each rule
    declares which inputs it needs by checking ``ctx.consensus`` etc.;
    if the rule needs a missing input it returns a ``skip`` result."""

    consensus: dict[str, Any] | None
    fidelity_report: dict[str, Any] | None
    invariants_report: dict[str, Any] | None
    evidence_dir: Path | None

    def consensus_or_skip(self) -> dict[str, Any] | RuleResult:
        if self.consensus is None:
            return RuleResult("skip", "consensus JSON not provided")
        return self.consensus

    def invariants_or_skip(self) -> dict[str, Any] | RuleResult:
        if self.invariants_report is None:
            return RuleResult("skip", "invariants report not provided")
        return self.invariants_report

    def fidelity_or_skip(self) -> dict[str, Any] | RuleResult:
        if self.fidelity_report is None:
            return RuleResult("skip", "fidelity report not provided")
        return self.fidelity_report

    def evidence_dir_or_skip(self) -> Path | RuleResult:
        if self.evidence_dir is None:
            return RuleResult("skip", "--evidence-dir not provided")
        return self.evidence_dir


# ---- rule evaluators ------------------------------------------------


def _rule_no_merged_room_names(rule: dict, ctx: HarnessContext) -> RuleResult:
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    forbidden = list(rule.get("forbidden_substrings") or [])
    names = [r.get("name") or "" for r in consensus.get("rooms", [])]
    hits = []
    matched_substrings: list[str] = []
    for name in names:
        for sub in forbidden:
            if sub in name:
                hits.append(name)
                if sub not in matched_substrings:
                    matched_substrings.append(sub)
                break
    if not hits:
        return RuleResult(
            "pass",
            f"no room name contains any of {forbidden!r}",
            {"checked_names": names, "forbidden_substrings": forbidden},
        )
    return RuleResult(
        "fail",
        f"{len(hits)} merged room name(s) violate forbidden_substrings",
        {
            "matched_rooms": hits,
            "forbidden_substrings_hit": matched_substrings,
            "checked_names": names,
        },
    )


def _rule_expected_room_names(rule: dict, ctx: HarnessContext) -> RuleResult:
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    required = list(rule.get("required") or [])
    names = [r.get("name") or "" for r in consensus.get("rooms", [])]
    # A room may carry a merged name like "A.S. | TERRACO SOCIAL";
    # treat its sub-tokens as present individually so a partial fix
    # that still ships the merged name doesn't satisfy this contract
    # (the no_merged_room_names rule catches that case separately).
    flat_tokens: set[str] = set()
    for n in names:
        for tok in n.split(" | "):
            flat_tokens.add(tok.strip())
    missing = [r for r in required if r not in flat_tokens]
    if not missing:
        return RuleResult(
            "pass",
            f"all {len(required)} required room names present",
            {"required": required, "observed_names": names},
        )
    return RuleResult(
        "fail",
        f"missing required room(s): {missing!r}",
        {"required": required, "missing": missing, "observed_names": names},
    )


def _rule_room_area_range(rule: dict, ctx: HarnessContext) -> RuleResult:
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    ranges = list(rule.get("ranges") or [])
    by_name = {r.get("name"): r for r in consensus.get("rooms", [])}
    out_of_range: list[dict] = []
    checked: list[dict] = []
    for entry in ranges:
        name = entry["name"]
        room = by_name.get(name)
        if room is None:
            # Skip individual missing rooms — the expected_room_names
            # contract owns the "must exist" assertion.
            continue
        area_m2 = (room.get("area_pts2") or 0.0) * PT_TO_M2
        ok = entry["min_m2"] <= area_m2 <= entry["max_m2"]
        checked.append({"name": name, "area_m2": round(area_m2, 3),
                         "min_m2": entry["min_m2"], "max_m2": entry["max_m2"]})
        if not ok:
            out_of_range.append({
                "name": name,
                "area_m2": round(area_m2, 3),
                "min_m2": entry["min_m2"],
                "max_m2": entry["max_m2"],
            })
    if not out_of_range:
        return RuleResult(
            "pass",
            f"all {len(checked)} measured rooms within range",
            {"checked": checked},
        )
    return RuleResult(
        "fail",
        f"{len(out_of_range)} room(s) outside their declared area range",
        {"out_of_range": out_of_range, "checked": checked},
    )


def _rule_soft_barriers_protected_count(rule: dict, ctx: HarnessContext) -> RuleResult:
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    keywords = [k.lower() for k in (rule.get("semantic_keywords") or [])]
    min_count = int(rule.get("min", 1))

    def is_semantic(sb: dict) -> bool:
        origin = (sb.get("geometry_origin") or "").strip().lower()
        if origin == "human_annotation":
            return True
        btype = (sb.get("barrier_type") or "").strip().lower()
        if btype and any(kw in btype for kw in keywords):
            return True
        blob = " ".join(str(sb.get(k, "")) for k in
                         ("id", "name", "label", "annotation")).lower()
        return any(kw in blob for kw in keywords)

    sbs = consensus.get("soft_barriers", [])
    semantic = [sb for sb in sbs if is_semantic(sb)]
    if len(semantic) >= min_count:
        return RuleResult(
            "pass",
            f"{len(semantic)} semantic SB(s) ≥ min={min_count}",
            {"semantic_count": len(semantic),
             "semantic_ids": [sb.get("id") for sb in semantic],
             "total_sbs": len(sbs)},
        )
    return RuleResult(
        "fail",
        f"only {len(semantic)} semantic SB(s); min required {min_count}",
        {"semantic_count": len(semantic),
         "semantic_ids": [sb.get("id") for sb in semantic],
         "total_sbs": len(sbs)},
    )


def _rule_door_leaf_proximity(rule: dict, ctx: HarnessContext) -> RuleResult:
    invariants = ctx.invariants_or_skip()
    if isinstance(invariants, RuleResult):
        return invariants
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    max_d = float(rule.get("max_distance_m", 1.0))

    # Index openings by id for fast lookup.
    op_centers: dict[str, tuple[float, float]] = {}
    for op in consensus.get("openings", []):
        oid = op.get("id")
        center = op.get("center")
        if not (oid and center and len(center) >= 2):
            continue
        op_centers[oid] = (center[0] * PT_TO_M, center[1] * PT_TO_M)

    failures: list[dict] = []
    checked: list[dict] = []
    groups = invariants.get("groups") or []
    for grp in groups:
        name = grp.get("name") or ""
        if not name.startswith("DoorLeaf_Group_"):
            continue
        oid = name[len("DoorLeaf_Group_"):]
        host_center = op_centers.get(oid)
        if host_center is None:
            continue  # leaf without a known host opening — invariants
                      # owns that detection, not the proximity rule
        bbox = grp.get("bbox_m") or {}
        bmin = bbox.get("min") or [0, 0, 0]
        bmax = bbox.get("max") or [0, 0, 0]
        cx = (bmin[0] + bmax[0]) / 2.0
        cy = (bmin[1] + bmax[1]) / 2.0
        dx = cx - host_center[0]
        dy = cy - host_center[1]
        d = (dx * dx + dy * dy) ** 0.5
        checked.append({"leaf": name, "opening_id": oid,
                         "leaf_center_m": [round(cx, 3), round(cy, 3)],
                         "opening_center_m": [round(host_center[0], 3),
                                              round(host_center[1], 3)],
                         "distance_m": round(d, 3)})
        if d > max_d:
            failures.append(checked[-1])
    if not failures:
        return RuleResult(
            "pass",
            f"all {len(checked)} door leaves within {max_d} m of host",
            {"checked": checked},
        )
    return RuleResult(
        "fail",
        f"{len(failures)} door leaf/leaves exceed {max_d} m proximity",
        {"failures": failures, "checked": checked},
    )


def _rule_room_has_door(rule: dict, ctx: HarnessContext) -> RuleResult:
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    required_rooms = list(rule.get("rooms_requiring_door") or [])
    rooms = consensus.get("rooms", [])
    openings = consensus.get("openings", [])

    # Heuristic: a door belongs to a room if (a) opening.adjacent_rooms
    # references the room, OR (b) the opening center lies inside the
    # room's polygon buffered by 1.5× wall thickness. (b) is the
    # fallback when consensus doesn't carry adjacency data.
    from shapely.geometry import Point, Polygon
    t = consensus.get("wall_thickness_pts", 5.4) or 5.4

    room_by_name: dict[str, dict] = {}
    for r in rooms:
        names = (r.get("name") or "").split(" | ")
        for n in names:
            room_by_name[n.strip()] = r

    missing: list[str] = []
    found: list[dict] = []
    for name in required_rooms:
        room = room_by_name.get(name)
        if room is None:
            missing.append(name)  # absent room can't have a door
            continue
        rid = room.get("id")
        has_door = False
        poly_pts = room.get("polygon_pts") or []
        if len(poly_pts) >= 3:
            try:
                poly = Polygon([(p[0], p[1]) for p in poly_pts])
                hull = poly.buffer(t * 1.5)
            except Exception:
                hull = None
        else:
            hull = None
        for op in openings:
            adj = op.get("adjacent_rooms") or []
            if rid in adj or name in adj:
                has_door = True
                break
            if hull is not None:
                center = op.get("center")
                if center and len(center) >= 2:
                    if hull.contains(Point(center[0], center[1])):
                        has_door = True
                        break
        if has_door:
            found.append({"room": name, "id": rid})
        else:
            missing.append(name)
    if not missing:
        return RuleResult(
            "pass",
            f"all {len(found)} required rooms have ≥1 door/opening",
            {"found": found},
        )
    return RuleResult(
        "fail",
        f"{len(missing)} required room(s) have no door/opening",
        {"missing": missing, "found": found},
    )


def _rule_evidence_pack_present(rule: dict, ctx: HarnessContext) -> RuleResult:
    edir = ctx.evidence_dir_or_skip()
    if isinstance(edir, RuleResult):
        return edir
    required = list(rule.get("required_artifacts") or [])
    missing: list[str] = []
    present: list[str] = []
    for name in required:
        p = edir / name
        if p.exists() and p.is_file() and p.stat().st_size > 0:
            present.append(name)
        else:
            missing.append(name)
    if not missing:
        return RuleResult(
            "pass",
            f"all {len(required)} evidence artifacts present",
            {"present": present, "evidence_dir": str(edir)},
        )
    return RuleResult(
        "fail",
        f"{len(missing)} evidence artifact(s) missing or zero-bytes",
        {"missing": missing, "present": present,
         "evidence_dir": str(edir)},
    )


def _rule_fidelity_axis_pass(rule: dict, ctx: HarnessContext) -> RuleResult:
    fidelity = ctx.fidelity_or_skip()
    if isinstance(fidelity, RuleResult):
        return fidelity
    axes = list(rule.get("axes") or [])
    min_score = float(rule.get("min_score", 0.0))
    per_axis = (fidelity.get("per_axis") or
                fidelity.get("axes") or {})
    failures: list[dict] = []
    checked: list[dict] = []
    for axis in axes:
        info = per_axis.get(axis)
        if info is None:
            continue  # missing axis is silent skip (forward-compat)
        score = float(info.get("score", 0.0))
        verdict = (info.get("verdict") or "").upper()
        checked.append({"axis": axis, "score": score, "verdict": verdict})
        if score < min_score or verdict == "FAIL":
            failures.append(checked[-1])
    if not checked:
        return RuleResult("skip", "no requested axes present in fidelity report")
    if not failures:
        return RuleResult(
            "pass",
            f"all {len(checked)} axes meet min_score={min_score}",
            {"checked": checked, "min_score": min_score},
        )
    return RuleResult(
        "fail",
        f"{len(failures)} axes below min_score or FAIL",
        {"failures": failures, "checked": checked, "min_score": min_score},
    )


def _rule_invariants_verdict_pass(rule: dict, ctx: HarnessContext) -> RuleResult:
    invariants = ctx.invariants_or_skip()
    if isinstance(invariants, RuleResult):
        return invariants
    verdict = ((invariants.get("summary") or {}).get("verdict") or "").upper()
    counts = invariants.get("summary") or {}
    if verdict == "PASS":
        return RuleResult(
            "pass", f"invariants verdict=PASS ({counts})",
            {"summary": counts},
        )
    return RuleResult(
        "fail", f"invariants verdict={verdict!r} != PASS",
        {"summary": counts},
    )


def _rule_openings_min_kind_count(rule: dict, ctx: HarnessContext) -> RuleResult:
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    kind = rule.get("kind")
    min_count = int(rule.get("min_count", 1))
    openings = consensus.get("openings", [])
    matches = [op for op in openings
               if (op.get("kind_v5") or op.get("kind")) == kind]
    if len(matches) >= min_count:
        return RuleResult(
            "pass",
            f"{len(matches)} opening(s) of kind={kind!r} ≥ min={min_count}",
            {"kind": kind, "count": len(matches),
             "ids": [op.get("id") for op in matches]},
        )
    return RuleResult(
        "fail",
        f"only {len(matches)} opening(s) of kind={kind!r}; min={min_count}",
        {"kind": kind, "count": len(matches),
         "ids": [op.get("id") for op in matches]},
    )


def _rule_openings_count_range(rule: dict, ctx: HarnessContext) -> RuleResult:
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    mn = int(rule.get("min", 0))
    mx = int(rule.get("max", 999))
    n = len(consensus.get("openings", []))
    if mn <= n <= mx:
        return RuleResult(
            "pass", f"openings count {n} in [{mn}, {mx}]",
            {"count": n, "min": mn, "max": mx},
        )
    return RuleResult(
        "fail", f"openings count {n} outside [{mn}, {mx}]",
        {"count": n, "min": mn, "max": mx},
    )


def _rule_soft_barriers_count_range(rule: dict, ctx: HarnessContext) -> RuleResult:
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    mn = int(rule.get("min", 0))
    mx = int(rule.get("max", 999))
    n = len(consensus.get("soft_barriers", []))
    if mn <= n <= mx:
        return RuleResult(
            "pass", f"soft_barriers count {n} in [{mn}, {mx}]",
            {"count": n, "min": mn, "max": mx},
        )
    return RuleResult(
        "fail", f"soft_barriers count {n} outside [{mn}, {mx}]",
        {"count": n, "min": mn, "max": mx},
    )


def _rule_soft_barriers_wall_coincident_count(rule: dict, ctx: HarnessContext) -> RuleResult:
    """Counts SBs whose overlap_fraction_with_walls (from the audit
    report) exceeds the threshold; fails if too many."""
    consensus = ctx.consensus_or_skip()
    if isinstance(consensus, RuleResult):
        return consensus
    max_overlap = float(rule.get("max_overlap_fraction", 0.5))
    max_count = int(rule.get("max_count", 0))
    # Re-derive overlap via simple 3-point sample (mirrors FP-006).
    walls = consensus.get("walls", [])
    t = consensus.get("wall_thickness_pts", 5.4) or 5.4
    half = t / 2.0
    wall_rects: list[tuple[float, float, float, float]] = []
    for w in walls:
        s = w.get("start")
        e = w.get("end")
        if not s or not e:
            continue
        ori = w.get("orientation")
        if ori == "h":
            x0, x1 = sorted([s[0], e[0]])
            cy = s[1]
            wall_rects.append((x0 - 1.0, cy - half - 1.0,
                                x1 + 1.0, cy + half + 1.0))
        elif ori == "v":
            cx = s[0]
            y0, y1 = sorted([s[1], e[1]])
            wall_rects.append((cx - half - 1.0, y0 - 1.0,
                                cx + half + 1.0, y1 + 1.0))

    def _overlap_frac(sb: dict) -> float:
        pts = sb.get("polyline_pts") or []
        total = 0.0
        inside = 0.0
        for i in range(len(pts) - 1):
            ax, ay = pts[i]
            bx, by = pts[i + 1]
            seg_len = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
            total += seg_len
            mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
            for x0, y0, x1, y1 in wall_rects:
                if x0 <= mx <= x1 and y0 <= my <= y1:
                    inside += seg_len
                    break
        return inside / total if total > 0 else 0.0

    sbs = consensus.get("soft_barriers", [])
    coincident_ids = [sb.get("id") for sb in sbs
                      if _overlap_frac(sb) > max_overlap]
    n = len(coincident_ids)
    if n <= max_count:
        return RuleResult(
            "pass",
            f"{n} wall-coincident SB(s) ≤ max={max_count}",
            {"count": n, "ids": coincident_ids, "max_count": max_count},
        )
    return RuleResult(
        "fail",
        f"{n} wall-coincident SB(s) exceed max={max_count}",
        {"count": n, "ids": coincident_ids, "max_count": max_count},
    )


def _rule_soft_barrier_height_band(rule: dict, ctx: HarnessContext) -> RuleResult:
    invariants = ctx.invariants_or_skip()
    if isinstance(invariants, RuleResult):
        return invariants
    max_h = float(rule.get("max_height_m", 2.0))
    failures: list[dict] = []
    checked: list[dict] = []
    for grp in invariants.get("groups") or []:
        if (grp.get("semantic_type") or "") != "soft_barrier":
            continue
        h = float(grp.get("height_m") or 0.0)
        checked.append({"name": grp.get("name"), "height_m": h})
        if h > max_h:
            failures.append(checked[-1])
    if not failures:
        return RuleResult(
            "pass",
            f"all {len(checked)} SB groups within height band",
            {"checked": checked, "max_height_m": max_h},
        )
    return RuleResult(
        "fail",
        f"{len(failures)} SB group(s) exceed max_height_m={max_h}",
        {"failures": failures, "checked": checked},
    )


def _rule_fidelity_axes_observe(rule: dict, ctx: HarnessContext) -> RuleResult:
    fidelity = ctx.fidelity_or_skip()
    if isinstance(fidelity, RuleResult):
        return fidelity
    per_axis = (fidelity.get("per_axis") or fidelity.get("axes") or {})
    snapshot = {axis: {
        "score": info.get("score"),
        "verdict": info.get("verdict"),
    } for axis, info in per_axis.items()}
    return RuleResult(
        "pass",
        f"observed {len(snapshot)} fidelity axes",
        {"axes": snapshot},
    )


_RULE_DISPATCHERS: dict[str, Callable[[dict, HarnessContext], RuleResult]] = {
    "no_merged_room_names":              _rule_no_merged_room_names,
    "expected_room_names":               _rule_expected_room_names,
    "room_area_range":                   _rule_room_area_range,
    "soft_barriers_protected_count":     _rule_soft_barriers_protected_count,
    "soft_barriers_count_range":         _rule_soft_barriers_count_range,
    "soft_barriers_wall_coincident_count": _rule_soft_barriers_wall_coincident_count,
    "soft_barrier_height_band":          _rule_soft_barrier_height_band,
    "door_leaf_proximity":               _rule_door_leaf_proximity,
    "room_has_door":                     _rule_room_has_door,
    "evidence_pack_present":             _rule_evidence_pack_present,
    "fidelity_axis_pass":                _rule_fidelity_axis_pass,
    "fidelity_axes_observe":             _rule_fidelity_axes_observe,
    "invariants_verdict_pass":           _rule_invariants_verdict_pass,
    "openings_min_kind_count":           _rule_openings_min_kind_count,
    "openings_count_range":              _rule_openings_count_range,
}


# ---- evaluation entry points ----------------------------------------


def _evaluate_rule(rule: dict, ctx: HarnessContext) -> RuleResult:
    rule_type = rule.get("type")
    dispatcher = _RULE_DISPATCHERS.get(rule_type)
    if dispatcher is None:
        return RuleResult(
            "error",
            f"unknown rule type {rule_type!r}; supported: "
            f"{sorted(_RULE_DISPATCHERS)}",
            {"rule_type": rule_type},
        )
    try:
        return dispatcher(rule, ctx)
    except Exception as e:  # noqa: BLE001
        return RuleResult(
            "error",
            f"{type(e).__name__}: {e}",
            {"rule_type": rule_type, "exception_class": type(e).__name__},
        )


def load_spec(path: Path) -> dict:
    """Load a single spec YAML and return its parsed dict.

    Raises ``ValueError`` if the YAML is malformed or the document is
    missing the required top-level keys. The caller is responsible for
    catching and turning that into a per-spec error report.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error in {path}: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(
            f"spec {path} root must be a mapping, got {type(data).__name__}"
        )
    if "contracts" not in data or not isinstance(data["contracts"], list):
        raise ValueError(
            f"spec {path} must declare a list under 'contracts'"
        )
    return data


def evaluate_specs(spec_paths: list[Path], ctx: HarnessContext,
                   ) -> tuple[list[dict], dict]:
    """Evaluate every contract in every spec; return (contracts_report,
    summary). The summary mirrors the JSON output's summary block.
    """
    contracts_out: list[dict] = []
    pass_n = warn_n = fail_n = skip_n = err_n = critical_fail_n = 0
    for sp in spec_paths:
        try:
            data = load_spec(sp)
        except ValueError as e:
            contracts_out.append({
                "spec_path": str(sp),
                "id": None,
                "severity": "critical",
                "rule_type": None,
                "verdict": "error",
                "evidence": {},
                "message": str(e),
            })
            err_n += 1
            critical_fail_n += 1
            continue
        for contract in data["contracts"]:
            cid = contract.get("id")
            severity = (contract.get("severity") or "warn").lower()
            rule = contract.get("rule") or {}
            result = _evaluate_rule(rule, ctx)
            record = {
                "spec_path": str(sp),
                "id": cid,
                "severity": severity,
                "rule_type": rule.get("type"),
                "verdict": result.verdict,
                "evidence": result.evidence,
                "message": result.message,
            }
            contracts_out.append(record)
            if result.verdict == "pass":
                pass_n += 1
            elif result.verdict == "skip":
                skip_n += 1
            elif result.verdict == "error":
                err_n += 1
                if severity == "critical":
                    critical_fail_n += 1
            elif result.verdict == "fail":
                if severity == "critical":
                    fail_n += 1
                    critical_fail_n += 1
                elif severity == "warn":
                    warn_n += 1
                else:  # info / unknown severity
                    pass_n += 1
            else:
                # Defensive: treat unknown verdict as error.
                err_n += 1
                if severity == "critical":
                    critical_fail_n += 1

    summary = {
        "total": len(contracts_out),
        "pass": pass_n,
        "warn": warn_n,
        "fail": fail_n,
        "skip": skip_n,
        "error": err_n,
        "critical_fail": critical_fail_n,
        "verdict": "pass" if critical_fail_n == 0 else "fail",
    }
    return contracts_out, summary


# ---- CLI -----------------------------------------------------------


def _load_json(path: Path | None) -> dict | None:
    if path is None:
        return None
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", action="append", type=Path, default=[],
                    help="Path to a spec YAML (may be passed multiple times).")
    ap.add_argument("--consensus", type=Path,
                    help="consensus_model.json path (optional).")
    ap.add_argument("--fidelity-report", type=Path,
                    help="fidelity_report.json path (optional).")
    ap.add_argument("--invariants-report", type=Path,
                    help="geometry_invariants_report.json path (optional).")
    ap.add_argument("--evidence-dir", type=Path,
                    help="directory containing the visual evidence pack (optional).")
    ap.add_argument("--out", type=Path,
                    help="output spec_harness_report.json path.")
    args = ap.parse_args(argv)

    if not args.spec:
        print("[err] at least one --spec is required", file=sys.stderr)
        return 1

    ctx = HarnessContext(
        consensus=_load_json(args.consensus),
        fidelity_report=_load_json(args.fidelity_report),
        invariants_report=_load_json(args.invariants_report),
        evidence_dir=args.evidence_dir,
    )

    contracts, summary = evaluate_specs(args.spec, ctx)

    report = {
        "schema_version": "1.0.0",
        "tool": "spec_harness",
        "specs_loaded": [str(p) for p in args.spec],
        "inputs": {
            "consensus": str(args.consensus) if args.consensus else None,
            "fidelity_report": (str(args.fidelity_report)
                                if args.fidelity_report else None),
            "invariants_report": (str(args.invariants_report)
                                  if args.invariants_report else None),
            "evidence_dir": (str(args.evidence_dir)
                             if args.evidence_dir else None),
        },
        "contracts": contracts,
        "summary": summary,
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[ok] wrote {args.out}")
    print(f"[summary] {summary}")
    return 0 if summary["critical_fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
