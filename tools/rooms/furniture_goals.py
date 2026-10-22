"""FP-051/P1: deterministic, read-only furniture capability DAG planner.

Not a SketchUp executor. Identifies missing capabilities and an honest next
learning step, without inferring geometry or inventing dimensions/approved targets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from core.schemas import schema_path
from tools.rooms import capability_catalog as cc
from tools.rooms import evidence_closure, reference_targets, specialists

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "furniture_goal.v1.schema.json"


def _blocked(state: str, why: str, **extra) -> dict:
    return {"state": state, "reason": why, "execution_authorized": False, **extra}


def _ordered(parts: list[dict]) -> tuple[list[dict], str | None]:
    """Topological order; duplicate, unknown and circular edges reject the whole request."""
    by_id = {p["id"]: p for p in parts}
    if len(by_id) != len(parts):
        return [], "duplicate part id"
    for p in parts:
        if p["id"] in p["depends_on"]:
            return [], f"self dependency: {p['id']}"
        if set(p["depends_on"]) - by_id.keys():
            return [], f"unknown dependencies: {p['id']}"
    visited: dict[str, int] = {}
    order: list[dict] = []

    def visit(pid: str) -> bool:
        if visited.get(pid) == 1:
            return False
        if visited.get(pid) == 2:
            return True
        visited[pid] = 1
        for dep in sorted(by_id[pid]["depends_on"]):
            if not visit(dep):
                return False
        visited[pid] = 2
        order.append(by_id[pid])
        return True

    for pid in sorted(by_id):
        if not visit(pid):
            return [], "dependency cycle"
    return order, None


def _reviewed_recipe(recipe_ids: list[str], catalog: dict, root: Path) -> list[str]:
    """Human review is scoped to EXACT recipe and source segment (FP-046/#358)."""
    try:
        video = json.loads((root / catalog["knowledge_catalogs"]["video"]).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    by_source = {s["id"]: s for s in video.get("sources", [])}
    by_recipe = {r["id"]: r for r in video.get("recipes", [])}
    approved = []
    for rid in recipe_ids:
        recipe = by_recipe.get(rid)
        if recipe is None:
            continue
        for ref in recipe.get("sources", []):
            review = by_source.get(ref["id"], {}).get("human_review") or {}
            if (review.get("recipe_id") == rid and review.get("segment")
                    and review["segment"].replace("–", "-") in ref.get("locator", "").replace("–", "-")
                    and review.get("reviewer")):
                approved.append(rid)
                break
    return sorted(set(approved))


def _evidence_current(cap: dict, root: Path) -> bool:
    if cap["validation"]["state"] != "L2_PASS" or not cap["validation"]["evidence"]:
        return False
    verified = set()
    for ev in cap["validation"]["evidence"]:
        digests = ev.get("symbol_digests") or {}
        closures = ev.get("closure_digests") or {}
        for key, digest in digests.items():
            lang, _, ref = key.partition(":")
            if cc.symbol_digest({"lang": lang, "ref": ref}, root) != digest:
                return False
            if lang == "python" and (
                    key not in closures
                    or evidence_closure.current_closure_digest(key, root) != closures[key]):
                return False
            verified.add(key)
    return all(f"{s['lang']}:{s['ref']}" in verified for s in cap["implementation"]["symbols"])


def _target_result(goal: dict, root: Path) -> dict:
    rel = Path(goal["target_ref"])
    if (rel.is_absolute() or ".." in rel.parts or not goal["target_ref"].startswith(
            "artifacts/reference_lab/targets/")):
        return {"ready": False, "codes": ["BLOCKED_TARGET_EVIDENCE"]}
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return {"ready": False, "codes": ["BLOCKED_TARGET_EVIDENCE"]}
    try:
        target = json.loads(path.read_text("utf-8"))
        result = reference_targets.inspect_reference_target(target, root=root)
    except (OSError, ValueError):
        return {"ready": False, "codes": ["BLOCKED_TARGET_EVIDENCE"]}
    if target.get("target_id") != goal["target_id"]:
        return {"ready": False, "codes": ["BLOCKED_TARGET_EVIDENCE"]}
    if not set(p["id"] for p in goal["parts"]).issubset(
            {p["id"] for p in target.get("parts", [])}):
        return {"ready": False, "codes": ["BLOCKED_TARGET_UNDEFINED"]}
    return result


def plan_furniture_goal(goal: dict, *, root: Path = ROOT) -> dict:
    """Pure advisory result: dependencies, reuse, missing abilities, next small task.

    Does not open SketchUp, call run_request, allocate assets or authorize jobs.
    Targets may be DRAFT_BLOCKED: diagnostic gaps still appear, never 'ready'.
    """
    schema = json.loads(schema_path(SCHEMA, root).read_text("utf-8"))
    issues = sorted(Draft202012Validator(schema).iter_errors(goal), key=lambda e: str(e.path))
    if issues:
        return _blocked("BLOCKED_GOAL_SCHEMA", "; ".join(
            f"{'/'.join(map(str, e.path))}: {e.message}" for e in issues[:3]))
    ordered, invalid = _ordered(goal["parts"])
    if invalid:
        return _blocked("BLOCKED_DEPENDENCY_CYCLE", invalid)
    try:
        profile = specialists.load_profile(goal["room"], root)
        catalog = cc.load_catalog(root / "tools/rooms/capability_catalog.v1.json")
    except (OSError, KeyError, ValueError) as exc:
        return _blocked("BLOCKED_INVALID_CONTEXT", str(exc))
    by_binding = {b["id"]: b for b in catalog["bindings"]}
    by_cap = {c["id"]: c for c in catalog["capabilities"]}
    dag, gaps = [], []
    for part in ordered:
        binding = by_binding.get(part["binding_id"])
        if binding is None or binding["room"] != goal["room"]:
            return _blocked("BLOCKED_CAPABILITY_NOT_IN_PROFILE",
                            f"{part['id']}: binding nao pertence a {goal['room']}")
        cid = binding["capability_id"]
        cap = by_cap.get(cid) if cid else None
        reviewed = _reviewed_recipe(binding["recipe_ids"], catalog, root)
        if cap is None:
            action = "BUILD_MICRO_DEMO" if reviewed else "BLOCKED_MISSING_EVIDENCE"
            state = "BLOCKED_CAPABILITY_MISSING" if reviewed else "BLOCKED_KNOWLEDGE_EVIDENCE"
        elif cid not in profile["capability_ids"]:
            return _blocked("BLOCKED_CAPABILITY_NOT_IN_PROFILE", f"{cid} fora do perfil {goal['room']}")
        elif any(t not in profile["tool_allowlist"] for t in cap["tools"]):
            return _blocked("BLOCKED_TOOL_NOT_ALLOWED", f"{cid} fora da allowlist")
        elif cap["implementation"]["state"] != "IMPLEMENTED":
            state, action = "BLOCKED_CAPABILITY_MISSING", "BUILD_MICRO_DEMO"
        elif cap["validation"]["state"] == "L2_PASS" and _evidence_current(cap, root):
            state, action = "L2_PASS", "REUSE_CAPABILITY"
        elif cap["validation"]["state"] == "L2_PASS":
            state, action = "BLOCKED_EVIDENCE_STALE", "REVALIDATE_L2"
        else:
            state, action = "PENDING_SKETCHUP", "VALIDATE_L2"
        node = {"part_id": part["id"], "depends_on": sorted(part["depends_on"]),
                "binding_id": binding["id"], "capability_id": cid,
                "recipe_ids": binding["recipe_ids"], "reviewed_recipe_ids": reviewed,
                "state": state, "decision": action}
        dag.append(node)
        if state != "L2_PASS":
            gaps.append(node)
    target = _target_result(goal, root)
    first = gaps[0] if gaps else None
    if not target.get("ready"):
        state = "BLOCKED_TARGET_UNDEFINED"
    elif first:
        state = first["state"]
    else:
        state = "PLAN_READY_NOT_EXECUTED"
    return {"goal_id": goal["goal_id"], "room": goal["room"],
            "state": state, "target_ready": bool(target.get("ready")),
            "target_blockers": target.get("codes", []), "capability_dag": dag,
            "missing_capabilities": [g["binding_id"] for g in gaps],
            "next_gap": first, "next_step": (first["decision"] if first else
                                                "CHECK_PARAMETERS_AND_PLACEMENT"),
            "execution_authorized": False}


def main() -> int:
    p = argparse.ArgumentParser(description="FP-051/P1: read-only furniture DAG planner")
    p.add_argument("request", type=Path, help="JSON furniture_goal.v1 request")
    args = p.parse_args()
    try:
        result = plan_furniture_goal(json.loads(args.request.read_text("utf-8")))
    except (ValueError, OSError) as exc:
        result = _blocked("BLOCKED_GOAL_SCHEMA", str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["state"] == "PLAN_READY_NOT_EXECUTED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
