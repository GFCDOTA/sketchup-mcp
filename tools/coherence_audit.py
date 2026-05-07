"""coherence_audit.py — Stage 1 of the uncertainty-aware pipeline.

Reads a classified consensus.json (post `classify_openings_by_room_context`)
PLUS a project assumptions.yaml, and emits TWO audit artifacts:

  - coherence_report.json   — facts, hypotheses, ambiguities, drops,
                              policy applied, summary counts
  - questions.json          — Rodada-2 follow-up questions for items
                              the policy routed to ``decision=='ask'``

Non-blocking by default: ALWAYS exits 0 if it could read the inputs,
even when the report contains drops / asks / floating doors. Pass
``--strict`` to opt into blocking exit codes for any of the issues
listed in ``assumptions.strict_blockers``.

Stage 1 boundary (PR feature/coherence-audit):
  - DOES NOT change consensus geometry
  - DOES NOT modify walls, rooms, openings beyond classifier output
  - DOES NOT call SketchUp / Ruby exporter
  - DOES NOT call any LLM
  - DOES NOT generate answers.json (Stage 2)

JSON schemas: see docs/SCHEMA-COHERENCE-REPORT.md. Both outputs
include ``schema_version: "1.0"``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from tools.assumptions_loader import (
    DEFAULT_ASSUMPTIONS_PATH,
    Assumptions,
    load_assumptions,
)

COHERENCE_REPORT_SCHEMA_VERSION = "1.0"
QUESTIONS_SCHEMA_VERSION = "1.0"


# ---- Detectors (read-only audits over consensus) ----

def _detect_floating_doors(consensus: dict) -> list[dict]:
    """An opening is "floating" if it lacks a host wall_id OR the
    wall_id doesn't resolve to any wall in the consensus."""
    walls_by_id = {w["id"]: w for w in (consensus.get("walls") or [])}
    issues = []
    for op in consensus.get("openings") or []:
        wid = op.get("wall_id")
        if not wid or wid not in walls_by_id:
            issues.append({
                "opening_id": op.get("id"),
                "wall_id_claimed": wid,
                "kind_v5": op.get("kind_v5"),
            })
    return issues


def _detect_invalid_room_polygons(consensus: dict) -> list[dict]:
    issues = []
    for r in consensus.get("rooms") or []:
        poly = r.get("polygon_pts") or []
        if len(poly) < 3:
            issues.append({"room_id": r.get("id"),
                            "name": r.get("name"),
                            "reason": f"polygon has {len(poly)} pts (<3)"})
    return issues


def _detect_duplicate_walls(consensus: dict,
                              tol_pt: float = 1.0) -> list[dict]:
    """Two walls are 'duplicate' if same orientation + same cross
    coordinate within tol_pt + overlapping axis range."""
    walls = consensus.get("walls") or []
    issues = []
    for i, a in enumerate(walls):
        for b in walls[i + 1:]:
            if a.get("orientation") != b.get("orientation"):
                continue
            if a.get("orientation") == "h":
                if abs(a["start"][1] - b["start"][1]) > tol_pt:
                    continue
                ax = sorted([a["start"][0], a["end"][0]])
                bx = sorted([b["start"][0], b["end"][0]])
                if ax[1] < bx[0] - tol_pt or bx[1] < ax[0] - tol_pt:
                    continue
            else:
                if abs(a["start"][0] - b["start"][0]) > tol_pt:
                    continue
                ay = sorted([a["start"][1], a["end"][1]])
                by = sorted([b["start"][1], b["end"][1]])
                if ay[1] < by[0] - tol_pt or by[1] < ay[0] - tol_pt:
                    continue
            issues.append({"wall_a": a.get("id"), "wall_b": b.get("id"),
                            "orientation": a.get("orientation")})
    return issues


# ---- Report builders ----

def _consensus_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summarise_decisions(consensus: dict) -> dict:
    counts: dict = defaultdict(int)
    by_kind: dict = defaultdict(int)
    for op in consensus.get("openings") or []:
        counts[op.get("decision", "unknown")] += 1
        by_kind[op.get("kind_v5", "unknown")] += 1
    return {
        "openings_total": len(consensus.get("openings") or []),
        "by_decision": dict(counts),
        "by_kind": dict(by_kind),
    }


def build_coherence_report(consensus: dict,
                             consensus_path: Path,
                             assumptions: Assumptions,
                             ) -> dict:
    """Pure function: build the full report dict from the inputs.
    No I/O, no mutation of consensus. The caller writes the JSON."""
    floating = _detect_floating_doors(consensus)
    invalid_rooms = _detect_invalid_room_polygons(consensus)
    dup_walls = _detect_duplicate_walls(consensus)

    facts = []
    for w in consensus.get("walls") or []:
        facts.append({"category": "wall", "id": w.get("id")})
    for r in consensus.get("rooms") or []:
        facts.append({"category": "room", "id": r.get("id"),
                       "name": r.get("name")})
    for op in consensus.get("openings") or []:
        facts.append({"category": "opening", "id": op.get("id"),
                       "kind": op.get("kind_v5"),
                       "decision": op.get("decision")})

    hypotheses = []
    ambiguities = []
    drops = []
    for op in consensus.get("openings") or []:
        oid = op.get("id")
        decision = op.get("decision")
        candidates = op.get("hypotheses") or []
        hypotheses.append({
            "opening_id": oid,
            "selected": op.get("kind_v5"),
            "candidates": candidates,
            "decision": decision,
            "confidence": op.get("confidence"),
        })
        if decision == "ask":
            ambiguities.append({
                "opening_id": oid,
                "confidence": op.get("confidence"),
                "evidence": op.get("evidence"),
                "candidates": candidates,
            })
        elif decision == "drop":
            drops.append({
                "opening_id": oid,
                "confidence": op.get("confidence"),
                "evidence": op.get("evidence"),
                "reason": op.get("kind_v5_reason"),
            })

    risks: list[str] = []
    if floating:
        risks.append(
            f"{len(floating)} opening(s) reference unknown wall_id"
        )
    if invalid_rooms:
        risks.append(
            f"{len(invalid_rooms)} room(s) with polygon < 3 pts"
        )
    if dup_walls:
        risks.append(
            f"{len(dup_walls)} wall pair(s) overlap; carving may "
            f"double-shrink walls"
        )
    if not (consensus.get("rooms") or []):
        risks.append("no rooms detected; openings are unclassifiable")

    return {
        "schema_version": COHERENCE_REPORT_SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "consensus_path": str(consensus_path),
        "consensus_sha256": _consensus_sha256(consensus_path),
        "assumptions": {
            "schema_version": assumptions.schema_version,
            "goal": assumptions.goal,
            "risk_policy": assumptions.risk_policy,
            "ambiguity": {
                "drop_below": assumptions.ambiguity.drop_below,
                "ask_above": assumptions.ambiguity.ask_above,
                "debug_above": assumptions.ambiguity.debug_above,
                "clean_above": assumptions.ambiguity.clean_above,
            },
            "source_path": assumptions.source_path,
        },
        "summary": _summarise_decisions(consensus),
        "facts": facts,
        "hypotheses": hypotheses,
        "ambiguities": ambiguities,
        "drops": drops,
        "issues": {
            "floating_doors": floating,
            "invalid_rooms": invalid_rooms,
            "duplicate_walls": dup_walls,
        },
        "risks": risks,
    }


def build_questions(consensus: dict,
                     report: dict) -> dict:
    """Generate Rodada-2 questions for openings the policy routed to
    ``decision=='ask'``. Stage 1: questions are written to disk only,
    no answers.json produced (Stage 2 will). Each question is
    structured so a future CLI can present it without further inference.
    """
    questions: list[dict] = []
    for amb in report.get("ambiguities") or []:
        oid = amb["opening_id"]
        evidence = amb.get("evidence") or {}
        candidates = amb.get("candidates") or []
        options = [
            {"id": chr(ord("a") + i), "label": c["kind"],
             "prob": c.get("prob")}
            for i, c in enumerate(candidates[:4])
        ]
        options.append({"id": "x", "label": "drop_this_opening",
                         "prob": None})
        questions.append({
            "id": f"q-{oid}",
            "subject": "opening",
            "subject_id": oid,
            "evidence": evidence,
            "confidence": amb.get("confidence"),
            "question": (
                f"Opening {oid} between "
                f"{evidence.get('room_left','?')} and "
                f"{evidence.get('room_right','?')}, width "
                f"{evidence.get('width_m','?')}m. "
                f"Top hypothesis confidence is "
                f"{amb.get('confidence', 0):.2f} — confirm a "
                f"classification?"
            ),
            "options": options,
            "default_if_unanswered": "debug",
        })
    return {
        "schema_version": QUESTIONS_SCHEMA_VERSION,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "consensus_path": report["consensus_path"],
        "consensus_sha256": report["consensus_sha256"],
        "questions": questions,
    }


# ---- Strict-mode evaluation ----

def evaluate_strict(report: dict, assumptions: Assumptions) -> list[str]:
    """Return a list of strict_blocker labels that fired. Empty list
    = no blockers. Caller decides exit code."""
    blockers = set(assumptions.strict_blockers or [])
    fired: list[str] = []
    if "opening_decision_ask" in blockers and report["ambiguities"]:
        fired.append("opening_decision_ask")
    if "opening_decision_drop" in blockers and report["drops"]:
        fired.append("opening_decision_drop")
    if ("floating_door" in blockers
            and report["issues"]["floating_doors"]):
        fired.append("floating_door")
    if ("opening_without_host_wall" in blockers
            and report["issues"]["floating_doors"]):
        fired.append("opening_without_host_wall")
    if ("invalid_room_polygon" in blockers
            and report["issues"]["invalid_rooms"]):
        fired.append("invalid_room_polygon")
    if ("duplicate_or_overlap_walls" in blockers
            and report["issues"]["duplicate_walls"]):
        fired.append("duplicate_or_overlap_walls")
    return fired


# ---- CLI ----

def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Stage-1 coherence audit: emit "
                    "coherence_report.json + questions.json from a "
                    "classified consensus. Non-blocking by default."
    )
    p.add_argument("consensus", type=Path,
                    help="path to consensus_with_room_context.json "
                         "(post-classifier)")
    p.add_argument("--assumptions", type=Path,
                    default=DEFAULT_ASSUMPTIONS_PATH,
                    help="config/assumptions.yaml (default: repo root)")
    p.add_argument("--out-dir", type=Path, default=None,
                    help="dir to write report + questions "
                         "(default: same dir as consensus)")
    p.add_argument("--strict", action="store_true",
                    help="exit with non-zero status if any "
                         "strict_blocker condition is present in the "
                         "report (default: always exit 0)")
    args = p.parse_args(argv)

    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))
    assumptions = load_assumptions(args.assumptions)
    report = build_coherence_report(consensus, args.consensus, assumptions)
    questions = build_questions(consensus, report)

    out_dir = args.out_dir or args.consensus.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "coherence_report.json"
    questions_path = out_dir / "questions.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    questions_path.write_text(
        json.dumps(questions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    summary = report["summary"]
    print(
        f"[coherence-audit] openings={summary['openings_total']} "
        f"by_decision={summary['by_decision']}"
    )
    print(f"[wrote] {report_path}")
    print(f"[wrote] {questions_path}")

    fired = evaluate_strict(report, assumptions)
    if args.strict and fired:
        print(f"[strict] blockers fired: {fired}", file=sys.stderr)
        return 2
    if fired:
        print(f"[non-strict] would-block: {fired}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
