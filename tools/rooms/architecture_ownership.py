"""FP-042 P1/P2: static owner role gate for infrastructure and cross-room primitives.

Path/role proof only, separately from semantic and SketchUp L2 verification.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs/specs/fp042_inventory.v1.json"


def owner_for(path: str, phase: str) -> str | None:
    if phase == "P1":
        for prefix, owner in (
            ("tools/rooms/", "room_module_registry_or_governance"),
            (".github/", "repository_ci_and_package_infrastructure"),
            (".git", "repository_ci_and_package_infrastructure"),
            ("configs/", "versioned_configurations"),
            ("ops/", "operational_dashboard"),
        ):
            if path.startswith(prefix):
                return owner
        if path in (".dockerignore", "pyproject.toml", "uv.lock"):
            return "repository_ci_and_package_infrastructure"
    if phase == "P2":
        for prefix, owner in (
            ("tests/", "regression_test_suite"),
            ("core/schemas/", "shared_validation_schemas"),   # FP-044/F3: schemas/ da raiz -> core/schemas/, mesmo dono
            ("core/", "core_cross_room_domain"),
            ("scripts/", "shared_gate_automation"),
            ("tools/rooms/shared/", "shared_room_primitives"),
            ("tools/rooms/kitchen/", "kitchen_validation_boundary"),
            ("tools/rooms/bathroom/", "bathroom_validation_boundary"),
            ("tools/rooms/", "room_module_governance"),
            ("tools/", "cross_room_shared_gates"),
        ):
            if path.startswith(prefix):
                return owner
    return None


def audit(index: dict) -> dict:
    entries = [e for e in index.get("entries", [])
               if e.get("phase") in ("P1", "P2")]
    bad = sorted(e["path"] for e in entries if
                 owner_for(e["path"], e["phase"]) is None
                 or e.get("architecture_owner") != owner_for(e["path"], e["phase"])
                 or e.get("disposition") != "retain_architecture_boundary_with_explicit_owner"
                 or e.get("status") != "VERIFIED_PATH_BASED_OWNER_CLASSIFICATION"
                 or e.get("ownership_evidence") !=
                 "FP042_P1_P2_PATH_ROLES_AND_AST_GATES_NO_SEMANTIC_REWRITE")
    return {"result": "FAIL" if bad else "PASS", "checked": len(entries),
            "unresolved": bad, "proof": "STATIC_OWNER_NOT_SEMANTIC_OR_L2"}


def main() -> int:
    out = audit(json.loads(INVENTORY.read_text("utf-8")))
    print(json.dumps(out, indent=2))
    return 0 if out["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
