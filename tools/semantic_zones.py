#!/usr/bin/env python3
"""M3 — semantic_zones overlay loader (annotation-only, NO geometry).

Resolves the planta_74 ``room_fidelity`` WARN honestly. The PDF draws some
ambients open-plan (no physical wall between e.g. SALA DE JANTAR / SALA DE
ESTAR), so ``polygonize`` closes ONE geometric cell where the plan legend names
two or three ambients. Counting geometric cells (8) against named ambients (11)
therefore under-counts rooms — a WARN, not a defect.

This module reads a ``semantic_zones.json`` overlay that maps each geometric
cell (a consensus room) to one or more *named* semantic zones. It adds NO wall,
opening, or polygon — only labels that are already authored in the consensus
(``rooms[].name`` pipe-separated, plus ``label_ids`` / ``merged_seeds`` for the
merged cells). Hard Rule #1 (never invent walls/rooms/openings) is preserved:
the overlay annotates; it does not build.

Pure + deterministic: consensus + overlay JSON in, dict out. No SU/PDF/network.
End-to-end validation against a real ``.skp`` build still needs SketchUp and is
out of scope here (the shell geometry is unchanged by design, so a build would
show the SAME 8 cells — the overlay only changes how they are *counted/named*).
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_VERSION = "semantic_zones.v1"


def _consensus_path(fixture: str) -> Path:
    p = (REPO_ROOT / "fixtures" / fixture
         / "consensus_with_human_walls_and_soft_barriers.json")
    if p.exists():
        return p
    cands = sorted((REPO_ROOT / "fixtures" / fixture).glob("consensus*.json"))
    if not cands:
        raise FileNotFoundError(f"no consensus json for fixture {fixture}")
    return cands[0]


def _overlay_path(fixture: str) -> Path:
    return REPO_ROOT / "fixtures" / fixture / "semantic_zones.json"


def load_consensus(fixture: str) -> dict:
    return json.loads(_consensus_path(fixture).read_text("utf-8"))


def load_overlay(fixture: str) -> dict:
    p = _overlay_path(fixture)
    if not p.exists():
        raise FileNotFoundError(f"no semantic_zones.json for fixture {fixture}")
    return json.loads(p.read_text("utf-8"))


def _consensus_zone_names(consensus: dict) -> dict[str, list[str]]:
    """cell_id -> the ambient names the consensus itself authored for that cell.

    This is the ground truth for provenance: a zone name is only legitimate if
    it appears (verbatim) in the pipe-separated ``rooms[].name`` of its cell.
    """
    out: dict[str, list[str]] = {}
    for r in consensus.get("rooms", []):
        out[r["id"]] = [p.strip() for p in r.get("name", "").split("|") if p.strip()]
    return out


def validate_overlay(consensus: dict, overlay: dict) -> dict:
    """Structural + provenance check. NO geometry is touched.

    Guards specifically against fabrication:
      - every cell_id in the overlay must be a real consensus room,
      - every consensus room must be covered exactly once,
      - every zone name must appear verbatim in that cell's consensus name
        (i.e. no zone invented beyond what the consensus already labels).

    Returns ``{"overall": "PASS"|"FAIL", "errors": [...]}``. Pure.
    """
    errors: list[str] = []

    if overlay.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version {overlay.get('schema_version')!r} != {SCHEMA_VERSION!r}")

    truth = _consensus_zone_names(consensus)
    consensus_ids = set(truth)
    overlay_cells = overlay.get("cells", [])
    seen: set[str] = set()

    for c in overlay_cells:
        cid = c.get("cell_id")
        if cid not in consensus_ids:
            errors.append(f"cell {cid!r} not a consensus room (invented cell)")
            continue
        if cid in seen:
            errors.append(f"cell {cid!r} annotated more than once")
        seen.add(cid)

        zone_names = [z.get("name", "").strip() for z in c.get("zones", [])]
        if not zone_names:
            errors.append(f"cell {cid!r} has no zones")
        for nm in zone_names:
            if nm not in truth[cid]:
                errors.append(
                    f"cell {cid!r} zone {nm!r} not in consensus name "
                    f"{truth[cid]!r} (fabricated zone)")
        # open_plan_merge flag must agree with reality (>1 ambient in the name)
        expected_merge = len(truth[cid]) > 1
        if bool(c.get("open_plan_merge")) != expected_merge:
            errors.append(
                f"cell {cid!r} open_plan_merge={c.get('open_plan_merge')} but "
                f"consensus names {len(truth[cid])} ambient(s)")

    missing = consensus_ids - seen
    if missing:
        errors.append(f"consensus rooms not covered by overlay: {sorted(missing)}")

    return {"overall": "FAIL" if errors else "PASS", "errors": errors}


def zone_mapping(overlay: dict) -> dict[str, list[str]]:
    """cell_id -> [zone name, ...] as annotated by the overlay."""
    return {
        c["cell_id"]: [z["name"] for z in c.get("zones", [])]
        for c in overlay.get("cells", [])
    }


def count_cells(consensus: dict) -> int:
    return len(consensus.get("rooms", []))


def count_zones(overlay: dict) -> int:
    return sum(len(c.get("zones", [])) for c in overlay.get("cells", []))


def assess_room_fidelity(fixture: str = "planta_74") -> dict:
    """Room-fidelity assessment WITH the semantic overlay applied.

    Without the overlay the pipeline sees ``geometric_cells`` closed rooms and
    the plan legend names ``semantic_zones`` ambients — the mismatch is the
    documented ``room_fidelity`` WARN. With the overlay the two open-plan cells
    are explained (annotated as multiple named zones from the consensus), so the
    count reconciles and the axis is reported EXPLAINED rather than a bare WARN.

    Geometry is never mutated: the shell still has ``geometric_cells`` cells.
    Returns a report dict; ``verdict`` is ``EXPLAINED`` when the overlay accounts
    for every zone, else ``WARN`` (falls back to the honest documented state).
    """
    consensus = load_consensus(fixture)
    overlay = load_overlay(fixture)
    val = validate_overlay(consensus, overlay)

    cells = count_cells(consensus)
    zones = count_zones(overlay)
    open_plan = [c["cell_id"] for c in overlay.get("cells", [])
                 if c.get("open_plan_merge")]

    if val["overall"] != "PASS":
        # A broken/fabricated overlay must NOT upgrade the verdict — degrade to
        # the honest baseline WARN and surface why.
        return {
            "axis": "room_fidelity",
            "verdict": "WARN",
            "geometric_cells": cells,
            "semantic_zones": zones,
            "overlay_valid": False,
            "errors": val["errors"],
            "explanation": "overlay invalid; room_fidelity stays baseline WARN",
        }

    return {
        "axis": "room_fidelity",
        "verdict": "EXPLAINED",
        "geometric_cells": cells,
        "semantic_zones": zones,
        "open_plan_cells": open_plan,
        "overlay_valid": True,
        "mapping": zone_mapping(overlay),
        "explanation": (
            f"{cells} geometric cells carry {zones} named semantic zones; the "
            f"{len(open_plan)} open-plan cell(s) {open_plan} are annotated "
            "(not walled) — shell geometry unchanged, Hard Rule #1 preserved."
        ),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="semantic_zones overlay assessment")
    ap.add_argument("--fixture", default="planta_74")
    a = ap.parse_args()
    rep = assess_room_fidelity(a.fixture)
    print(f"[semantic-zones] fixture={a.fixture} verdict={rep['verdict']} "
          f"cells={rep['geometric_cells']} zones={rep['semantic_zones']} "
          f"overlay_valid={rep['overlay_valid']}")
    if rep.get("errors"):
        for e in rep["errors"]:
            print(f"  ERR {e}")
    print(f"  {rep['explanation']}")
    raise SystemExit(0 if rep["verdict"] == "EXPLAINED" else 1)
