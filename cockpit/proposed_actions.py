"""Cockpit-side consumer for ``proposed_actions.json`` (Slice 4 + 6b).

ADR-001 §2.6 says proposed_actions are **advisory** — the pipeline
never auto-applies them. The cockpit Review tab surfaces each
proposed_action as a chip next to the affected element; the human
clicks "Apply" to promote a chip into a real ``review_overrides.json``
entry. This module provides the loader + the promotion mapping +
a thin convenience wrapper around :func:`cockpit.overrides.save_override`.

# Promotion mapping

| Proposed action type | Override type | Notes |
|---|---|---|
| ``classify_opening`` | ``opening_kind_override`` | ``payload.suggested_kind`` → ``new_kind_v5`` |
| ``mark_low_confidence`` | ``mark_suspect`` | severity = ``"low"`` |
| ``request_human_review`` (opening) | ``mark_suspect`` | severity = ``"medium"`` |
| ``request_human_review`` (room) | ``mark_suspect`` | severity = ``"medium"`` |
| ``expand_room_polygon`` (Slice 6b) | ``room_polygon_override`` | ``edit_method = "from_proposed_action"``; ``new_polygon_pts`` ← ``payload.suggested_polygon_pts`` |
| ``shrink_room_polygon`` (Slice 6b) | ``room_polygon_override`` | same as expand |

The producer emits ``suggested_polygon_pts`` pre-computed (uniform
centroid scale by ``payload.scale_factor``). The cockpit UI is
expected to seed the polygon text-area from that field so the human
can review and edit BEFORE the override is written; calling
:func:`apply_proposed_action` directly on a polygon chip writes the
suggested polygon AS-IS (no review step) and is intended for headless
tests, not the UI path. See ADR-002 §4 Slice 6b.

The renderer returns ``None`` for any unknown action type so future
producer versions can ship more types before the cockpit knows how
to promote them.

# Boundary

- **Read-only** w.r.t. ``proposed_actions.json`` — never mutates it.
  The producer (``tools.propose_skp_actions``) owns writes.
- **Write-only** w.r.t. ``review_overrides.json`` — only via
  :func:`cockpit.overrides.save_override`, which preserves the
  ADR-001 §2.10 invariants (originals immutable, audit trail
  append-only, etc.).
- The ``source_proposed_action_id`` link lives in the audit-trail
  ``create`` entry (per ADR-001 §2.7), not on the override record
  itself. The override is the decision; the audit trail is the
  history.
"""
from __future__ import annotations

import json
from pathlib import Path

from cockpit import overrides as overrides_mod
from cockpit.overrides import PT_TO_M

PROPOSED_ACTIONS_FILENAME = "proposed_actions.json"

# Slice 6b — proposed_action types that the cockpit promotes into a
# ``room_polygon_override``. Kept as a frozenset so callers (including
# the cockpit Review tab) can do membership tests cheaply.
POLYGON_PROPOSED_ACTION_TYPES: frozenset[str] = frozenset({
    "expand_room_polygon",
    "shrink_room_polygon",
})

# Mirror the producer's enums so a stale install of one side doesn't
# silently drift from the other. If these diverge from
# ``tools.propose_skp_actions.ACTION_TYPES`` the unit tests will
# notice at module-load time.
PROPOSED_ACTION_TYPES: tuple[str, ...] = (
    "classify_opening",
    "expand_room_polygon",
    "shrink_room_polygon",
    "relink_opening_rooms",
    "mark_low_confidence",
    "request_human_review",
)


def proposed_actions_path(run_dir: Path | str) -> Path:
    """Conventional path: ``<run_dir>/proposed_actions.json``."""
    return Path(run_dir) / PROPOSED_ACTIONS_FILENAME


def _polygon_area_pts2(pts: list[list[float]]) -> float:
    """Signed shoelace area, absolute value. Mirrors the same helper
    in ``tools.propose_skp_actions`` so this module stays import-light
    (no shapely dep). Used as a fallback when the producer chip omits
    ``estimated_area_pts2``."""
    n = len(pts) if pts else 0
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x0, y0 = float(pts[i][0]), float(pts[i][1])
        x1, y1 = float(pts[(i + 1) % n][0]), float(pts[(i + 1) % n][1])
        total += x0 * y1 - x1 * y0
    return abs(total) / 2.0


# ---------- Loader ----------------------------------------------------

def load_proposed_actions(run_dir: Path | str,
                          expected_consensus_sha: str | None = None,
                          ) -> dict:
    """Load ``proposed_actions.json`` from ``run_dir``.

    Returns a dict shaped like the wire schema (per ADR-001 §2.4)
    plus a runtime-only ``_consensus_sha256_match`` field that the
    cockpit uses to decide whether to surface chips:

    - ``True``  — the file's ``consensus_sha256`` matches
      ``expected_consensus_sha`` (or no expected was supplied).
    - ``False`` — the file is stale; chips should be hidden or
      flagged. Mirrors the override loader's behaviour for
      consistency. Per ADR-001 §2.6 proposed_actions are advisory
      so we never *invalidate* them, but we let the UI demote
      stale proposals.

    When the file is missing, returns an empty-shaped dict with
    ``actions == []`` so callers don't have to handle ``None``.
    Never raises on missing file. On JSON parse error returns the
    empty shape with a ``_load_error`` key for visibility.
    """
    path = proposed_actions_path(run_dir)
    base = {
        "schema_version": "proposed_actions_v1",
        "run_id": Path(run_dir).name if run_dir is not None else None,
        "consensus_sha256": None,
        "generated_at": None,
        "generator": None,
        "actions": [],
        "_consensus_sha256_match": True,
    }
    if not path.exists():
        return base
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        base["_load_error"] = f"{type(e).__name__}: {e}"
        return base
    # Merge keeping defaults for missing fields, then overlay loaded.
    merged = {**base, **loaded}
    merged.setdefault("actions", [])
    if expected_consensus_sha is not None and merged.get("consensus_sha256"):
        merged["_consensus_sha256_match"] = (
            str(merged["consensus_sha256"]) == str(expected_consensus_sha)
        )
    else:
        merged["_consensus_sha256_match"] = True
    return merged


# ---------- Promotion mapping ----------------------------------------

def proposed_action_to_override_payload(action: dict) -> dict | None:
    """Map one proposed_action → an override-payload dict suitable for
    :func:`cockpit.overrides.save_override`.

    Returns ``None`` for action types this Slice doesn't yet know how
    to promote (so future producer types can ship safely).

    The returned dict has the partial-override shape:
    ``{type, target, payload, reason}``. ``save_override`` fills in
    ``id``, ``created_at``, ``author``, ``signature``.
    """
    if not isinstance(action, dict):
        return None
    a_type = action.get("type")
    target = action.get("target") or {}
    payload = action.get("payload") or {}
    target_kind = target.get("kind")
    target_id = target.get("id")
    if not target_kind or not target_id:
        return None
    rationale = action.get("rationale") or ""
    pa_id = action.get("id") or "<unknown>"
    base_reason = (
        f"Promoted from proposed_action {pa_id}: {rationale[:200]}"
    )

    if a_type == "classify_opening":
        suggested = payload.get("suggested_kind")
        if not suggested:
            return None
        return {
            "type": "opening_kind_override",
            "target": {"kind": "opening", "id": str(target_id)},
            "payload": {"new_kind_v5": str(suggested)},
            "reason": base_reason,
        }
    if a_type == "mark_low_confidence":
        return {
            "type": "mark_suspect",
            "target": {"kind": str(target_kind), "id": str(target_id)},
            "payload": {"severity": "low", "tag": "low_confidence"},
            "reason": base_reason,
        }
    if a_type == "request_human_review":
        # Promote to mark_suspect medium so the SVG annotates it.
        # Reason carries the original reason_codes for traceability.
        codes = payload.get("reason_codes") or []
        tag = (codes[0] if codes else "review_requested")
        return {
            "type": "mark_suspect",
            "target": {"kind": str(target_kind), "id": str(target_id)},
            "payload": {"severity": "medium", "tag": str(tag)},
            "reason": base_reason,
        }
    if a_type in POLYGON_PROPOSED_ACTION_TYPES:
        # Slice 6b: polygon-correction chip → room_polygon_override.
        # Reads suggested_polygon_pts from the producer payload (the
        # producer ran a uniform-centroid scale; the cockpit text-area
        # surfaces this as a DRAFT for human review before save).
        if target_kind != "room":
            return None
        suggested = payload.get("suggested_polygon_pts")
        if (not isinstance(suggested, list)
                or len(suggested) < 3):
            return None
        # Defensive: every point must be a [x, y] number pair.
        normalised: list[list[float]] = []
        for pt in suggested:
            if (not isinstance(pt, (list, tuple))
                    or len(pt) != 2
                    or not isinstance(pt[0], (int, float))
                    or not isinstance(pt[1], (int, float))):
                return None
            normalised.append([float(pt[0]), float(pt[1])])
        # Prefer producer-supplied areas; otherwise recompute so the
        # override always carries consistent estimated_area_*.
        area_pts2 = payload.get("estimated_area_pts2")
        if not isinstance(area_pts2, (int, float)) or area_pts2 <= 0:
            area_pts2 = _polygon_area_pts2(normalised)
        if area_pts2 <= 0:
            return None
        area_m2 = payload.get("estimated_area_m2")
        if not isinstance(area_m2, (int, float)) or area_m2 <= 0:
            area_m2 = float(area_pts2) * (PT_TO_M ** 2)
        return {
            "type": "room_polygon_override",
            "target": {"kind": "room", "id": str(target_id)},
            "payload": {
                "new_polygon_pts": normalised,
                "edit_method": "from_proposed_action",
                "estimated_area_pts2": float(area_pts2),
                "estimated_area_m2": float(area_m2),
                "from_proposed_action_id": str(pa_id),
            },
            "reason": base_reason,
        }
    # Unknown / not-yet-supported types
    return None


# ---------- Apply convenience -----------------------------------------

def apply_proposed_action(run_dir: Path | str,
                           action: dict,
                           audit_actor: str = "human",
                           consensus_path: Path | None = None,
                           consensus: dict | None = None) -> dict:
    """Promote ``action`` → override and call
    :func:`cockpit.overrides.save_override` with the
    ``source_proposed_action_id`` audit-link wired up.

    Raises :class:`ValueError` if the proposed_action shape is
    invalid or its type is not promotable in this Slice.
    """
    if not isinstance(action, dict):
        raise ValueError(f"action must be a dict, got {type(action).__name__}")
    pa_id = action.get("id")
    if not pa_id:
        raise ValueError("proposed_action missing required field: id")
    override_payload = proposed_action_to_override_payload(action)
    if override_payload is None:
        raise ValueError(
            f"proposed_action type {action.get('type')!r} is not "
            "promotable in Slice 4 (no mapping defined)"
        )
    return overrides_mod.save_override(
        run_dir=Path(run_dir),
        override_payload=override_payload,
        audit_actor=audit_actor,
        consensus_path=consensus_path,
        consensus=consensus,
        source_proposed_action_id=str(pa_id),
    )


# ---------- View helpers (cockpit UI) --------------------------------

def actions_for_target(actions: list[dict],
                        target_kind: str,
                        target_id: str) -> list[dict]:
    """Return all proposed_actions whose target matches
    ``(target_kind, target_id)``. Used by the Review tab to render
    chips next to each opening / room."""
    out: list[dict] = []
    for a in actions or []:
        t = a.get("target") or {}
        if (t.get("kind") == target_kind
                and str(t.get("id")) == str(target_id)):
            out.append(a)
    return out


def action_already_applied(action: dict, audit_trail: list[dict]) -> bool:
    """``True`` if any audit-trail entry references this action's id
    via ``source_proposed_action_id``. Lets the cockpit grey out
    chips that have already been promoted."""
    pa_id = (action or {}).get("id")
    if not pa_id:
        return False
    for entry in audit_trail or []:
        if entry.get("source_proposed_action_id") == str(pa_id):
            return True
    return False


__all__ = [
    "POLYGON_PROPOSED_ACTION_TYPES",
    "PROPOSED_ACTIONS_FILENAME",
    "PROPOSED_ACTION_TYPES",
    "action_already_applied",
    "actions_for_target",
    "apply_proposed_action",
    "load_proposed_actions",
    "proposed_action_to_override_payload",
    "proposed_actions_path",
]
