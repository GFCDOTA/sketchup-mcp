"""FP-033 — normalize detector outputs into the unified `correction_finding.v1`.

Each detector speaks its own dialect:

- ``visual_findings.v1`` (FP-032): ``findings[] {id, severity, axis, type, location,
  evidence_image, evidence, source?}``
- ``geometry_sanity.audit()``: ``findings[] {severity, check, label, kind, detail}``
- ``furniture_overlap_gate.overlap_gate()``: ``{result, room, fails[str], warns[str]}``
- ``run_deterministic_gates.run_all()``: ``{gate_name: {verdict|overall|result, ...}}``

This module maps them ALL onto one shape (see ``schemas/correction_finding.schema.json``)
so ``finding_router.classify`` and the loop consume a single dialect. Pure, no I/O.
Normalization NEVER invents a verdict/type — it only reshapes what the detector said;
message-only detectors (``geometry_sanity.sanity_room``) are deferred (slice 2).
"""
from __future__ import annotations

from tools import finding_router

# gate name (run_deterministic_gates) -> canonical finding type
_GATE_TYPE = {
    "opening_host": "opening_host_mismatch",
    "wall_overlap": "wall_overlap",
    "position_fidelity": "position_fidelity",
    "render_bbox": "render_bbox",
    "wall_presence": "wall_presence",
}
# gate verdict keys, in the order we trust them
_VERDICT_KEYS = ("verdict", "overall", "result", "status")
_BAD_VERDICTS = {"FAIL", "WARN"}


def make_finding(
    *, type: str, severity: str, source: str, evidence: str,
    source_check: str = "", suspected_owner: str | None = None,
    location: str | None = None, axis: str | None = None,
    room: str | None = None, id: str | None = None,
) -> dict:
    """Build a unified correction_finding, dropping None optionals so the result
    stays minimal and schema-clean."""
    f: dict = {
        "type": str(type), "severity": severity, "source": source,
        "evidence": str(evidence),
    }
    for k, v in (
        ("source_check", source_check), ("suspected_owner", suspected_owner),
        ("location", location), ("axis", axis), ("room", room), ("id", id),
    ):
        if v:
            f[k] = v
    f["route"] = finding_router.classify(f)
    return f


def _gate_verdict(gate: dict) -> str | None:
    if not isinstance(gate, dict):
        return None
    for k in _VERDICT_KEYS:
        v = gate.get(k)
        if isinstance(v, str) and v.upper() in _BAD_VERDICTS:
            return v.upper()
    return None


def from_visual_findings_v1(vf: dict) -> list[dict]:
    """visual_findings.v1 (FP-032) -> unified findings. Reads the explicit
    ``findings`` list; carries `axis`/`location`/`source` through for routing."""
    if not isinstance(vf, dict):
        return []
    src = vf.get("source") or "claude_bridge"
    out: list[dict] = []
    for f in vf.get("findings", []) or []:
        if not isinstance(f, dict):
            continue
        sev = f.get("severity", "WARN")
        if sev not in _BAD_VERDICTS:
            sev = "WARN"
        out.append(make_finding(
            type=f.get("type", "global_visual_fail"),
            severity=sev,
            source=src,
            source_check="visual_oracle",
            suspected_owner=f.get("suspected_owner"),
            evidence=f.get("evidence", ""),
            location=f.get("location"),
            axis=f.get("axis"),
            id=f.get("id"),
        ))
    return out


def from_geometry_audit(audit: dict, *, room: str | None = None) -> list[dict]:
    """geometry_sanity.audit() -> unified findings (typed via `check`)."""
    if not isinstance(audit, dict):
        return []
    out: list[dict] = []
    for f in audit.get("findings", []) or []:
        if not isinstance(f, dict):
            continue
        out.append(make_finding(
            type=f.get("check", "degenerate_footprint"),
            severity=f.get("severity", "WARN"),
            source="deterministic",
            source_check="geometry_sanity",
            suspected_owner="furniture_brain",
            evidence=f.get("detail", ""),
            location=f.get("label"),
            room=room,
        ))
    return out


def from_overlap_gate(gate: dict) -> list[dict]:
    """furniture_overlap_gate.overlap_gate() -> unified findings (all
    ``furniture_overlap``; fails=FAIL, warns=WARN)."""
    if not isinstance(gate, dict):
        return []
    room = gate.get("room")
    out: list[dict] = []
    for sev, key in (("FAIL", "fails"), ("WARN", "warns")):
        for msg in gate.get(key, []) or []:
            out.append(make_finding(
                type="furniture_overlap", severity=sev,
                source="deterministic", source_check="furniture_overlap_gate",
                suspected_owner="furniture_brain", evidence=str(msg), room=room,
            ))
    return out


def from_deterministic_gates(gates: dict) -> list[dict]:
    """run_deterministic_gates.run_all() -> one unified finding per FAIL/WARN gate,
    typed by the gate. Robust to the gates' varying verdict key."""
    if not isinstance(gates, dict):
        return []
    out: list[dict] = []
    for name, gate in gates.items():
        verdict = _gate_verdict(gate)
        if verdict is None:
            continue  # PASS / SKIPPED / unknown-shape -> no finding
        out.append(make_finding(
            type=_GATE_TYPE.get(name, name),
            severity=verdict,
            source="deterministic",
            source_check=name,
            evidence=f"{name} gate verdict={verdict}",
        ))
    return out
