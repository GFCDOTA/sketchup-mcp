"""FP-052 reference target: L1 read-only preflight. No SketchUp, writes, or approval mutation.

This is NOT YET connected to the executable kitchen flows. A ready target only
permits proceeding to further gates; it never authorizes execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "core/schemas/reference_target.v1.schema.json"


def inspect_reference_target(target: dict, *, root: Path = ROOT) -> dict:
    """Fail closed for missing authority, source path, checksum, parts and open conflicts."""
    codes = set()
    root = root.resolve()
    schema = json.loads((root / "core/schemas/reference_target.v1.schema.json").read_text("utf-8"))
    problems = sorted(Draft202012Validator(schema).iter_errors(target), key=lambda e: str(e.path))
    if problems:
        return {"schema_valid": False, "ready": False, "codes": ["BLOCKED_TARGET_SCHEMA"],
                "issues": [f"{'/'.join(map(str, e.path))}: {e.message}" for e in problems],
                "execution_authorized": False}

    ids = [x["id"] for x in target["source_refs"]]
    if len(ids) != len(set(ids)):
        codes.add("BLOCKED_TARGET_EVIDENCE")
    refs = {s["id"]: s for s in target["source_refs"]}
    for source in target["source_refs"]:
        try:
            rel = Path(source["path"])
            if rel.is_absolute() or ".." in rel.parts or not (root / rel).resolve().is_relative_to(root):
                raise ValueError("unsafe path")
            resolved = (root / rel).resolve()
            if not resolved.is_file():
                raise ValueError("missing file")
            digest = source["sha256"]
            if digest and hashlib.sha256(resolved.read_bytes()).hexdigest() != digest:
                raise ValueError("sha256 mismatch")
            if target["state"] == "APPROVED_TARGET" and digest is None:
                raise ValueError("approved target needs source hash")
        except (ValueError, OSError):
            codes.add("BLOCKED_TARGET_EVIDENCE")

    for part in target["parts"]:
        required = part["required_source_ids"]
        visuals = part["reference_view_ids"]
        if any(r not in refs for r in required) or any(
            v not in refs or refs[v]["role"] != "VISUAL" for v in visuals
        ):
            codes.add("BLOCKED_TARGET_EVIDENCE")
        if target["state"] == "APPROVED_TARGET" and (
            part["target_state"] != "APPROVED" or not required or not visuals
            or not part["anatomy_and_operations"] or not part["acceptance_checks"]
        ):
            codes.add("BLOCKED_TARGET_UNDEFINED")

    if any(c["status"] == "OPEN" for c in target["conflicts"]):
        codes.add("BLOCKED_TARGET_CONFLICT")
    if any(s not in refs or refs[s]["role"] not in ("VISUAL", "DESIGN_DECISION")
           for s in target["style"]["source_ids"]):
        codes.add("BLOCKED_TARGET_EVIDENCE")

    approval = target["approval"]
    if (target["state"] != "APPROVED_TARGET" or approval["decision"] != "APPROVED"
            or approval["scope"] != "FURNITURE_TARGET" or not approval["reviewer"]
            or not approval["review_record_path"]):
        codes.add("BLOCKED_TARGET_UNDEFINED")
    else:
        try:
            approval_path = (root / approval["review_record_path"]).resolve()
            if not approval_path.is_relative_to(root) or not approval_path.is_file():
                raise ValueError("invalid approval record")
        except (ValueError, OSError):
            codes.add("BLOCKED_TARGET_EVIDENCE")
    return {"schema_valid": True, "ready": not codes, "codes": sorted(codes),
            "target_id": target["target_id"], "execution_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reference target preflight (read-only)")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        target = json.loads(args.manifest.read_text("utf-8"))
        result = inspect_reference_target(target)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"schema_valid": False, "ready": False, "codes": ["BLOCKED_TARGET_SCHEMA"],
                  "issues": [str(exc)], "execution_authorized": False}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ready"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
