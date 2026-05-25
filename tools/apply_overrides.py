"""apply_overrides.py — Slice 3 of the Validation Cockpit Mutation Surface.

Pure function + thin CLI shell that consumes a ``review_overrides.json``
document (schema ``review_overrides_v1`` per ADR-001 §2.3) plus the
source consensus JSON and emits an ``amended_observed.json`` artefact
(schema ``amended_observed_v1`` per ADR-001 §2.10.4) — the consensus
shape with per-element ``source`` attribution + ``_<field>_original``
preservation for any field changed by an override.

Boundary (ADR-001 §2.10):
- Originals are immutable: this script NEVER edits the consensus in
  place — it produces a new dict.
- Overrides are a layer: every changed field carries
  ``_<field>_original`` so the raw detector output is recoverable.
- Source attribution is mandatory: every room / opening in the output
  carries ``source`` ∈ ``{detected, manual, override_rejected}``.
- Consensus SHA-256 binds overrides: a stale-binding override doc
  is REJECTED whole — no overrides are applied — and a metadata
  warning is emitted.
- The detector pipeline NEVER reads overrides — this script is
  strictly above the detector.

Precedence (ADR-001 §2.5): for the same target,
``reject_element`` > ``mark_suspect`` > kind/connect/label
> ``approve_element`` > nothing. Within the same precedence level,
last ``created_at`` wins.

Usage::

    python -m tools.apply_overrides \\
        --consensus runs/<run_id>/consensus_with_room_context.json \\
        --overrides runs/<run_id>/review_overrides.json \\
        --output runs/<run_id>/amended_observed.json

The ``--overrides`` argument is optional: when omitted (or pointed at
a non-existent file), the output is a deep-copy of the consensus with
every element tagged ``source: detected``.
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

AMENDED_SCHEMA_VERSION = "amended_observed_v1"
OVERRIDES_SCHEMA_VERSION = "review_overrides_v1"

# Mirrors tools/classify_openings_by_room_context.py (ADR-001 §2.5).
VALID_OPENING_KINDS = {
    "interior_door",
    "interior_passage",
    "window",
    "glazed_balcony",
    "exterior_door",
    "unknown",
}

VALID_SUSPECT_SEVERITIES = {"low", "medium", "high"}

# Precedence ranks for ADR-001 §2.5 + ADR-002. Higher rank wins.
# ``room_polygon_override`` shares rank 2 with the other element-shape
# overrides because they touch DISJOINT fields on the same room
# (polygon vs name) and both are meant to apply, in created_at order.
_PRECEDENCE: dict[str, int] = {
    "reject_element": 4,
    "mark_suspect": 3,
    "opening_kind_override": 2,
    "opening_connects_override": 2,
    "room_label_override": 2,
    "room_polygon_override": 2,  # ADR-002
    "approve_element": 1,
}

VALID_POLYGON_EDIT_METHODS = {
    "manual_draw",
    "snap_to_walls",
    "trace_pdf",
    "from_proposed_action",
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _consensus_sha256(consensus: dict) -> str:
    """Compute a deterministic sha256 of a consensus dict.

    Uses ``json.dumps(..., sort_keys=True, separators=...)`` so the
    same dict produces the same hash regardless of key insertion
    order. This matches what the cockpit (Slice 2) records when it
    writes the override file.
    """
    encoded = json.dumps(
        consensus, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _index_by_id(items: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for it in items or []:
        eid = it.get("id")
        if eid:
            out[eid] = it
    return out


def _validate_override_payload(override: dict, consensus: dict) -> str | None:
    """Return None when valid, else a string describing the violation.

    Validation rules per ADR-001 §2.5. Any failure means the override
    is silently dropped from the apply set (recorded in metadata).
    """
    target = override.get("target") or {}
    kind = target.get("kind")
    tid = target.get("id")
    otype = override.get("type")
    if otype == "block_skp_export":
        # Top-level only; nothing to validate at element level.
        return None
    if kind not in {"opening", "room"}:
        return f"target.kind {kind!r} not in {{opening, room}}"
    if not isinstance(tid, str) or not tid:
        return f"target.id {tid!r} must be non-empty string"
    bucket = "openings" if kind == "opening" else "rooms"
    if tid not in _index_by_id(consensus.get(bucket) or []):
        return f"target.id {tid!r} not found in consensus.{bucket}"
    payload = override.get("payload") or {}
    if otype == "opening_kind_override":
        new_kind = payload.get("new_kind_v5")
        if new_kind not in VALID_OPENING_KINDS:
            return f"new_kind_v5 {new_kind!r} not in valid set"
    elif otype == "opening_connects_override":
        room_ids = {r.get("id") for r in (consensus.get("rooms") or [])}
        for fld in ("room_left_id", "room_right_id"):
            v = payload.get(fld)
            if v is not None and v not in room_ids:
                return f"{fld}={v!r} not found in consensus.rooms"
    elif otype == "mark_suspect":
        sev = payload.get("severity")
        if sev not in VALID_SUSPECT_SEVERITIES:
            return f"mark_suspect.severity {sev!r} not in {VALID_SUSPECT_SEVERITIES}"
    elif otype == "room_label_override":
        new_name = payload.get("new_name")
        if not isinstance(new_name, str) or not new_name.strip():
            return "room_label_override.new_name must be non-empty string"
    elif otype == "room_polygon_override":
        # ADR-002 §2.4 — hard validation only. Soft checks are the
        # cockpit's responsibility (cockpit/overrides.py:validate_override_warnings).
        if kind != "room":
            return "room_polygon_override target.kind must be 'room'"
        edit_method = payload.get("edit_method")
        if edit_method not in VALID_POLYGON_EDIT_METHODS:
            return (
                f"room_polygon_override.edit_method {edit_method!r} "
                f"not in {sorted(VALID_POLYGON_EDIT_METHODS)}"
            )
        pts = payload.get("new_polygon_pts")
        if not isinstance(pts, list) or len(pts) < 3:
            return ("room_polygon_override.new_polygon_pts must be a "
                    "list of >=3 [x,y] pairs")
        for pt in pts:
            if (not isinstance(pt, (list, tuple))
                    or len(pt) != 2
                    or not isinstance(pt[0], (int, float))
                    or not isinstance(pt[1], (int, float))):
                return ("room_polygon_override.new_polygon_pts entries "
                        "must be [x,y] pairs of numbers")
        area_pts2 = payload.get("estimated_area_pts2")
        area_m2 = payload.get("estimated_area_m2")
        if not isinstance(area_pts2, (int, float)) or area_pts2 <= 0:
            return ("room_polygon_override.estimated_area_pts2 must be "
                    "a positive number")
        if not isinstance(area_m2, (int, float)) or area_m2 <= 0:
            return ("room_polygon_override.estimated_area_m2 must be "
                    "a positive number")
    return None


def _resolve_active_overrides(
    overrides: list[dict],
) -> dict[tuple[str, str], list[dict]]:
    """Group valid overrides by target and resolve precedence.

    Returns a dict keyed by ``(kind, id)`` whose value is the list of
    overrides that should actually apply, ordered by precedence (lowest
    first) so iteration applies them in dependency order. Within the
    same precedence rank, ``created_at`` ascending so "last wins" for
    field replacements but order is deterministic.
    """
    by_target: dict[tuple[str, str], list[dict]] = {}
    for ov in overrides:
        target = ov.get("target") or {}
        if ov.get("type") == "block_skp_export":
            continue
        key = (target.get("kind") or "", target.get("id") or "")
        if not key[0] or not key[1]:
            continue
        by_target.setdefault(key, []).append(ov)

    resolved: dict[tuple[str, str], list[dict]] = {}
    for key, ovs in by_target.items():
        # Stable sort by (precedence, created_at) ascending. Apply
        # order: low precedence first, high precedence last (so a
        # later reject overrides an earlier kind change).
        def _sort_key(o: dict) -> tuple:
            rank = _PRECEDENCE.get(o.get("type") or "", 0)
            return (rank, o.get("created_at") or "")

        ovs_sorted = sorted(ovs, key=_sort_key)
        # Reject_element trumps everything: if any reject is present,
        # only the last reject (by created_at) is the active one. ADR
        # says reject is dominant; other overrides on the same
        # element are still recorded in audit but don't apply.
        rejects = [o for o in ovs_sorted if o.get("type") == "reject_element"]
        if rejects:
            resolved[key] = [rejects[-1]]
            continue
        # mark_suspect dominates non-reject: keep all kind/connect/
        # label/approve overrides AND the suspect tag (the suspect
        # tag is additive — it doesn't replace fields).
        resolved[key] = ovs_sorted
    return resolved


def _apply_to_opening(opening: dict, override: dict) -> None:
    """Mutate ``opening`` in place per the override.

    Caller is responsible for having deep-copied the source consensus;
    this function mutates the working copy.
    """
    otype = override.get("type")
    payload = override.get("payload") or {}
    if otype == "opening_kind_override":
        new_kind = payload.get("new_kind_v5")
        if "kind_v5" in opening and "_kind_v5_original" not in opening:
            opening["_kind_v5_original"] = opening.get("kind_v5")
        opening["kind_v5"] = new_kind
        opening["source"] = "manual"
    elif otype == "opening_connects_override":
        for fld in ("room_left_id", "room_right_id"):
            new_v = payload.get(fld)
            if new_v is None:
                continue
            orig_key = f"_{fld}_original"
            if fld in opening and orig_key not in opening:
                opening[orig_key] = opening.get(fld)
            opening[fld] = new_v
        opening["source"] = "manual"
    elif otype == "mark_suspect":
        opening["_suspect"] = {
            "severity": payload.get("severity"),
            "tag": payload.get("tag"),
        }
    elif otype == "approve_element":
        opening["_approved"] = True
        opening["source"] = "manual"


def _apply_to_room(room: dict, override: dict) -> None:
    """Mutate ``room`` in place per the override."""
    otype = override.get("type")
    payload = override.get("payload") or {}
    if otype == "room_label_override":
        new_name = payload.get("new_name")
        if "name" in room and "_name_original" not in room:
            room["_name_original"] = room.get("name")
        room["name"] = new_name
        room["source"] = "manual"
    elif otype == "room_polygon_override":
        # ADR-002 §2.5 — preserve originals, replace geometry, surface
        # `_edit_method` and optional `_source_proposed_action_id`.
        if "polygon_pts" in room and "_polygon_pts_original" not in room:
            room["_polygon_pts_original"] = room.get("polygon_pts")
        if "area_pts2" in room and "_area_pts2_original" not in room:
            room["_area_pts2_original"] = room.get("area_pts2")
        if "area_m2" in room and "_area_m2_original" not in room:
            room["_area_m2_original"] = room.get("area_m2")
        room["polygon_pts"] = list(payload.get("new_polygon_pts") or [])
        room["area_pts2"] = float(payload.get("estimated_area_pts2") or 0.0)
        room["area_m2"] = float(payload.get("estimated_area_m2") or 0.0)
        room["source"] = "manual"
        room["_edit_method"] = payload.get("edit_method")
        fpa_id = payload.get("from_proposed_action_id")
        if fpa_id:
            room["_source_proposed_action_id"] = fpa_id
    elif otype == "mark_suspect":
        room["_suspect"] = {
            "severity": payload.get("severity"),
            "tag": payload.get("tag"),
        }
    elif otype == "approve_element":
        room["_approved"] = True
        room["source"] = "manual"


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def apply_overrides(
    consensus: dict,
    overrides_doc: dict | None,
    *,
    expected_sha: str | None = None,
) -> dict:
    """Return amended_observed dict per ADR-001 §2.10.4.

    Parameters
    ----------
    consensus
        The source consensus dict (typically loaded from
        ``consensus_with_room_context.json``). Not mutated.
    overrides_doc
        The ``review_overrides_v1`` document. ``None`` or an empty
        ``overrides`` list means: identity copy of consensus, every
        element tagged ``source: detected``.
    expected_sha
        Optional sha256 of the consensus the overrides were written
        against. When supplied AND it doesn't match
        ``overrides_doc["consensus_sha256"]``, NO overrides are
        applied and a warning is recorded in
        ``_overrides_metadata.warnings``. When ``None`` (default),
        the script trusts the override file's sha and skips the
        binding check.
    """
    amended = copy.deepcopy(consensus)
    metadata: dict[str, Any] = {
        "schema_version": AMENDED_SCHEMA_VERSION,
        "applied_at": _utc_now(),
        "overrides_applied_count": 0,
        "overrides_dropped_count": 0,
        "polygon_overrides_applied_count": 0,  # ADR-002 §2.6
        "warnings": [],
        "block_skp_export": False,
        "block_reason": None,
    }

    # Tag everything with source=detected before any override touches it.
    for op in amended.get("openings") or []:
        op.setdefault("source", "detected")
    for room in amended.get("rooms") or []:
        room.setdefault("source", "detected")

    if not overrides_doc:
        amended["_overrides_metadata"] = metadata
        amended["_overrides_applied"] = 0
        return amended

    schema_version = overrides_doc.get("schema_version")
    if schema_version != OVERRIDES_SCHEMA_VERSION:
        metadata["warnings"].append(
            f"overrides schema_version={schema_version!r} != "
            f"{OVERRIDES_SCHEMA_VERSION!r}; ignoring all overrides",
        )
        amended["_overrides_metadata"] = metadata
        amended["_overrides_applied"] = 0
        return amended

    if expected_sha is not None:
        bound_sha = overrides_doc.get("consensus_sha256")
        if bound_sha and bound_sha != expected_sha:
            metadata["warnings"].append(
                f"consensus_sha256 mismatch: overrides bound to "
                f"{bound_sha[:12]}..., live consensus is "
                f"{expected_sha[:12]}...; rejecting all overrides "
                f"(ADR-001 §2.10.6)",
            )
            metadata["sha_mismatch"] = True
            amended["_overrides_metadata"] = metadata
            amended["_overrides_applied"] = 0
            return amended

    overrides = list(overrides_doc.get("overrides") or [])
    valid: list[dict] = []
    for ov in overrides:
        if ov.get("type") == "block_skp_export":
            valid.append(ov)
            continue
        why = _validate_override_payload(ov, consensus)
        if why is None:
            valid.append(ov)
        else:
            metadata["overrides_dropped_count"] += 1
            metadata["warnings"].append(
                f"dropped override {ov.get('id', '?')}: {why}"
            )

    # block_skp_export from `global` block (top-level) takes priority,
    # but ADR-001 §2.5 also lists it as an override type for the audit
    # trail — accept both. The latest sets the verdict.
    global_block = (overrides_doc.get("global") or {}).get(
        "block_skp_export"
    )
    if global_block:
        metadata["block_skp_export"] = True
        metadata["block_reason"] = (
            (overrides_doc.get("global") or {}).get("block_reason")
        )
    for ov in valid:
        if ov.get("type") == "block_skp_export":
            metadata["block_skp_export"] = True
            metadata["block_reason"] = (
                (ov.get("payload") or {}).get("reason")
            )

    resolved = _resolve_active_overrides(valid)

    rooms_idx = _index_by_id(amended.get("rooms") or [])
    openings_idx = _index_by_id(amended.get("openings") or [])

    rejected_room_ids: set[str] = set()
    rejected_opening_ids: set[str] = set()
    applied_count = 0

    for (kind, tid), ovs in resolved.items():
        target_dict = (
            openings_idx if kind == "opening" else rooms_idx
        ).get(tid)
        if target_dict is None:
            metadata["overrides_dropped_count"] += 1
            metadata["warnings"].append(
                f"target ({kind}, {tid}) missing at apply time"
            )
            continue
        for ov in ovs:
            otype = ov.get("type")
            if otype == "reject_element":
                if kind == "opening":
                    rejected_opening_ids.add(tid)
                else:
                    rejected_room_ids.add(tid)
                target_dict["source"] = "override_rejected"
                applied_count += 1
                continue
            if kind == "opening":
                _apply_to_opening(target_dict, ov)
            else:
                _apply_to_room(target_dict, ov)
            if otype == "room_polygon_override":
                metadata["polygon_overrides_applied_count"] += 1
            applied_count += 1

    if rejected_opening_ids:
        amended["openings"] = [
            o for o in (amended.get("openings") or [])
            if o.get("id") not in rejected_opening_ids
        ]
    if rejected_room_ids:
        amended["rooms"] = [
            r for r in (amended.get("rooms") or [])
            if r.get("id") not in rejected_room_ids
        ]

    metadata["overrides_applied_count"] = applied_count
    metadata["rejected_opening_ids"] = sorted(rejected_opening_ids)
    metadata["rejected_room_ids"] = sorted(rejected_room_ids)
    amended["_overrides_metadata"] = metadata
    amended["_overrides_applied"] = applied_count
    return amended


# ---------------------------------------------------------------------------
# CLI shell
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="apply_overrides",
        description=(
            "Apply review_overrides.json (ADR-001 §2.3) to a consensus "
            "JSON, producing amended_observed.json. Non-mutating: the "
            "source consensus is never modified."
        ),
    )
    ap.add_argument(
        "--consensus", type=Path, required=True,
        help="path to the source consensus JSON",
    )
    ap.add_argument(
        "--overrides", type=Path, default=None,
        help=(
            "path to review_overrides.json. Optional — when omitted "
            "or absent, the output is an identity copy with "
            "source: detected on every element."
        ),
    )
    ap.add_argument(
        "--output", type=Path, required=True,
        help="output path for amended_observed.json",
    )
    ap.add_argument(
        "--no-sha-check", action="store_true",
        help=(
            "skip the consensus_sha256 binding check (ADR-001 §2.10.6). "
            "Default is to enforce binding when overrides_doc carries "
            "a consensus_sha256."
        ),
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.consensus.exists():
        print(f"[apply_overrides] consensus not found: {args.consensus}",
              file=sys.stderr)
        return 2
    consensus = json.loads(args.consensus.read_text(encoding="utf-8"))

    overrides_doc: dict | None = None
    if args.overrides is not None and args.overrides.exists():
        try:
            overrides_doc = json.loads(
                args.overrides.read_text(encoding="utf-8"),
            )
        except json.JSONDecodeError as e:
            print(
                f"[apply_overrides] overrides JSON parse error: {e}",
                file=sys.stderr,
            )
            return 2

    expected_sha: str | None = None
    if (
        overrides_doc is not None
        and not args.no_sha_check
        and overrides_doc.get("consensus_sha256")
    ):
        expected_sha = _consensus_sha256(consensus)

    amended = apply_overrides(
        consensus, overrides_doc, expected_sha=expected_sha,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(amended, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md = amended.get("_overrides_metadata") or {}
    print(
        f"[apply_overrides] applied={md.get('overrides_applied_count', 0)} "
        f"dropped={md.get('overrides_dropped_count', 0)} "
        f"block_skp_export={md.get('block_skp_export', False)}",
    )
    if md.get("warnings"):
        for w in md["warnings"]:
            print(f"[apply_overrides][warn] {w}", file=sys.stderr)
    print(f"[wrote] {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
