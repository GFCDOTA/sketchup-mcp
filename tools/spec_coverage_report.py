"""Spec ↔ failure-pattern coverage map.

The repo has two parallel catalogues:

  1. ``docs/learning/failure_patterns.md`` — every FP-NNN entry +
     ``tests/test_failure_patterns_regression_catalog.py`` which
     enforces that each FP has ≥ 1 regression TEST.
  2. ``specs/<planta>/*.spec.yaml`` — architectural contracts that
     run via ``tools/spec_harness.py``.

The IMPLEMENTATION test catalog (#1) and the CONTRACT spec catalog
(#2) cover different surfaces:

  - tests assert that the CODE behaves as documented;
  - specs assert that the OUTPUT matches an external truth.

A mature project wants BOTH for every architectural failure mode.
This tool computes the matrix:

       FP-NNN  ←→  spec_contract_id  (zero or more)

and surfaces:

  - FPs with NO spec coverage (test-only — opportunity to harden);
  - spec contracts with NO FP back-link (orphaned coverage — likely
    fine if the contract is a "new" architectural truth not yet
    tied to a failure event);
  - the total coverage percentage.

The mapping itself is hand-curated in ``KNOWN_FP_SPEC_LINKS`` at
the top of this file; the tool only validates that the curated
links resolve to real entries on both sides.

Usage:

  python -m tools.spec_coverage_report \
      --specs-dir specs/ \
      --failure-patterns docs/learning/failure_patterns.md \
      --out runs/spec_coverage_report.json

Exits 0 always — this is an observational tool, NOT a gate. The
spec_harness is the gate; this tool is the inventory.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml  # noqa: I001 — keeps third-party last (matches repo style)

# Hand-curated link table — keep small and explicit. Each entry maps
# an FP-NNN to the set of spec contract IDs that, taken together,
# would surface the failure mode the FP describes. Update this
# whenever a new spec contract is added that mitigates an existing
# FP, or when a new FP is documented for an already-covered area.
#
# An empty list is an HONEST acknowledgement that the FP has no
# spec coverage today — the report surfaces those so the team can
# prioritise.
KNOWN_FP_SPEC_LINKS: dict[str, list[str]] = {
    "FP-001": [],  # cheap-gate ordering — infra, not architectural truth
    "FP-002": [],  # forgotten dep — install-time, not spec
    "FP-003": [],  # direct push to main — git policy
    "FP-004": [],  # ruff --fix global — git policy
    "FP-005": [],  # triplication of geometry — CI grep gate covers it
    "FP-006": [
        # The wall-coincident-SB noise that the FP-006 filter rejects.
        # soft_barriers-not-wall-coincident-noise (warn) is the
        # architectural projection — count of noise SBs should be low.
        "soft_barriers-not-wall-coincident-noise",
    ],
    "FP-007": [],  # SU welcome dialog — launcher-level, not spec
    "FP-008": [],  # mass branch deletion — git policy
    "FP-009": [],  # specialist agents write perms — agent spec
    "FP-010": [],  # hidden CI deselects — meta-CI policy
    "FP-011": [],  # ground-truth leaked into validator — pipeline policy
    "FP-012": [
        # Convex-hull room clip leakage — manifests as a wildly large
        # SUITE 01 polygon. The area band check on SUITE 01 is the
        # architectural canary. Not a perfect mapping (the FP is
        # about hull strategy, the spec about resulting area) but
        # the spec WOULD have surfaced the regression.
        "rooms-area-suite-01",
    ],
    "FP-013": [],  # adjacency_f1 plateau — fidelity-axis advisory
    "FP-014": [],  # autorun control orphan — runtime cleanup, not spec
    "FP-015": [
        # DoorLeaf vertical-wall hinge bug. The proximity contract
        # is the architectural projection of the regression test.
        "openings-door-leaf-proximity-to-host",
    ],
    "FP-016": [
        # Boundary-coincident SBs causing merged floor cell.
        "rooms-no-merged-as-tt-cell",
        "rooms-no-merged-salas-cell",
        "soft_barriers-protected-count-minimum",
    ],
}


def _fp_ids_in_md(md_path: Path) -> list[str]:
    """Extract every ``## FP-NNN`` heading from a failure-patterns md."""
    if not md_path.exists():
        return []
    text = md_path.read_text(encoding="utf-8")
    return re.findall(r"^## (FP-\d+)\b", text, flags=re.M)


def _spec_contract_ids(specs_dir: Path) -> dict[str, str]:
    """Map contract_id → spec_path for every contract in every
    spec YAML under ``specs_dir`` (recursive)."""
    out: dict[str, str] = {}
    for sp in sorted(specs_dir.rglob("*.spec.yaml")):
        try:
            data = yaml.safe_load(sp.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        for c in data.get("contracts") or []:
            cid = c.get("id")
            if cid:
                out[cid] = str(sp.relative_to(specs_dir.parent)
                                if sp.is_absolute() else sp)
    return out


def build_coverage_report(
    fp_md_path: Path, specs_dir: Path,
) -> dict[str, Any]:
    """Produce the spec ↔ FP coverage matrix as a dict ready to
    json.dumps. Surfaces dangling links on both sides:

      - FP-NNN listed in KNOWN_FP_SPEC_LINKS but missing from the md
      - FP-NNN in the md but not in KNOWN_FP_SPEC_LINKS
      - spec contract referenced in KNOWN_FP_SPEC_LINKS but missing
        from the actual YAMLs
      - spec contract present in the YAMLs but never referenced from
        any FP (orphan coverage — informational)
    """
    md_fps = sorted(set(_fp_ids_in_md(fp_md_path)))
    known_fps = sorted(KNOWN_FP_SPEC_LINKS.keys())
    contract_to_spec = _spec_contract_ids(specs_dir)
    all_contract_ids = sorted(contract_to_spec.keys())

    fps_missing_from_md = sorted(set(known_fps) - set(md_fps))
    fps_missing_from_links = sorted(set(md_fps) - set(known_fps))

    contracts_referenced: set[str] = set()
    bad_contract_refs: list[tuple[str, str]] = []
    fp_rows: list[dict[str, Any]] = []
    for fp_id in md_fps:
        spec_ids = KNOWN_FP_SPEC_LINKS.get(fp_id, [])
        missing_contracts = [cid for cid in spec_ids
                             if cid not in contract_to_spec]
        for cid in missing_contracts:
            bad_contract_refs.append((fp_id, cid))
        contracts_referenced.update(spec_ids)
        fp_rows.append({
            "fp_id": fp_id,
            "covered_by": spec_ids,
            "covered_by_count": len(spec_ids),
            "has_spec_coverage": len(spec_ids) > 0,
            "missing_contracts": missing_contracts,
        })

    orphan_contracts = sorted(set(all_contract_ids) - contracts_referenced)

    fp_with_coverage = sum(1 for r in fp_rows if r["has_spec_coverage"])
    total_fps = len(fp_rows)
    coverage_pct = (100.0 * fp_with_coverage / total_fps) if total_fps else 0.0

    summary = {
        "total_fps_in_md": total_fps,
        "fps_with_spec_coverage": fp_with_coverage,
        "fps_without_spec_coverage": total_fps - fp_with_coverage,
        "coverage_percentage": round(coverage_pct, 1),
        "total_spec_contracts": len(all_contract_ids),
        "orphan_contracts_count": len(orphan_contracts),
        "fps_in_links_missing_from_md": fps_missing_from_md,
        "fps_in_md_missing_from_links": fps_missing_from_links,
        "bad_contract_references": [
            {"fp_id": fp, "contract_id": cid}
            for fp, cid in bad_contract_refs
        ],
    }

    return {
        "schema_version": "1.0.0",
        "tool": "spec_coverage_report",
        "failure_patterns_md": str(fp_md_path),
        "specs_dir": str(specs_dir),
        "fps": fp_rows,
        "orphan_contracts": orphan_contracts,
        "all_contract_ids": all_contract_ids,
        "summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--specs-dir", type=Path, default=Path("specs"))
    ap.add_argument("--failure-patterns", type=Path,
                    default=Path("docs/learning/failure_patterns.md"))
    ap.add_argument("--out", type=Path,
                    help="output JSON path (default: stdout pretty)")
    args = ap.parse_args(argv)

    report = build_coverage_report(args.failure_patterns, args.specs_dir)
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"[ok] wrote {args.out}")
    else:
        print(text)

    s = report["summary"]
    print(
        f"\n[summary] FPs={s['total_fps_in_md']} "
        f"with_coverage={s['fps_with_spec_coverage']} "
        f"({s['coverage_percentage']}%) "
        f"orphans={s['orphan_contracts_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
