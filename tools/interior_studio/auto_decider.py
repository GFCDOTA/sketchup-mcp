"""auto_decider.py — the CARTEIRO: drains OBJECTIVE decisions so Felipe stops
clicking the technical ones. Runs as its own job with its own caps.

Single pass over a FROZEN snapshot of ``proposals.state()['pending']`` (no
re-loop). Each proposal is judged by ``decision_judge.classify`` (objective only —
STYLE/taste never enters) and acted on CONSERVATIVELY:

- OBJECTIVE_STRONG_PASS  -> proposals.approve   (auto_approve, decided_by=auto_decider)
- OBJECTIVE_STRONG_FAIL  -> proposals.reject    (auto_reject,  decided_by=auto_decider)
- TASTE_REFUSED          -> refused_taste        (NEVER touched — no approve/reject)
- INVALID                -> left_pending
- BORDERLINE             -> left_pending          (commit 3; gate mode B lands in commit 4)

Every processed item writes an append-only ``decision_audit_record`` (idempotent:
a re-run does not re-decide — approved/rejected proposals have left the pending
folder, and left_pending/refused records are deduped by (decision_id, action)).
``created_at`` is DERIVED from the pending file mtime, never the wall clock.

The RAIL: this module never imports the human-verdict vocabulary nor the literals
IMPROVED/SAME/WORSE; ``decided_by`` is always ``auto_decider`` (``gate_mode_b`` in
commit 4) — never a human. stdlib + decision_judge only.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from tools import ask_gpt_gate as agg
from tools.interior_studio import decision_judge as dj
from tools.interior_studio import proposals as ic_proposals
from tools.jsonl_io import append_jsonl, read_jsonl

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "runs"
AUDIT_NAME = "auto_decider_audit.jsonl"
DLQ_NAME = "auto_decider_dlq.jsonl"

AUDIT_SCHEMA = "decision_audit_record/1.0.0"
DEFAULT_CAPS = {"max_auto_decisions_per_drain": 20, "max_gate_calls_per_drain": 5}
GATE_TRIGGER = agg.OBJECTIVE_GATE_BORDERLINE

# actions
_APPROVE = "auto_approve"
_REJECT = "auto_reject"
_REFUSE = "refused_taste"
_PENDING = "left_pending"
_ESCALATED = "escalated_gate"

# a decisive gate verdict must be GO/NO-GO at non-low confidence; anything else
# (MORE-INFO, VISUAL_REVIEW, low confidence, offline) is inconclusive -> stays human.
_GATE_APPLY = {"GO": _APPROVE, "NO-GO": _REJECT}
_GATE_OK_CONF = ("high", "medium")
_FILL_RE = re.compile(r"~?(\d+)\s*%\s*do piso")


def _effective_caps(caps: dict | None) -> dict:
    eff = dict(DEFAULT_CAPS)
    env_max = os.environ.get("AUTO_DECIDER_MAX_DECISIONS")
    if env_max and env_max.strip().lstrip("-").isdigit():
        eff["max_auto_decisions_per_drain"] = int(env_max)
    env_gate = os.environ.get("AUTO_DECIDER_MAX_GATE_CALLS")
    if env_gate and env_gate.strip().lstrip("-").isdigit():
        eff["max_gate_calls_per_drain"] = int(env_gate)
    if caps:                                    # explicit param wins (testability)
        eff.update(caps)
    return eff


def _default_created_at(proposals_mod):
    """created_at derived from the PENDING file mtime (deterministic) — captured
    BEFORE the proposal is moved. No wall clock; unknown file -> epoch sentinel."""
    pdir = getattr(proposals_mod, "PDIR", None)

    def _iso(pid: str) -> str:
        if pdir:
            f = Path(pdir) / "pending" / f"{pid}.json"
            if f.exists():
                return datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return "1970-01-01T00:00:00Z"

    return _iso


def _default_gates(proposal: dict) -> tuple[str | None, str | None]:
    """Best-effort deterministic gates for a furniture_program's room, off the LIVE
    consensus. Any failure -> (None, None) == SKIPPED (never fabricated PASS), which
    keeps the item out of STRONG_PASS."""
    if proposal.get("type") != "furniture_program":
        return (None, None)
    room_id = proposal.get("room_id")
    if not room_id:
        return (None, None)
    try:
        os.environ.setdefault("PT_TO_M", "0.0259")
        from tools.furnish_apartment import CONSENSUS
        from tools.furniture_overlap_gate import overlap_gate
        from tools.geometry_sanity import sanity_room
        con = json.loads(Path(CONSENSUS).read_text("utf-8"))
        geo = sanity_room(con, room_id).get("status")
        ovl = overlap_gate(con, room_id).get("result")
        return (geo, ovl)
    except Exception:  # noqa: BLE001 — gates are advisory; SKIPPED is honest
        return (None, None)


def _record(judged: dict, action: str, created_at: str, caps: dict,
            corpus_version: str, *, decided_by: str = "auto_decider",
            gate: dict | None = None) -> dict:
    return {
        "schema": AUDIT_SCHEMA,
        "decision_id": judged["decision_id"],
        "decision_type": judged["decision_type"],
        "classification": judged["classification"],
        "action": action,
        "confidence": judged["confidence"],
        "evidence": judged["evidence"],
        "judge_verdicts": judged["judge_verdicts"],
        "gate": gate,
        "decided_by": decided_by,
        "caps_snapshot": dict(caps),
        "corpus_version": corpus_version,
        "created_at": created_at,
    }


def _gate_context(prop: dict, judged: dict) -> dict:
    """Deterministic evidence for the gate — gates, fill%, overlap verdict, the
    intern findings. The oracle rules on measured facts, never on taste."""
    evidence = list(judged.get("evidence", []))
    ctx = {
        "decision_id": judged["decision_id"],
        "decision_type": judged["decision_type"],
        "environment": prop.get("environment"),
        "room_id": prop.get("room_id"),
        "room_name": prop.get("room_name"),
        "judge_verdicts": judged["judge_verdicts"],   # geometry_sanity / furniture_overlap
        "objective_confidence": judged["confidence"],
        "deterministic_evidence": evidence,
    }
    for line in evidence:                              # surface fill% as a number
        m = _FILL_RE.search(line)
        if m:
            ctx["fill_pct"] = int(m.group(1))
            break
    return ctx


def _default_gate_fn(questions_dir: Path, responses_dir: Path, url: str | None):
    """Wraps ask_gpt_gate.run_gate with the 10th trigger. Offline degrades honest
    (SKIPPED_OFFLINE) — never fabricates a verdict."""
    def _call(prop: dict, judged: dict):
        ctx = _gate_context(prop, judged)
        question = (
            f"Objective BORDERLINE decision {judged['decision_id']} "
            f"({judged['decision_type']}): the deterministic gates carry a WARN "
            f"(no FAIL). From the deterministic evidence ONLY, should this be "
            f"approved (GO) or rejected (NO-GO)? This is a technical/objective call "
            f"— do NOT rule on taste/aesthetics; if it needs a human visual look, "
            f"answer VISUAL_REVIEW.")
        g = agg.GateInput(trigger=GATE_TRIGGER, question=question, context=ctx)
        kw = {"questions_dir": questions_dir, "responses_dir": responses_dir}
        if url:
            kw["url"] = url
        return agg.run_gate(g, **kw)
    return _call


def drain(*, caps: dict | None = None, proposals=ic_proposals, gates_fn=None,
          now_fn=None, out_dir: Path | None = None,
          corpus_version: str = "unknown", use_gate: bool = True, gate_fn=None,
          questions_dir: Path | None = None, responses_dir: Path | None = None,
          bridge_url: str | None = None) -> dict:
    """Single-pass objective drain. Returns
    {decided, escalated, refused, left_pending, audit_records}.

    Injectables (defaults are the live wiring): ``proposals`` (state/approve/reject),
    ``gates_fn(proposal)->(geo,overlap)``, ``now_fn(pid)->iso``, ``out_dir``.
    """
    eff_caps = _effective_caps(caps)
    max_dec = eff_caps["max_auto_decisions_per_drain"]
    max_gate = eff_caps["max_gate_calls_per_drain"]
    out = Path(out_dir) if out_dir else DEFAULT_OUT
    audit_path = out / AUDIT_NAME
    dlq_path = out / DLQ_NAME
    gates_fn = gates_fn or _default_gates
    now_fn = now_fn or _default_created_at(proposals)
    if use_gate and gate_fn is None:
        gate_fn = _default_gate_fn(
            questions_dir or (ROOT / ".ai_bridge" / "questions"),
            responses_dir or (ROOT / ".ai_bridge" / "responses"), bridge_url)
    if not use_gate:
        gate_fn = None

    # append-only + idempotent: never re-append a record for a (decision_id, action)
    seen = {(r.get("decision_id"), r.get("action")) for r in read_jsonl(audit_path)}

    pending = sorted(proposals.state().get("pending", []),
                     key=lambda p: str(p.get("id", "")))     # FROZEN, deterministic

    decided: list[dict] = []
    escalated: list[dict] = []
    refused: list[str] = []
    left_pending: list[str] = []
    new_records: list[dict] = []
    n_decisions = 0
    n_gate_calls = 0

    def _emit(rec: dict) -> None:
        # append-only + idempotent: a (decision_id, action) already recorded is not
        # re-appended, and does NOT count as a fresh record for this drain.
        if (rec["decision_id"], rec["action"]) not in seen:
            append_jsonl(audit_path, [rec])
            seen.add((rec["decision_id"], rec["action"]))
            new_records.append(rec)

    for prop in pending:
        pid = str(prop.get("id", ""))
        created_at = now_fn(pid)
        try:
            geo, ovl = gates_fn(prop)
            judged = dj.classify(prop, geometry=geo, overlap=ovl)
        except Exception as e:  # noqa: BLE001 — never crash the drain; DLQ + leave pending
            append_jsonl(dlq_path, [{"decision_id": pid, "stage": "classify",
                                     "error": repr(e), "created_at": created_at}])
            left_pending.append(pid)
            continue

        klass = judged["classification"]

        if klass == dj.TASTE_REFUSED:
            _emit(_record(judged, _REFUSE, created_at, eff_caps, corpus_version))
            refused.append(pid)
            continue

        if klass == dj.STRONG_PASS or klass == dj.STRONG_FAIL:
            if n_decisions >= max_dec:               # cap reached -> defer to human
                rec = _record(judged, _PENDING, created_at, eff_caps, corpus_version)
                rec["evidence"] = list(rec["evidence"]) + [
                    f"capped: max_auto_decisions_per_drain={max_dec} atingido"]
                _emit(rec)
                left_pending.append(pid)
                continue
            action = _APPROVE if klass == dj.STRONG_PASS else _REJECT
            try:
                (proposals.approve if action == _APPROVE else proposals.reject)(pid)
            except Exception as e:  # noqa: BLE001
                append_jsonl(dlq_path, [{"decision_id": pid, "stage": "apply",
                                         "action": action, "error": repr(e),
                                         "created_at": created_at}])
                left_pending.append(pid)
                continue
            _emit(_record(judged, action, created_at, eff_caps, corpus_version))
            decided.append({"decision_id": pid, "action": action})
            n_decisions += 1
            continue

        if klass == dj.INVALID:
            _emit(_record(judged, _PENDING, created_at, eff_caps, corpus_version))
            left_pending.append(pid)
            continue

        # ---- BORDERLINE -> gate mode B --------------------------------------
        if gate_fn is None or n_gate_calls >= max_gate:
            rec = _record(judged, _PENDING, created_at, eff_caps, corpus_version)
            note = ("gate desabilitado" if gate_fn is None
                    else f"gate cap atingido (max_gate_calls_per_drain={max_gate})")
            rec["evidence"] = list(rec["evidence"]) + [note]
            _emit(rec)
            left_pending.append(pid)
            continue
        n_gate_calls += 1
        try:
            gr = gate_fn(prop, judged)
        except Exception as e:  # noqa: BLE001 — a gate crash is inconclusive, never fatal
            append_jsonl(dlq_path, [{"decision_id": pid, "stage": "gate",
                                     "error": repr(e), "created_at": created_at}])
            gate_meta = {"trigger": GATE_TRIGGER, "status": "error", "verdict": None,
                         "confidence": None, "applied": None}
            _emit(_record(judged, _ESCALATED, created_at, eff_caps, corpus_version,
                          decided_by="gate_mode_b", gate=gate_meta))
            escalated.append({"decision_id": pid, "status": "error", "applied": None})
            left_pending.append(pid)
            continue

        status = getattr(gr, "status", None)
        verdict = getattr(gr, "verdict", None)
        confidence = getattr(gr, "confidence", None)
        gate_meta = {"trigger": GATE_TRIGGER, "status": status, "verdict": verdict,
                     "confidence": confidence, "applied": None}
        decisive = (status == "ok" and verdict in _GATE_APPLY
                    and confidence in _GATE_OK_CONF)
        if decisive and n_decisions < max_dec:
            action = _GATE_APPLY[verdict]
            gate_meta["applied"] = "approve" if action == _APPROVE else "reject"
            try:
                (proposals.approve if action == _APPROVE else proposals.reject)(pid)
            except Exception as e:  # noqa: BLE001
                append_jsonl(dlq_path, [{"decision_id": pid, "stage": "gate_apply",
                                         "action": action, "error": repr(e),
                                         "created_at": created_at}])
                left_pending.append(pid)
                continue
            _emit(_record(judged, action, created_at, eff_caps, corpus_version,
                          decided_by="gate_mode_b", gate=gate_meta))
            decided.append({"decision_id": pid, "action": action})
            escalated.append({"decision_id": pid, "verdict": verdict,
                              "applied": gate_meta["applied"]})
            n_decisions += 1
            continue

        # inconclusive (MORE-INFO / VISUAL_REVIEW / low conf / offline) OR
        # decision-cap-limited -> stays human, DLQ, 0 retry, NEVER fabricate a verdict
        append_jsonl(dlq_path, [{"decision_id": pid, "stage": "gate",
                                 "status": status, "verdict": verdict,
                                 "confidence": confidence, "created_at": created_at}])
        _emit(_record(judged, _ESCALATED, created_at, eff_caps, corpus_version,
                      decided_by="gate_mode_b", gate=gate_meta))
        escalated.append({"decision_id": pid, "status": status,
                          "verdict": verdict, "applied": None})
        left_pending.append(pid)

    return {"decided": decided, "escalated": escalated, "refused": refused,
            "left_pending": left_pending, "audit_records": new_records}


def _main() -> int:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    summary = drain()
    print(json.dumps({k: (v if k == "audit_records" else v)
                      for k, v in summary.items()
                      if k != "audit_records"}, ensure_ascii=False, indent=2))
    print(f"audit_records={len(summary['audit_records'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
