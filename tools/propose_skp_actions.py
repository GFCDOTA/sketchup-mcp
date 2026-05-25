"""Propose advisory actions from a consensus + (optional) fidelity report.

Per ADR-001 §2.6 — emits ``proposed_actions_v1`` JSON. Actions are
**advisory only**: nothing in the pipeline reads them automatically.
They surface in the cockpit Review tab as suggestion chips next to
the affected element. The human (or a future Slice 4 wiring) decides
whether to apply each.

# Detection rules (v1)

For each opening in the consensus:

1. **mark_low_confidence** when ``opening.confidence`` is below
   :data:`LOW_CONFIDENCE_THRESHOLD` (0.7). The cockpit can use this
   to highlight the opening with a faint border.
2. **request_human_review** when ``opening.decision != "clean"``
   (i.e. the classifier put it in the "debug" bin). Reason code
   ``decision_not_clean``.
3. **classify_opening** when ``opening.kind_v5 == "unknown"``. The
   suggested kind defaults to ``"interior_passage"`` because that
   is the most common observed kind across the synth + planta_74
   corpora; the rationale records "kind_unknown_default" so a
   reviewer knows where the suggestion came from.

For each room (only when fidelity_report is supplied):

4. **request_human_review** when the room's name appears in any
   fidelity warning. Reason code ``fidelity_warning``.

# Idempotence

Each action's ``id`` is a SHA-256-derived UUIDv5 over the tuple
``(generator, type, target.kind, target.id, payload_canonical_json)``.
Re-running on byte-identical input produces byte-identical output —
no proliferation of duplicate suggestions.

The wrapping document's ``generated_at`` is **NOT** part of the
idempotence key; it always reflects the latest run, but the
individual action ids are stable.

# CLI

::

    python -m tools.propose_skp_actions \\
        --consensus runs/<run_id>/consensus_with_room_context.json \\
        [--fidelity runs/<run_id>/fidelity_report.json] \\
        [--output runs/<run_id>/proposed_actions.json]

Or auto-discover from a run directory::

    python -m tools.propose_skp_actions --run-dir runs/<run_id>

When ``--output`` is omitted, the file is written next to the
consensus as ``proposed_actions.json``.

# Boundary

This tool is **read-only** with respect to consensus and fidelity
inputs. It only writes ``proposed_actions.json``. It never touches
``review_overrides.json`` (that's the human's authoritative voice
per ADR-001 §2.1) and it never modifies the consensus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Public schema constants -----------------------------------------------

PROPOSED_ACTIONS_SCHEMA_VERSION: str = "proposed_actions_v1"
GENERATOR_NAME: str = "tools/propose_skp_actions.py@v0.1"

LOW_CONFIDENCE_THRESHOLD: float = 0.7

# PDF-points to metres conversion. Mirrors the canonical anchor in
# `cockpit/overrides.py:PT_TO_M` (kept local here so this tool has no
# cockpit import dependency — UI boundary, per ADR-001 §2.9).
PT_TO_M: float = 0.19 / 5.4

# Slice 6b — confidence of the polygon-correction chip. Always
# <LOW_CONFIDENCE_THRESHOLD so the cockpit treats it as a draft
# suggestion (human must review/edit in the polygon text-area before
# the override is actually written).
POLYGON_CORRECTION_CONFIDENCE: float = 0.55

# Regex for the "ROOM NAME area <qualifier>: observed X.XX m^2 vs
# expected [LO, HI]" warning emitted by
# `tools/fidelity/compare_generated_to_expected.py` when a room's
# area falls outside the expected range. The Slice 6b producer rule
# parses these warnings to derive expand/shrink chip suggestions.
_AREA_WARNING_RE: re.Pattern[str] = re.compile(
    r"^(?P<name>.+?)\s+area\s+\S+:\s+observed\s+(?P<obs>[\d.]+)\s+m\^?2"
    r"\s+vs\s+expected\s+\[(?P<lo>[\d.]+)\s*,\s*(?P<hi>[\d.]+)\]",
    re.IGNORECASE,
)

# Mirror cockpit.overrides.OPENING_KIND_VALUES so we don't drift.
OPENING_KIND_VALUES: tuple[str, ...] = (
    "interior_door",
    "interior_passage",
    "window",
    "glazed_balcony",
    "exterior_door",
    "unknown",
)

ACTION_TYPES: tuple[str, ...] = (
    "classify_opening",
    "expand_room_polygon",
    "shrink_room_polygon",
    "relink_opening_rooms",
    "mark_low_confidence",
    "request_human_review",
)

# Stable v5 namespace so action ids are reproducible across machines.
# Picked once and frozen here per ADR-001 §2.6 idempotence note.
_NAMESPACE_PROPOSED_ACTIONS = uuid.UUID("3c5f8a64-9d76-5e4f-9b2c-1f0e7d6a4b3c")


# ---------- Pure helpers ----------------------------------------------

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _consensus_sha256(consensus_path: Path) -> str:
    raw = consensus_path.read_bytes()
    return hashlib.sha256(raw).hexdigest()


def _stable_action_id(*, action_type: str, target_kind: str,
                      target_id: str, payload: dict) -> str:
    """Deterministic id for an action so re-runs are byte-identical.

    Uses uuid5 over a canonical concatenation of the identity fields.
    payload is JSON-serialised with sorted keys for stability.
    """
    payload_canon = json.dumps(payload, sort_keys=True,
                                separators=(",", ":"))
    name = f"{GENERATOR_NAME}|{action_type}|{target_kind}|{target_id}|{payload_canon}"
    return str(uuid.uuid5(_NAMESPACE_PROPOSED_ACTIONS, name))


def _build_action(*, action_type: str, target_kind: str, target_id: str,
                   payload: dict, confidence: float, rationale: str,
                   created_at: str) -> dict:
    if action_type not in ACTION_TYPES:
        raise ValueError(
            f"unknown action_type {action_type!r}; "
            f"must be one of {ACTION_TYPES}"
        )
    if target_kind not in ("opening", "room"):
        raise ValueError(
            f"target_kind must be 'opening' or 'room', got {target_kind!r}"
        )
    return {
        "id": _stable_action_id(
            action_type=action_type, target_kind=target_kind,
            target_id=target_id, payload=payload,
        ),
        "type": action_type,
        "target": {"kind": target_kind, "id": target_id},
        "payload": payload,
        "confidence": round(float(confidence), 3),
        "rationale": rationale,
        "generator": GENERATOR_NAME,
        "created_at": created_at,
    }


# ---------- Detection rules -------------------------------------------

def _rule_mark_low_confidence(openings: list[dict],
                                created_at: str) -> list[dict]:
    """Rule 1 — flag openings with confidence < threshold."""
    out: list[dict] = []
    for op in openings:
        conf = op.get("confidence")
        if conf is None:
            continue
        try:
            cf = float(conf)
        except (TypeError, ValueError):
            continue
        if cf >= LOW_CONFIDENCE_THRESHOLD:
            continue
        oid = op.get("id")
        if not oid:
            continue
        out.append(_build_action(
            action_type="mark_low_confidence",
            target_kind="opening",
            target_id=str(oid),
            payload={"current_confidence": round(cf, 3)},
            confidence=1.0,  # the detection itself is certain
            rationale=(
                f"opening.confidence={cf:.3f} is below threshold "
                f"{LOW_CONFIDENCE_THRESHOLD}"
            ),
            created_at=created_at,
        ))
    return out


def _rule_request_review_on_debug_decision(openings: list[dict],
                                              created_at: str) -> list[dict]:
    """Rule 2 — flag openings whose decision is not 'clean'."""
    out: list[dict] = []
    for op in openings:
        decision = op.get("decision")
        if not decision or decision == "clean":
            continue
        oid = op.get("id")
        if not oid:
            continue
        out.append(_build_action(
            action_type="request_human_review",
            target_kind="opening",
            target_id=str(oid),
            payload={"reason_codes": ["decision_not_clean"]},
            confidence=1.0,
            rationale=(
                f"opening.decision={decision!r}; "
                "classifier flagged this as non-clean"
            ),
            created_at=created_at,
        ))
    return out


def _rule_classify_unknown_openings(openings: list[dict],
                                       created_at: str) -> list[dict]:
    """Rule 3 — propose a kind for openings with kind_v5=='unknown'.

    The suggested kind is `interior_passage` (most common observed
    kind in the corpus). Rationale records the heuristic so the
    human can override.
    """
    out: list[dict] = []
    for op in openings:
        kind = op.get("kind_v5") or op.get("kind")
        if kind != "unknown":
            continue
        oid = op.get("id")
        if not oid:
            continue
        ev = op.get("evidence") or {}
        evidence_pointers = sorted(
            k for k in ("room_left", "room_right", "width_m")
            if k in ev
        )
        out.append(_build_action(
            action_type="classify_opening",
            target_kind="opening",
            target_id=str(oid),
            payload={
                "suggested_kind": "interior_passage",
                "evidence": evidence_pointers,
            },
            confidence=0.4,  # heuristic default; not high-conviction
            rationale=(
                "kind_unknown_default; suggesting interior_passage as "
                "the most common observed kind across synth + planta_74 "
                "corpora. Reviewer should confirm with cockpit overlay."
            ),
            created_at=created_at,
        ))
    return out


# ---------- Polygon math helpers (Slice 6b) ---------------------------

def _polygon_area_pts2(pts: list[list[float]]) -> float:
    """Signed shoelace area, returned as absolute value (PDF-points²).

    Pure stdlib; works without shapely so this tool stays import-light.
    """
    n = len(pts)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x0, y0 = float(pts[i][0]), float(pts[i][1])
        x1, y1 = float(pts[(i + 1) % n][0]), float(pts[(i + 1) % n][1])
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


def _polygon_bbox(pts: list[list[float]]) -> tuple[float, float, float, float]:
    """Return (xmin, ymin, xmax, ymax). pts is assumed non-empty."""
    xs = [float(p[0]) for p in pts]
    ys = [float(p[1]) for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _polygon_centroid(pts: list[list[float]]) -> tuple[float, float]:
    """Geometric centroid (mean of vertices, ignores self-intersection).

    Good enough for the chip suggestion — the human reviews/edits the
    result in the cockpit text-area before save.
    """
    if not pts:
        return (0.0, 0.0)
    sx = sum(float(p[0]) for p in pts)
    sy = sum(float(p[1]) for p in pts)
    n = len(pts)
    return (sx / n, sy / n)


def _scale_polygon_around_centroid(
    pts: list[list[float]], scale: float,
) -> list[list[float]]:
    """Uniform scale about the polygon's centroid.

    scale > 1 expands, scale < 1 shrinks. Result is a new list (does
    not mutate input).
    """
    cx, cy = _polygon_centroid(pts)
    return [
        [cx + (float(p[0]) - cx) * scale, cy + (float(p[1]) - cy) * scale]
        for p in pts
    ]


def _bbox_delta_pts(orig: list[list[float]],
                     scaled: list[list[float]]) -> list[float]:
    """Return [left_dx, bottom_dy, right_dx, top_dy] — how each bbox
    corner moves from `orig` to `scaled`. Positive on the right/top
    means the corner shifted outward.

    Provided alongside `suggested_polygon_pts` in the chip payload so
    the cockpit can render a one-line summary ("expand by ~Xpts on
    each side") without re-computing the math.
    """
    if not orig or not scaled:
        return [0.0, 0.0, 0.0, 0.0]
    ox0, oy0, ox1, oy1 = _polygon_bbox(orig)
    sx0, sy0, sx1, sy1 = _polygon_bbox(scaled)
    return [
        round(sx0 - ox0, 3),  # left edge delta (negative = expanded)
        round(sy0 - oy0, 3),  # bottom edge delta
        round(sx1 - ox1, 3),  # right edge delta (positive = expanded)
        round(sy1 - oy1, 3),  # top edge delta
    ]


def _rule_polygon_correction(
    rooms: list[dict],
    fidelity_report: dict | None,
    created_at: str,
) -> list[dict]:
    """Rule 5 (Slice 6b / ADR-002 §4) — when fidelity_report warns
    that a room's area is outside its expected range, emit a draft
    chip suggesting an expand/shrink polygon override.

    Reads the warning text directly (e.g. ``"TERRACO TECNICO area
    marginal: observed 1.61 m^2 vs expected [2.0, 8.0]"``) — does not
    require an `expected_model` companion file. The cockpit MUST treat
    this as a draft suggestion: the human reviews and edits the
    suggested polygon in the polygon text-area before
    :func:`cockpit.overrides.save_override` is invoked.

    Idempotence: action id derives from (type, target, payload) per
    :func:`_stable_action_id`. Repeated runs on byte-identical warning
    text produce byte-identical chip ids.
    """
    if not fidelity_report:
        return []
    warnings = fidelity_report.get("warnings") or []
    if not warnings:
        return []
    out: list[dict] = []
    seen_room_ids: set[str] = set()
    rooms_by_upper_name: dict[str, dict] = {}
    for room in rooms:
        nm = (room.get("name") or "").strip().upper()
        rid = room.get("id")
        if not nm or not rid:
            continue
        rooms_by_upper_name.setdefault(nm, room)
    for w in warnings:
        if not isinstance(w, str):
            continue
        m = _AREA_WARNING_RE.search(w)
        if not m:
            continue
        warning_name = m.group("name").strip().upper()
        try:
            observed_m2 = float(m.group("obs"))
            expected_lo = float(m.group("lo"))
            expected_hi = float(m.group("hi"))
        except (TypeError, ValueError):
            continue
        if observed_m2 <= 0 or expected_lo <= 0 or expected_hi <= expected_lo:
            # Malformed warning — skip rather than emit a degenerate chip.
            continue
        # Strict name match. Substring match would over-fire on e.g.
        # "SUITE 01" matching a warning about "SUITE 02".
        room = rooms_by_upper_name.get(warning_name)
        if room is None:
            continue
        rid = str(room.get("id"))
        if rid in seen_room_ids:
            continue
        polygon_pts = room.get("polygon_pts") or []
        if len(polygon_pts) < 3:
            continue
        # Decide direction + target area
        if observed_m2 < expected_lo:
            action_type = "expand_room_polygon"
            target_m2 = expected_lo  # conservative — just touch the low edge
        elif observed_m2 > expected_hi:
            action_type = "shrink_room_polygon"
            target_m2 = expected_hi  # conservative — just touch the high edge
        else:
            # In range — nothing to suggest.
            continue
        # Uniform scale around centroid. Linear factor = sqrt(area_ratio).
        scale_factor = (target_m2 / observed_m2) ** 0.5
        suggested = _scale_polygon_around_centroid(polygon_pts, scale_factor)
        suggested_rounded = [
            [round(x, 3), round(y, 3)] for x, y in suggested
        ]
        bbox_delta = _bbox_delta_pts(polygon_pts, suggested_rounded)
        # Recompute area on the rounded polygon so the chip's
        # estimated_area_* fields match what the cockpit will see.
        est_area_pts2 = _polygon_area_pts2(suggested_rounded)
        est_area_m2 = est_area_pts2 * (PT_TO_M ** 2)
        seen_room_ids.add(rid)
        out.append(_build_action(
            action_type=action_type,
            target_kind="room",
            target_id=rid,
            payload={
                "current_area_m2": round(observed_m2, 3),
                "target_area_m2": round(target_m2, 3),
                "expected_range_m2": [
                    round(expected_lo, 3), round(expected_hi, 3),
                ],
                "scale_factor": round(scale_factor, 4),
                "delta_pts": bbox_delta,
                "suggested_polygon_pts": suggested_rounded,
                "estimated_area_pts2": round(est_area_pts2, 3),
                "estimated_area_m2": round(est_area_m2, 4),
                "warning_text": w[:200],
            },
            confidence=POLYGON_CORRECTION_CONFIDENCE,
            rationale=(
                f"room {warning_name!r} observed area {observed_m2:.2f} m² is "
                f"outside expected [{expected_lo:.2f}, {expected_hi:.2f}] m²; "
                f"chip suggests uniform-centroid scale by {scale_factor:.3f} "
                f"toward {target_m2:.2f} m². Human must review/edit the "
                "polygon in the cockpit text-area before save (ADR-002 §2.4 "
                "soft warnings apply)."
            ),
            created_at=created_at,
        ))
    return out


def _rule_review_rooms_in_fidelity_warnings(rooms: list[dict],
                                              fidelity_report: dict | None,
                                              created_at: str) -> list[dict]:
    """Rule 4 — flag rooms whose name appears in any fidelity warning."""
    if not fidelity_report:
        return []
    warnings = fidelity_report.get("warnings") or []
    if not warnings:
        return []
    out: list[dict] = []
    seen_room_ids: set[str] = set()
    for room in rooms:
        name = (room.get("name") or "").strip()
        rid = room.get("id")
        if not name or not rid or rid in seen_room_ids:
            continue
        # Match the room name (uppercased) appearing in any warning string.
        upper_name = name.upper()
        matching: list[str] = [
            w for w in warnings if isinstance(w, str)
            and upper_name in w.upper()
        ]
        if not matching:
            continue
        seen_room_ids.add(str(rid))
        out.append(_build_action(
            action_type="request_human_review",
            target_kind="room",
            target_id=str(rid),
            payload={
                "reason_codes": ["fidelity_warning"],
                "warning_count": len(matching),
            },
            confidence=0.85,
            rationale=(
                f"room {name!r} matched {len(matching)} fidelity warning(s); "
                "first match: " + (matching[0][:120] if matching else "")
            ),
            created_at=created_at,
        ))
    return out


# ---------- Public API ------------------------------------------------

def propose_actions(*, consensus: dict,
                    fidelity_report: dict | None = None,
                    consensus_sha256: str | None = None,
                    run_id: str | None = None,
                    generated_at: str | None = None) -> dict:
    """Pure function: build the ``proposed_actions_v1`` document.

    Parameters
    ----------
    consensus
        Loaded consensus dict (post-classifier ``c3`` shape).
    fidelity_report
        Optional loaded fidelity_report dict. When supplied, rule 4
        (room-in-warning) fires.
    consensus_sha256
        Hex sha256 of the source consensus file. Caller may compute
        it via :func:`_consensus_sha256` (or any other equivalent).
    run_id
        Stable identifier for the run. Defaults to ``"<unknown>"``
        when missing.
    generated_at
        ISO8601 UTC timestamp. Defaults to the current UTC time.

    Returns
    -------
    dict
        The full ``proposed_actions_v1`` document, ready to be JSON-
        serialised and written to ``runs/<run_id>/proposed_actions.json``.
    """
    created_at = generated_at or _utc_now_iso()
    openings = consensus.get("openings") or []
    rooms = consensus.get("rooms") or []

    actions: list[dict] = []
    actions.extend(_rule_mark_low_confidence(openings, created_at))
    actions.extend(_rule_request_review_on_debug_decision(
        openings, created_at,
    ))
    actions.extend(_rule_classify_unknown_openings(openings, created_at))
    actions.extend(_rule_review_rooms_in_fidelity_warnings(
        rooms, fidelity_report, created_at,
    ))
    # Rule 5 (Slice 6b) — polygon-correction draft chips from
    # area-out-of-range fidelity warnings. Always advisory; chips are
    # not promoted into overrides until the human edits + saves in the
    # cockpit polygon text-area.
    actions.extend(_rule_polygon_correction(
        rooms, fidelity_report, created_at,
    ))

    # Sort by (type, target.kind, target.id) for byte-stable output.
    actions.sort(key=lambda a: (
        a["type"], a["target"]["kind"], a["target"]["id"],
    ))

    return {
        "schema_version": PROPOSED_ACTIONS_SCHEMA_VERSION,
        "run_id": run_id or "<unknown>",
        "consensus_sha256": consensus_sha256 or "<not_provided>",
        "generated_at": created_at,
        "generator": GENERATOR_NAME,
        "actions": actions,
    }


def write_proposed_actions(doc: dict, output_path: Path) -> Path:
    """Atomic write — temp file + rename so partial writes can't
    corrupt readers."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(output_path)
    return output_path


# ---------- CLI -------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="propose_skp_actions",
        description=(
            "Emit advisory proposed_actions_v1 JSON from a consensus "
            "(+ optional fidelity_report) per ADR-001 §2.6. "
            "Actions are advisory; nothing in the pipeline applies "
            "them automatically."
        ),
    )
    p.add_argument(
        "--run-dir", type=Path, default=None,
        help=(
            "Directory containing consensus_*.json + (optional) "
            "fidelity_report.json. Auto-discovers paths and writes "
            "proposed_actions.json into the same dir."
        ),
    )
    p.add_argument(
        "--consensus", type=Path, default=None,
        help="Explicit consensus JSON path. Overrides --run-dir.",
    )
    p.add_argument(
        "--fidelity", type=Path, default=None,
        help="Optional explicit fidelity_report.json path.",
    )
    p.add_argument(
        "--output", type=Path, default=None,
        help=(
            "Output path. Defaults to <consensus_dir>/proposed_actions.json"
        ),
    )
    p.add_argument(
        "--run-id", type=str, default=None,
        help=(
            "Run id stamped in the document. Defaults to the consensus "
            "directory name."
        ),
    )
    return p


def _autodiscover_consensus(run_dir: Path) -> Path | None:
    """Pick the first consensus_*.json under ``run_dir``."""
    candidates = sorted(run_dir.glob("consensus_*.json"))
    if not candidates:
        # Fallback: any .json with rooms+walls top-level keys
        for p in sorted(run_dir.glob("*.json")):
            try:
                head = p.read_text(encoding="utf-8")[:2048]
            except OSError:
                continue
            if '"rooms"' in head and '"walls"' in head:
                return p
        return None
    return candidates[0]


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.consensus is None and args.run_dir is None:
        print(
            "error: provide --consensus or --run-dir",
            file=sys.stderr,
        )
        return 2
    consensus_path: Path
    if args.consensus is not None:
        consensus_path = args.consensus
    else:
        discovered = _autodiscover_consensus(args.run_dir)
        if discovered is None:
            print(
                f"error: no consensus_*.json found under {args.run_dir}",
                file=sys.stderr,
            )
            return 2
        consensus_path = discovered
    if not consensus_path.exists():
        print(
            f"error: consensus path not found: {consensus_path}",
            file=sys.stderr,
        )
        return 2
    fidelity_path = args.fidelity
    if fidelity_path is None and args.run_dir is not None:
        candidate = args.run_dir / "fidelity_report.json"
        if candidate.exists():
            fidelity_path = candidate
    output_path = args.output
    if output_path is None:
        output_path = consensus_path.parent / "proposed_actions.json"
    run_id = args.run_id or consensus_path.parent.name

    consensus = json.loads(consensus_path.read_text(encoding="utf-8"))
    fidelity_report: dict | None = None
    if fidelity_path is not None and fidelity_path.exists():
        fidelity_report = json.loads(
            fidelity_path.read_text(encoding="utf-8"),
        )

    doc = propose_actions(
        consensus=consensus,
        fidelity_report=fidelity_report,
        consensus_sha256=_consensus_sha256(consensus_path),
        run_id=run_id,
    )
    write_proposed_actions(doc, output_path)
    print(
        f"wrote {output_path} "
        f"({len(doc['actions'])} action{'s' if len(doc['actions']) != 1 else ''}; "
        f"run_id={run_id})"
    )
    return 0


@dataclass
class _Sentinel:
    """Marker re-exported for tests that need to assert on
    presence of a sentinel default value."""
    name: str = "default"


__all__ = [
    "ACTION_TYPES",
    "GENERATOR_NAME",
    "LOW_CONFIDENCE_THRESHOLD",
    "OPENING_KIND_VALUES",
    "POLYGON_CORRECTION_CONFIDENCE",
    "PROPOSED_ACTIONS_SCHEMA_VERSION",
    "PT_TO_M",
    "main",
    "propose_actions",
    "write_proposed_actions",
]


if __name__ == "__main__":
    sys.exit(main())
