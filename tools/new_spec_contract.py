"""Scaffold a new spec contract YAML stub.

Reduces friction for adding new architectural contracts: instead of
hand-copying an existing spec to figure out the layout, contributors
run

  python -m tools.new_spec_contract \
      --planta planta_74 \
      --aspect rooms \
      --rule-type no_merged_room_names \
      --id rooms-no-merged-as-tt-cell \
      --severity critical

and get an idempotent insert into ``specs/planta_74/rooms.spec.yaml``
with the rule-specific parameter skeleton + a TODO description.

The tool is deliberately PYTHON-AND-YAML-LITERATE only — it doesn't
need a template engine. The rule-specific skeletons live in
``_RULE_SKELETONS`` below; adding a new rule type to spec_harness
should also add an entry there.

Idempotency: if the contract id already exists in the target spec,
the tool refuses to overwrite (use ``--force`` to replace). New
spec files are created with the standard preamble.

The tool DOES NOT validate the resulting YAML — run ``lint_specs``
afterwards. Two-step protocol on purpose: scaffold → fill in
description + parameters → lint.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml  # noqa: I001

from tools.spec_harness import _RULE_DISPATCHERS

# Rule-specific parameter skeletons. Keys mirror the rule_type
# dispatcher names in tools.spec_harness._RULE_DISPATCHERS. Values
# are dicts that will be inserted under ``rule:``; the user fills
# in concrete values after scaffolding.
_RULE_SKELETONS: dict[str, dict[str, Any]] = {
    "no_merged_room_names": {
        "forbidden_substrings": ["TODO REPLACE | TODO REPLACE"],
    },
    "expected_room_names": {
        "required": ["TODO_ROOM_NAME"],
    },
    "room_area_range": {
        "ranges": [
            {"name": "TODO_ROOM_NAME", "min_m2": 0.0, "max_m2": 0.0},
        ],
    },
    "soft_barriers_protected_count": {
        "min": 1,
        "semantic_keywords": ["peitoril", "mureta"],
    },
    "soft_barriers_count_range": {
        "min": 0,
        "max": 30,
    },
    "soft_barriers_wall_coincident_count": {
        "max_overlap_fraction": 0.5,
        "max_count": 4,
    },
    "soft_barrier_height_band": {
        "max_height_m": 2.0,
    },
    "door_leaf_proximity": {
        "max_distance_m": 1.0,
    },
    "room_has_door": {
        "rooms_requiring_door": ["TODO_ROOM_NAME"],
    },
    "evidence_pack_present": {
        "required_artifacts": ["TODO_ARTIFACT.png"],
    },
    "fidelity_axis_pass": {
        "axes": ["TODO_AXIS"],
        "min_score": 0.80,
    },
    "fidelity_axes_observe": {},
    "invariants_verdict_pass": {},
    "openings_min_kind_count": {
        "kind": "TODO_KIND",
        "min_count": 1,
    },
    "openings_count_range": {
        "min": 0,
        "max": 30,
    },
}


def _new_spec_preamble(planta: str, aspect: str) -> dict[str, Any]:
    """Default top-level structure for a new spec YAML."""
    return {
        "schema_version": "1.0.0",
        "target": planta,
        "contracts": [],
    }


def _build_contract(contract_id: str, severity: str,
                    rule_type: str) -> dict[str, Any]:
    """Construct the contract dict to insert."""
    skeleton = _RULE_SKELETONS.get(rule_type, {})
    rule_body: dict[str, Any] = {"type": rule_type}
    rule_body.update(skeleton)
    return {
        "id": contract_id,
        "severity": severity,
        "description": (
            f"TODO: explain why this contract exists, what failure mode "
            f"it catches, and link to evidence (PR, ADR, FP-NNN). "
            f"Scaffolded for {rule_type}."
        ),
        "rule": rule_body,
    }


def scaffold(specs_dir: Path, planta: str, aspect: str,
             contract_id: str, severity: str, rule_type: str,
             *, force: bool = False) -> tuple[Path, bool]:
    """Insert a new contract into ``specs/<planta>/<aspect>.spec.yaml``.

    Returns ``(path, created_spec_file)`` where ``created_spec_file``
    is True if the target spec file did not previously exist.

    Raises:
      ValueError on unsupported rule type / invalid severity / id
        collision (when ``force=False``).
    """
    if rule_type not in _RULE_DISPATCHERS:
        raise ValueError(
            f"unknown rule type {rule_type!r}; supported: "
            f"{sorted(_RULE_DISPATCHERS)}"
        )
    if severity not in {"critical", "warn", "info"}:
        raise ValueError(
            f"severity {severity!r} not in {{critical, warn, info}}"
        )

    target_dir = specs_dir / planta
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{aspect}.spec.yaml"

    created = not target_path.exists()
    if created:
        doc = _new_spec_preamble(planta, aspect)
    else:
        doc = yaml.safe_load(target_path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise ValueError(
                f"{target_path}: existing root is {type(doc).__name__}, "
                "expected mapping; cannot insert"
            )
        # Ensure required keys exist (defensive — older specs may be
        # incomplete but still loadable).
        doc.setdefault("schema_version", "1.0.0")
        doc.setdefault("target", planta)
        doc.setdefault("contracts", [])

    # ID collision check.
    existing_ids = [c.get("id") for c in doc["contracts"]
                    if isinstance(c, dict)]
    if contract_id in existing_ids and not force:
        raise ValueError(
            f"contract id {contract_id!r} already exists in {target_path}; "
            "pass --force to replace"
        )

    new_contract = _build_contract(contract_id, severity, rule_type)
    if force:
        # Replace the existing entry in-place, preserving order.
        doc["contracts"] = [new_contract if c.get("id") == contract_id
                            else c for c in doc["contracts"]
                            if isinstance(c, dict)]
        if contract_id not in [c.get("id") for c in doc["contracts"]
                                if isinstance(c, dict)]:
            doc["contracts"].append(new_contract)
    else:
        doc["contracts"].append(new_contract)

    target_path.write_text(yaml.safe_dump(doc, sort_keys=False,
                                           allow_unicode=True),
                            encoding="utf-8")
    return target_path, created


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--specs-dir", type=Path, default=Path("specs"))
    ap.add_argument("--planta", required=True,
                    help="planta identifier (e.g. planta_74)")
    ap.add_argument("--aspect", required=True,
                    choices=("rooms", "openings", "soft_barriers", "fidelity"),
                    help="which aspect file to update")
    ap.add_argument("--id", dest="contract_id", required=True,
                    help="globally unique contract id (kebab-case)")
    ap.add_argument("--severity", default="warn",
                    choices=("critical", "warn", "info"))
    ap.add_argument("--rule-type", required=True,
                    choices=sorted(_RULE_DISPATCHERS),
                    help="rule type (must match a spec_harness dispatcher)")
    ap.add_argument("--force", action="store_true",
                    help="replace existing contract with the same id")
    args = ap.parse_args(argv)

    try:
        path, created = scaffold(
            args.specs_dir, args.planta, args.aspect,
            args.contract_id, args.severity, args.rule_type,
            force=args.force,
        )
    except ValueError as e:
        print(f"[err] {e}", file=sys.stderr)
        return 1

    state = "created" if created else "appended to"
    print(f"[ok] {state} {path} with contract {args.contract_id!r}")
    print("     next: fill in 'description' + rule parameters, then "
          "run python -m tools.lint_specs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
