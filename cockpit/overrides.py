"""Validation Cockpit — review_overrides.json read/write helper.

Slice 2 (2026-05-08). Implements the Phase 1 of the mutation
surface defined in `docs/adr/ADR-001-validation-cockpit-mutation-surface.md`.

The cockpit reads + writes `runs/<run_id>/review_overrides.json`.
The pipeline still IGNORES the file at this Phase (per ADR §2.9
Phase 1). Slice 3 introduces `tools/apply_overrides.py` and the
fidelity engine starts honouring overrides.

Boundary (pure-Python):
- NO streamlit imports — this module is unit-tested independently
  and re-used by the Streamlit shell + (future) CLI.
- NEVER edits `consensus_*.json`. Originals are immutable
  (ADR §2.10.1).
- Append-only `audit_trail[]` (ADR §2.10.3 / §2.7).
- Atomic writes via tempfile + os.replace.
- consensus_sha256 binds the override file to the source consensus
  (ADR §2.10.6 / §2.5).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Schema / enum surface (ADR §2.5)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "review_overrides_v1"

OVERRIDE_TYPES: tuple[str, ...] = (
    "opening_kind_override",
    "opening_connects_override",
    "room_label_override",
    "mark_suspect",
    "reject_element",
    "approve_element",
    # block_skp_export is global, not per-element — see set_block_skp_export()
)

OPENING_KIND_VALUES: tuple[str, ...] = (
    "interior_door",
    "interior_passage",
    "window",
    "glazed_balcony",
    "exterior_door",
    "unknown",
)

SUSPECT_SEVERITIES: tuple[str, ...] = ("low", "medium", "high")

TARGET_KINDS: tuple[str, ...] = ("opening", "room")

# Precedence order: higher index = higher priority
# (per ADR §2.5 "Precedence rules"). reject beats mark_suspect beats
# explicit kind/connect/label overrides beats approve_element.
_PRECEDENCE_ORDER: tuple[str, ...] = (
    "approve_element",
    "opening_kind_override",
    "opening_connects_override",
    "room_label_override",
    "mark_suspect",
    "reject_element",
)


# ---------------------------------------------------------------------------
# Filenames + paths
# ---------------------------------------------------------------------------

OVERRIDES_FILENAME = "review_overrides.json"


def overrides_path(run_dir: Path) -> Path:
    """Path to the review_overrides.json file for a run dir."""
    return Path(run_dir) / OVERRIDES_FILENAME


# ---------------------------------------------------------------------------
# Time / id helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """ISO 8601 timestamp in UTC, second-precision (ADR §2.5)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# SHA-256 helpers (ADR §2.10.6)
# ---------------------------------------------------------------------------

def compute_consensus_sha256(consensus_path: Path) -> str:
    """sha256 of the consensus file's bytes-on-disk.

    Used to bind a `review_overrides.json` to a specific consensus
    snapshot. A re-run that produces a new consensus invalidates the
    binding (overrides are flagged stale until re-confirmed).
    """
    h = hashlib.sha256()
    with Path(consensus_path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _signature_for(target: dict, payload: dict, author: str,
                   created_at: str) -> str:
    """sha256 of {target, payload, author, created_at}.

    Stable across reads/writes (canonical JSON via sort_keys).
    """
    blob = json.dumps(
        {
            "target": target,
            "payload": payload,
            "author": author,
            "created_at": created_at,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _audit_diff_signature(before: dict | None, after: dict | None) -> str:
    blob = json.dumps(
        {"before": before, "after": after},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Empty / default file
# ---------------------------------------------------------------------------

def empty_overrides_file(run_id: str,
                          consensus_path: Path | str | None,
                          consensus_sha256: str | None) -> dict:
    """Return a fresh, schema-conformant `review_overrides_v1` dict.

    Useful as a starting point when no file exists yet on disk.
    """
    now = _now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "consensus_sha256": consensus_sha256 or "",
        "consensus_path": (str(consensus_path) if consensus_path is not None
                           else ""),
        "created_at": now,
        "last_updated_at": now,
        "overrides": [],
        "global": {
            "block_skp_export": False,
            "block_reason": None,
        },
        "audit_trail": [],
    }


# ---------------------------------------------------------------------------
# Atomic file IO
# ---------------------------------------------------------------------------

def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON to ``path`` via a sibling tempfile + os.replace.

    Crash-safe: a partial write never overwrites the destination.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False,
                      sort_keys=False)
            fh.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        # Best-effort cleanup
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_overrides(run_dir: Path,
                    consensus_path: Path | None = None) -> dict:
    """Load `review_overrides.json` from a run dir.

    When the file is missing, returns a fresh in-memory empty
    overrides dict (NOT written to disk — the cockpit can decide to
    persist on first save). When `consensus_path` is supplied, the
    on-disk `consensus_sha256` is compared to the live consensus
    sha256; the returned dict carries a `_consensus_sha256_match`
    boolean (True / False / None when no consensus_path supplied).
    Per ADR §2.10.6, a mismatch INVALIDATES the overrides for
    apply-time but they remain on disk for human re-confirmation.
    """
    path = overrides_path(run_dir)
    if not path.exists():
        sha = (compute_consensus_sha256(consensus_path)
               if consensus_path is not None and Path(consensus_path).exists()
               else None)
        run_id = Path(run_dir).name
        out = empty_overrides_file(run_id, consensus_path, sha)
        out["_consensus_sha256_match"] = (
            None if consensus_path is None else True
        )
        return out
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    # Best-effort sha-validation
    if consensus_path is not None and Path(consensus_path).exists():
        live_sha = compute_consensus_sha256(consensus_path)
        data["_consensus_sha256_match"] = (
            data.get("consensus_sha256") == live_sha
        )
    else:
        data["_consensus_sha256_match"] = None
    return data


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_override_payload(payload: dict,
                               consensus: dict | None = None) -> list[str]:
    """Return a list of validation errors. Empty list = valid.

    `payload` is the override-record-shaped dict that would be added
    to `overrides[]`. `consensus` is the source consensus dict; when
    provided, target.id is checked against it.

    The cockpit calls this before `save_override` and surfaces the
    error list to the user when non-empty.
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload is not a dict"]
    typ = payload.get("type")
    if typ not in OVERRIDE_TYPES:
        errors.append(
            f"type {typ!r} not in {OVERRIDE_TYPES}"
        )
    target = payload.get("target") or {}
    if not isinstance(target, dict):
        errors.append("target must be a dict")
        target = {}
    target_kind = target.get("kind")
    target_id = target.get("id")
    if target_kind not in TARGET_KINDS:
        errors.append(
            f"target.kind {target_kind!r} not in {TARGET_KINDS}"
        )
    if not isinstance(target_id, str) or not target_id:
        errors.append("target.id must be a non-empty string")

    body = payload.get("payload")
    if body is None or not isinstance(body, dict):
        errors.append("payload.payload must be a dict (may be empty)")
        body = {}

    # Type-specific payload checks
    if typ == "opening_kind_override":
        kv = body.get("new_kind_v5")
        if kv not in OPENING_KIND_VALUES:
            errors.append(
                f"opening_kind_override.new_kind_v5 {kv!r} not in "
                f"{OPENING_KIND_VALUES}"
            )
        if target_kind != "opening":
            errors.append("opening_kind_override target.kind must be 'opening'")
    elif typ == "opening_connects_override":
        rl = body.get("room_left_id")
        rr = body.get("room_right_id")
        if not isinstance(rl, str) or not rl:
            errors.append("opening_connects_override.room_left_id required")
        if not isinstance(rr, str) or not rr:
            errors.append("opening_connects_override.room_right_id required")
        if target_kind != "opening":
            errors.append(
                "opening_connects_override target.kind must be 'opening'"
            )
        # Cross-check against consensus rooms when supplied
        if consensus is not None:
            room_ids = {r.get("id") for r in (consensus.get("rooms") or [])}
            if isinstance(rl, str) and rl and rl not in room_ids:
                errors.append(
                    f"opening_connects_override.room_left_id {rl!r} "
                    f"not in consensus rooms"
                )
            if isinstance(rr, str) and rr and rr not in room_ids:
                errors.append(
                    f"opening_connects_override.room_right_id {rr!r} "
                    f"not in consensus rooms"
                )
    elif typ == "room_label_override":
        nm = body.get("new_name")
        if not isinstance(nm, str) or not nm.strip():
            errors.append(
                "room_label_override.new_name required (non-empty string)"
            )
        if target_kind != "room":
            errors.append("room_label_override target.kind must be 'room'")
    elif typ == "mark_suspect":
        sev = body.get("severity")
        if sev not in SUSPECT_SEVERITIES:
            errors.append(
                f"mark_suspect.severity {sev!r} not in {SUSPECT_SEVERITIES}"
            )
        # tag is free-text and optional in v1; accept missing
    elif typ in ("reject_element", "approve_element"):
        # Empty body permitted
        pass

    # Cross-check target.id against consensus when supplied
    if consensus is not None and isinstance(target_id, str) and target_id:
        if target_kind == "opening":
            ids = {o.get("id") for o in (consensus.get("openings") or [])}
        elif target_kind == "room":
            ids = {r.get("id") for r in (consensus.get("rooms") or [])}
        else:
            ids = set()
        if target_id not in ids:
            errors.append(
                f"target.id {target_id!r} not found in consensus "
                f"{target_kind}s"
            )

    return errors


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_override(run_dir: Path,
                   override_payload: dict,
                   audit_actor: str,
                   consensus_path: Path | None = None,
                   consensus: dict | None = None) -> dict:
    """Append a new override to `review_overrides.json`.

    `override_payload` is a partial override-record shaped like
    {type, target, payload, reason?}. The function fills in `id`,
    `created_at`, `author`, `signature`. The corresponding
    audit_trail entry is appended atomically.

    Returns the full file dict after write. Raises ValueError on
    schema validation failure (with all errors concatenated).
    """
    # Build fully-shaped record
    typ = override_payload.get("type")
    target = override_payload.get("target") or {}
    body = override_payload.get("payload") or {}
    reason = override_payload.get("reason") or ""

    record = {
        "id": _new_id(),
        "type": typ,
        "target": dict(target),
        "payload": dict(body),
        "author": audit_actor or "human",
        "created_at": _now_iso(),
        "reason": reason,
    }

    errors = validate_override_payload(record, consensus=consensus)
    if errors:
        raise ValueError(
            "review_overrides validation failed: "
            + "; ".join(errors)
        )

    record["signature"] = _signature_for(
        target=record["target"],
        payload=record["payload"],
        author=record["author"],
        created_at=record["created_at"],
    )

    # Load existing file (may be empty)
    data = load_overrides(run_dir, consensus_path=consensus_path)
    # Strip the runtime-only key before persisting
    data.pop("_consensus_sha256_match", None)

    data["overrides"].append(record)
    data["last_updated_at"] = _now_iso()

    audit = {
        "id": _new_id(),
        "event": "create",
        "override_id": record["id"],
        "actor": audit_actor or "human",
        "timestamp": data["last_updated_at"],
        "before": None,
        "after": dict(record),
        "diff_signature": _audit_diff_signature(None, record),
    }
    data["audit_trail"].append(audit)

    _atomic_write_json(overrides_path(run_dir), data)
    return data


def remove_override(run_dir: Path,
                     override_id: str,
                     audit_actor: str,
                     consensus_path: Path | None = None) -> dict:
    """Remove an override from `overrides[]` and append a `delete`
    audit entry.

    The audit trail is **append-only** (ADR §2.10.3 / §2.7): the
    deleted override's prior `create` entry STAYS in `audit_trail[]`
    untouched; this function appends a NEW entry with
    ``event: "delete"``, the captured ``before`` state of the removed
    override, and ``after: null``. A future viewer can replay the
    full history (create → delete) without losing fidelity.

    Args:
        run_dir: directory containing the `review_overrides.json`.
        override_id: the `id` of the override to remove (the uuid
            assigned by ``save_override``). Lookup is exact match.
        audit_actor: free-form actor string (e.g. ``"human"`` or
            ``"agent:cleanup"``).
        consensus_path: optional, only used to refresh the
            `_consensus_sha256_match` flag on the loaded doc.

    Returns:
        The full file dict after the atomic write.

    Raises:
        ValueError: if no override with the supplied ``override_id``
            is found in ``overrides[]``.
    """
    data = load_overrides(run_dir, consensus_path=consensus_path)
    data.pop("_consensus_sha256_match", None)

    overrides = data.get("overrides") or []
    idx = next(
        (i for i, ov in enumerate(overrides)
         if ov.get("id") == override_id),
        None,
    )
    if idx is None:
        raise ValueError(
            f"override_id {override_id!r} not found in overrides[]"
        )

    before = dict(overrides[idx])  # snapshot for audit
    # Remove the override from the live list
    del overrides[idx]
    data["overrides"] = overrides
    data["last_updated_at"] = _now_iso()

    audit = {
        "id": _new_id(),
        "event": "delete",
        "override_id": override_id,
        "actor": audit_actor or "human",
        "timestamp": data["last_updated_at"],
        "before": before,
        "after": None,
        "diff_signature": _audit_diff_signature(before, None),
    }
    data["audit_trail"].append(audit)

    _atomic_write_json(overrides_path(run_dir), data)
    return data


def set_block_skp_export(run_dir: Path,
                          blocked: bool,
                          reason: str | None,
                          audit_actor: str,
                          consensus_path: Path | None = None) -> dict:
    """Toggle the global `block_skp_export` flag.

    ADR §2.10.7: sticky — once set, remains until explicitly
    cleared via a new audit-trailed event. Writing the same value
    again is still recorded in the audit trail (no-op detection is
    deferred to the UI layer).
    """
    data = load_overrides(run_dir, consensus_path=consensus_path)
    data.pop("_consensus_sha256_match", None)

    before_global = dict(data.get("global") or {})
    new_global = {
        "block_skp_export": bool(blocked),
        "block_reason": (reason if reason else None),
    }
    data["global"] = new_global
    data["last_updated_at"] = _now_iso()

    audit = {
        "id": _new_id(),
        "event": "update" if before_global else "create",
        "override_id": None,  # global flag, not per-element
        "actor": audit_actor or "human",
        "timestamp": data["last_updated_at"],
        "before": {"global": before_global},
        "after": {"global": dict(new_global)},
        "diff_signature": _audit_diff_signature(
            {"global": before_global}, {"global": dict(new_global)}
        ),
        "tag": "block_skp_export",
    }
    data["audit_trail"].append(audit)
    _atomic_write_json(overrides_path(run_dir), data)
    return data


# ---------------------------------------------------------------------------
# Precedence + apply view (read-only)
# ---------------------------------------------------------------------------

def _element_key(target: dict | None) -> str | None:
    if not target:
        return None
    kind = target.get("kind")
    eid = target.get("id")
    if not kind or not eid:
        return None
    return f"{kind}:{eid}"


def precedence_resolve(overrides: Iterable[dict]) -> dict[str, dict]:
    """Pick the active override per element, applying ADR §2.5
    precedence:

        reject_element > mark_suspect > opening/room overrides
        > approve_element > nothing

    Within the same precedence level, last `created_at` wins.

    Returns a dict keyed by `<kind>:<id>` -> the chosen override
    record. Elements with no overrides are absent from the dict.
    """
    by_element: dict[str, list[dict]] = {}
    for ov in overrides:
        key = _element_key(ov.get("target"))
        if key is None:
            continue
        by_element.setdefault(key, []).append(ov)

    out: dict[str, dict] = {}
    for key, group in by_element.items():
        def sort_key(ov: dict) -> tuple[int, str]:
            typ = ov.get("type")
            try:
                prio = _PRECEDENCE_ORDER.index(typ)
            except ValueError:
                prio = -1
            return (prio, ov.get("created_at") or "")
        chosen = max(group, key=sort_key)
        out[key] = chosen
    return out


def overrides_apply_view(consensus: dict,
                          overrides: list[dict],
                          pt_to_m: float = 0.19 / 5.4) -> dict:
    """Build a READ-ONLY derived view of consensus + overrides.

    Used ONLY by the cockpit for display (Review tab + SVG tooltip
    annotations in a future cycle). Pipeline still IGNORES this.

    Each opening / room in the returned view carries a `source`
    field (per ADR §2.10.4):
      - "detected"          — straight from consensus
      - "manual"            — overridden by a human
      - "override_rejected" — element marked for drop via
                              `reject_element` (still in view but
                              flagged)

    Approved elements are flagged via `_approved: True`.
    Suspects gain `_suspect: {severity, tag}`.
    """
    consensus = consensus or {}
    rooms = list(consensus.get("rooms") or [])
    openings = list(consensus.get("openings") or [])

    active = precedence_resolve(overrides or [])

    # Annotate openings
    out_openings: list[dict] = []
    for op in openings:
        record = dict(op)
        record["source"] = "detected"
        key = f"opening:{op.get('id')}"
        ov = active.get(key)
        # Walk all overrides for this element to surface
        # mark_suspect / approve which are NOT chosen by precedence
        # but still need to be reflected.
        for sec in (overrides or []):
            if _element_key(sec.get("target")) != key:
                continue
            if sec.get("type") == "mark_suspect":
                body = sec.get("payload") or {}
                record["_suspect"] = {
                    "severity": body.get("severity"),
                    "tag": body.get("tag"),
                }
            elif sec.get("type") == "approve_element":
                record["_approved"] = True
        if ov is not None:
            typ = ov.get("type")
            if typ == "reject_element":
                record["source"] = "override_rejected"
                record["_rejected"] = True
            elif typ == "opening_kind_override":
                body = ov.get("payload") or {}
                record["_kind_v5_original"] = record.get("kind_v5")
                record["kind_v5"] = body.get("new_kind_v5")
                record["source"] = "manual"
            elif typ == "opening_connects_override":
                body = ov.get("payload") or {}
                ev = dict(record.get("evidence") or {})
                record["_room_left_id_original"] = ev.get("room_left_id")
                record["_room_right_id_original"] = ev.get("room_right_id")
                ev["room_left_id"] = body.get("room_left_id")
                ev["room_right_id"] = body.get("room_right_id")
                record["evidence"] = ev
                record["source"] = "manual"
        out_openings.append(record)

    # Annotate rooms
    out_rooms: list[dict] = []
    for r in rooms:
        record = dict(r)
        record["source"] = "detected"
        key = f"room:{r.get('id')}"
        ov = active.get(key)
        for sec in (overrides or []):
            if _element_key(sec.get("target")) != key:
                continue
            if sec.get("type") == "mark_suspect":
                body = sec.get("payload") or {}
                record["_suspect"] = {
                    "severity": body.get("severity"),
                    "tag": body.get("tag"),
                }
            elif sec.get("type") == "approve_element":
                record["_approved"] = True
        if ov is not None:
            typ = ov.get("type")
            if typ == "reject_element":
                record["source"] = "override_rejected"
                record["_rejected"] = True
            elif typ == "room_label_override":
                body = ov.get("payload") or {}
                record["_name_original"] = record.get("name")
                record["name"] = body.get("new_name")
                record["source"] = "manual"
        out_rooms.append(record)

    return {
        "schema_version": "review_overrides_view_v1",
        "rooms": out_rooms,
        "openings": out_openings,
        "pt_to_m": pt_to_m,
        "active_overrides_count": len(active),
        "total_overrides_count": len(overrides or []),
    }


# ---------------------------------------------------------------------------
# Convenience: list active overrides for an element (for UI surfacing)
# ---------------------------------------------------------------------------

def overrides_for_element(overrides: Iterable[dict],
                           kind: str, eid: str) -> list[dict]:
    """All overrides pointing at `<kind>:<id>`, newest-first."""
    target_key = f"{kind}:{eid}"
    matches = [o for o in (overrides or [])
               if _element_key(o.get("target")) == target_key]
    matches.sort(key=lambda o: o.get("created_at") or "", reverse=True)
    return matches


__all__ = [
    "SCHEMA_VERSION",
    "OVERRIDE_TYPES",
    "OPENING_KIND_VALUES",
    "SUSPECT_SEVERITIES",
    "TARGET_KINDS",
    "OVERRIDES_FILENAME",
    "overrides_path",
    "compute_consensus_sha256",
    "empty_overrides_file",
    "load_overrides",
    "validate_override_payload",
    "save_override",
    "remove_override",
    "set_block_skp_export",
    "precedence_resolve",
    "overrides_apply_view",
    "overrides_for_element",
]
