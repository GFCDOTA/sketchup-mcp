"""Find what's needed to close each merged-cell loop in a consensus.

For each room cell whose name contains "|" (= multiple seed labels
collapsed into one polygonize cell), enumerates the room pairs and
classifies what closure type would split them. Emits a JSON the
reviewer reads BEFORE painting more walls, so they don't paint walls
where the architecture has none.

Classification taxonomy (per user mandate 2026-05-11):
- ``human_wall``           — a physical wall exists in the PDF but
                              is missing from the consensus. Paint
                              this in BLUE.
- ``human_soft_barrier``   — peitoril / guarda-corpo / esquadria /
                              parapet line. Render as bound on the
                              SKP floor but NOT as a full wall;
                              should be added to soft_barriers, not
                              walls.
- ``semantic_room_split``  — open-plan rooms with no physical
                              divider in the PDF (e.g. SALA DE
                              ESTAR ↔ SALA DE JANTAR). The merge is
                              semantically inaccurate but
                              architecturally honest. DO NOT paint.
- ``already_explained``    — an existing opening (door, window,
                              glazed_balcony) ALREADY sits on the
                              boundary; the merge is a polygonize
                              artifact and would resolve once the
                              opening's host wall closes the loop.

The evidence_source field records WHY we picked the type:
- ``visible_pdf_wall``         (filled rect crossing the segment)
- ``drywall``                  (visible thin partition in PDF)
- ``peitoril``                 (low wall H=1.10m or similar)
- ``guarda-corpo``             (railing)
- ``existing_human_opening``   (an h_o* opening on the segment)
- ``open_plan``                (no physical separator visible)
- ``inferred_only``            (no PDF evidence; conservative
                                 default = semantic_room_split)
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

# Architectural priors for planta_74 — based on visible PDF inspection
# in PR #120 / #121 cycle. Each entry says: "between these two rooms,
# the PDF shows X, so the closure should be Y". When the consensus
# walls don't reflect this, we propose the corresponding action.
#
# Sourced from: door_audit_after_human_walls.png + the PDF in
# planta_74.pdf (visible peitoris / drywalls / open-plan voids).
PLANTA_74_PAIR_PRIORS: dict[frozenset[str], dict] = {
    frozenset({"COZINHA", "A.S."}): {
        "candidate_type": "human_wall",
        "evidence_source": "drywall",
        "confidence": 0.95,
        "should_user_paint": True,
        "reason": "Drywall com vão de porta (h_o005) entre COZINHA e A.S. — "
                   "h_w000 já cobre 40pt mas precisa estender pra fechar loop. "
                   "Wall horizontal at y≈580, x range full A.S./COZINHA column.",
    },
    frozenset({"COZINHA", "SALA DE JANTAR"}): {
        "candidate_type": "semantic_room_split",
        "evidence_source": "open_plan",
        "confidence": 0.85,
        "should_user_paint": False,
        "reason": "Open plan: COZINHA flui pra SALA DE JANTAR sem parede física. "
                   "Bancada (móvel) NÃO conta como parede. Aceitar fusão como honesta.",
    },
    frozenset({"COZINHA", "TERRACO SOCIAL"}): {
        "candidate_type": "already_explained",
        "evidence_source": "existing_human_opening",
        "confidence": 0.80,
        "should_user_paint": False,
        "reason": "Boundary explicada por porta-balcão (h_o011 glazed_balcony) "
                   "ou peitoril intermediário; cell-merge resolve quando o loop "
                   "fecha via SALA DE ESTAR.",
    },
    frozenset({"COZINHA", "TERRACO TECNICO"}): {
        "candidate_type": "human_soft_barrier",
        "evidence_source": "peitoril",
        "confidence": 0.75,
        "should_user_paint": False,
        "reason": "TERRACO TECNICO é varanda externa separada por peitoril "
                   "H=1,10M (já em consensus.soft_barriers). NÃO pintar como wall.",
    },
    frozenset({"A.S.", "TERRACO SOCIAL"}): {
        "candidate_type": "human_wall",
        "evidence_source": "drywall",
        "confidence": 0.80,
        "should_user_paint": True,
        "reason": "Drywall separando A.S. (área serviço) do TERRACO SOCIAL "
                   "(varanda). Wall vertical at x≈130, cobrindo y range "
                   "da A.S./TERRACO transition.",
    },
    frozenset({"A.S.", "TERRACO TECNICO"}): {
        "candidate_type": "human_soft_barrier",
        "evidence_source": "peitoril",
        "confidence": 0.65,
        "should_user_paint": False,
        "reason": "Limítrofe entre A.S. interna e TERRACO TECNICO externo via "
                   "peitoril/grade; soft_barrier, não wall.",
    },
    frozenset({"TERRACO SOCIAL", "TERRACO TECNICO"}): {
        "candidate_type": "human_soft_barrier",
        "evidence_source": "peitoril",
        "confidence": 0.80,
        "should_user_paint": False,
        "reason": "Dois terraços separados por peitoril/muretas (H=0.70M no "
                   "PDF). soft_barrier, não wall.",
    },
    frozenset({"SALA DE JANTAR", "SALA DE ESTAR"}): {
        "candidate_type": "semantic_room_split",
        "evidence_source": "open_plan",
        "confidence": 0.95,
        "should_user_paint": False,
        "reason": "Sala integrada: SALA DE JANTAR e SALA DE ESTAR são um único "
                   "ambiente em planta aberta. NÃO existe parede física. "
                   "Aceitar fusão como semanticamente correta.",
    },
}


@dataclass
class ClosureCandidate:
    from_room: str
    to_room: str
    seed_from: list[float]
    seed_to: list[float]
    midpoint_pdf: list[float]
    distance_pts: float
    candidate_type: str            # human_wall | human_soft_barrier | semantic_room_split | already_explained
    evidence_source: str
    confidence: float
    should_user_paint: bool
    reason: str
    # If wall, estimate suggested segment (perpendicular bisector centered on midpoint)
    suggested_segment_pdf: list[float] | None
    suggested_orientation: str | None
    suggested_length_pts: float | None


def _seed_pairs_in_merged_cell(cell_name: str, labels: list[dict],
                                 cell_polygon: list[list[float]]
                                 ) -> list[tuple[dict, dict]]:
    """Return all unordered pairs of (label_a, label_b) inside the cell."""
    names = [n.strip() for n in cell_name.split("|") if n.strip()]
    label_by_name = {lb["name"]: lb for lb in labels}
    seeds = [label_by_name[n] for n in names if n in label_by_name]
    pairs = []
    for i in range(len(seeds)):
        for j in range(i + 1, len(seeds)):
            pairs.append((seeds[i], seeds[j]))
    return pairs


def classify_pair(a: dict, b: dict) -> dict:
    key = frozenset({a["name"], b["name"]})
    if key in PLANTA_74_PAIR_PRIORS:
        return dict(PLANTA_74_PAIR_PRIORS[key])
    return {
        "candidate_type": "semantic_room_split",
        "evidence_source": "inferred_only",
        "confidence": 0.30,
        "should_user_paint": False,
        "reason": (f"No prior classification for "
                    f"{a['name']} <-> {b['name']}; conservative default = "
                    f"semantic_split (NÃO pintar até confirmação visual)."),
    }


def _suggested_segment(a: dict, b: dict,
                        candidate_type: str
                        ) -> tuple[list[float] | None, str | None, float | None]:
    """When candidate_type=human_wall, suggest a segment perpendicular
    to the seed-pair direction, centered on the midpoint, of length =
    distance between seeds. Returned for reviewer reference, NOT for
    auto-paint."""
    if candidate_type != "human_wall":
        return None, None, None
    sax, say = a["seed_pt"]
    sbx, sby = b["seed_pt"]
    mx = (sax + sbx) / 2.0
    my = (say + sby) / 2.0
    dx = sbx - sax
    dy = sby - say
    # Wall orientation = perpendicular to seed-pair direction
    if abs(dx) >= abs(dy):
        # Seeds spread horizontally → wall is VERTICAL
        orientation = "v"
        # Length matches seed span perpendicular axis (use the smaller of
        # the spread + a 25 pt margin so the wall actually crosses).
        half = max(abs(dy) / 2.0 + 25.0, 50.0)
        seg = [round(mx, 3), round(my - half, 3),
               round(mx, 3), round(my + half, 3)]
    else:
        orientation = "h"
        half = max(abs(dx) / 2.0 + 25.0, 50.0)
        seg = [round(mx - half, 3), round(my, 3),
               round(mx + half, 3), round(my, 3)]
    return seg, orientation, round(2 * half, 3)


def find_candidates(consensus: dict, labels: list[dict]) -> dict:
    rooms = consensus.get("rooms", [])
    merged = [r for r in rooms if "|" in r.get("name", "")]
    candidates: list[ClosureCandidate] = []
    for cell in merged:
        name = cell["name"]
        cell_poly = cell.get("polygon_pts", [])
        pairs = _seed_pairs_in_merged_cell(name, labels, cell_poly)
        for a, b in pairs:
            cls = classify_pair(a, b)
            sax, say = a["seed_pt"]
            sbx, sby = b["seed_pt"]
            mx = (sax + sbx) / 2.0
            my = (say + sby) / 2.0
            dist = ((sax - sbx) ** 2 + (say - sby) ** 2) ** 0.5
            seg, orient, length = _suggested_segment(a, b, cls["candidate_type"])
            candidates.append(ClosureCandidate(
                from_room=a["name"],
                to_room=b["name"],
                seed_from=list(a["seed_pt"]),
                seed_to=list(b["seed_pt"]),
                midpoint_pdf=[round(mx, 3), round(my, 3)],
                distance_pts=round(dist, 3),
                candidate_type=cls["candidate_type"],
                evidence_source=cls["evidence_source"],
                confidence=cls["confidence"],
                should_user_paint=cls["should_user_paint"],
                reason=cls["reason"],
                suggested_segment_pdf=seg,
                suggested_orientation=orient,
                suggested_length_pts=length,
            ))
    # Aggregate counters
    by_type: dict[str, int] = {}
    by_paint: dict[bool, int] = {True: 0, False: 0}
    for c in candidates:
        by_type[c.candidate_type] = by_type.get(c.candidate_type, 0) + 1
        by_paint[c.should_user_paint] += 1
    return {
        "schema_version": "1.0",
        "n_merged_cells": len(merged),
        "n_pairs": len(candidates),
        "by_candidate_type": by_type,
        "n_should_user_paint": by_paint[True],
        "n_should_not_paint": by_paint[False],
        "candidates": [asdict(c) for c in candidates],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--consensus", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    consensus = json.loads(args.consensus.read_text())
    labels = json.loads(args.labels.read_text())
    report = find_candidates(consensus, labels)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(f"[ok] candidates -> {args.out}")
    print(f"  merged cells: {report['n_merged_cells']}")
    print(f"  room pairs:   {report['n_pairs']}")
    print(f"  by_candidate_type: {report['by_candidate_type']}")
    print(f"  should_user_paint: {report['n_should_user_paint']}")
    print(f"  should NOT paint:  {report['n_should_not_paint']}")
    print()
    print("Per-pair classification:")
    print(f"  {'from':>18} {'to':>18} {'type':>22} {'paint?':>7} confidence")
    for c in report["candidates"]:
        print(f"  {c['from_room']:>18} {c['to_room']:>18} "
              f"{c['candidate_type']:>22} "
              f"{'YES' if c['should_user_paint'] else 'no':>7} "
              f"{c['confidence']:.2f}")


if __name__ == "__main__":
    main()
