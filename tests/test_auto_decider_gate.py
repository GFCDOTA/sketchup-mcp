"""Semi-autonomous pipeline (commit 4) — BORDERLINE -> gate mode B.

Hermetic: the gate is either an injected fake (GateResult-shaped SimpleNamespace)
or the real default with ``probe_bridge`` stubbed offline. No network. Locks:
GO/NO-GO applies (decided_by=gate_mode_b), the deterministic evidence travels in
the gate context, offline degrades to left_pending + DLQ with NO fabricated
verdict, inconclusive verdicts back off, and max_gate_calls_per_drain cuts.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from tools import ask_gpt_gate as agg
from tools.interior_studio import auto_decider as ad
from tools.interior_studio import decision_judge as dj

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "decision_audit_record.schema.json"
FIXED_NOW = lambda pid: "2026-01-01T00:00:00Z"  # noqa: E731


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


class FakeProposals:
    def __init__(self, pending):
        self.pending = {p["id"]: p for p in pending}
        self.approved: dict = {}
        self.rejected: dict = {}

    def state(self):
        return {"pending": list(self.pending.values()),
                "approved": list(self.approved.values()),
                "rejected": list(self.rejected.values())}

    def approve(self, pid):
        p = self.pending.pop(pid, None)
        if p is not None:
            self.approved[pid] = p
        return p

    def reject(self, pid):
        p = self.pending.pop(pid, None)
        if p is not None:
            self.rejected[pid] = p
        return p


def _borderline(pid="furniture_program_r002", area=3.0):
    # sofa in a tiny sala -> capacidade WARN (carries a fill%) -> BORDERLINE
    return {"id": pid, "type": "furniture_program", "environment": "sala",
            "room_id": "r002", "room_name": "SALA", "area_m2": area,
            "items": [{"asset": "sofa", "priority": "core"}]}


def _gr(status="ok", verdict="GO", confidence="high"):
    return SimpleNamespace(status=status, verdict=verdict, confidence=confidence)


def _drain(props, tmp_path, gate_fn, **kw):
    return ad.drain(proposals=props, out_dir=tmp_path, now_fn=FIXED_NOW,
                    gates_fn=kw.pop("gates_fn", lambda p: ("PASS", "PASS")),
                    gate_fn=gate_fn, **kw)


# ---- the deterministic evidence travels in the gate context --------------


def test_gate_context_carries_gates_fill_and_evidence():
    judged = dj.classify(_borderline(), geometry="PASS", overlap="PASS")
    assert judged["classification"] == dj.BORDERLINE
    ctx = ad._gate_context(_borderline(), judged)
    assert ctx["judge_verdicts"]["geometry_sanity"] == "PASS"
    assert ctx["fill_pct"] == 60                       # ~60% do piso, surfaced
    assert any("piso" in e for e in ctx["deterministic_evidence"])
    assert ctx["decision_type"] == "furniture_program"


def test_borderline_escalates_with_evidence_and_go_applies(tmp_path, validator):
    seen = {}

    def spy(prop, judged):
        seen["ctx"] = ad._gate_context(prop, judged)
        return _gr("ok", "GO", "high")

    props = FakeProposals([_borderline()])
    res = _drain(props, tmp_path, spy)
    assert seen["ctx"]["fill_pct"] == 60               # evidence reached the gate
    assert res["decided"] == [{"decision_id": "furniture_program_r002",
                               "action": "auto_approve"}]
    assert "furniture_program_r002" in props.approved
    rec = res["audit_records"][0]
    validator.validate(rec)
    assert rec["decided_by"] == "gate_mode_b"
    assert rec["classification"] == dj.BORDERLINE
    assert rec["gate"]["verdict"] == "GO" and rec["gate"]["applied"] == "approve"
    assert res["escalated"][0]["applied"] == "approve"


def test_gate_no_go_rejects(tmp_path, validator):
    props = FakeProposals([_borderline()])
    res = _drain(props, tmp_path, lambda p, j: _gr("ok", "NO-GO", "high"))
    assert res["decided"][0]["action"] == "auto_reject"
    assert "furniture_program_r002" in props.rejected
    validator.validate(res["audit_records"][0])
    assert res["audit_records"][0]["gate"]["applied"] == "reject"
    assert res["audit_records"][0]["decided_by"] == "gate_mode_b"


# ---- offline / inconclusive: never fabricate, stays human ----------------


def test_gate_offline_leaves_pending_and_dlqs_without_fabricating(tmp_path,
                                                                  monkeypatch):
    # stub the REAL default gate's probe as offline -> run_gate returns
    # SKIPPED_OFFLINE (no verdict); the carteiro must not invent one.
    monkeypatch.setattr(agg, "probe_bridge", lambda url=agg.BRIDGE_URL:
                        (False, "stub offline"))
    props = FakeProposals([_borderline()])
    res = ad.drain(proposals=props, out_dir=tmp_path, now_fn=FIXED_NOW,
                   gates_fn=lambda p: ("PASS", "PASS"),
                   questions_dir=tmp_path / "q", responses_dir=tmp_path / "r")
    assert res["decided"] == []
    assert res["left_pending"] == ["furniture_program_r002"]
    assert "furniture_program_r002" in props.pending
    rec = res["audit_records"][0]
    assert rec["action"] == "escalated_gate"
    assert rec["decided_by"] == "gate_mode_b"
    assert rec["gate"]["verdict"] is None              # NOT fabricated
    assert "SKIPPED_OFFLINE" in (res["escalated"][0]["status"] or "")
    # DLQ recorded, question file written (evidence forwarded even when offline)
    dlq = (tmp_path / ad.DLQ_NAME).read_text("utf-8").splitlines()
    assert dlq and json.loads(dlq[0])["stage"] == "gate"
    qfiles = list((tmp_path / "q").glob("*objective_gate_borderline*.md"))
    assert qfiles and "fill_pct" in qfiles[0].read_text("utf-8")


def test_visual_review_verdict_backs_off_to_pending(tmp_path):
    props = FakeProposals([_borderline()])
    res = _drain(props, tmp_path, lambda p, j: _gr("ok", "VISUAL_REVIEW", "high"))
    assert res["decided"] == []
    assert res["left_pending"] == ["furniture_program_r002"]
    assert res["audit_records"][0]["action"] == "escalated_gate"


def test_low_confidence_go_is_inconclusive(tmp_path):
    props = FakeProposals([_borderline()])
    res = _drain(props, tmp_path, lambda p, j: _gr("ok", "GO", "low"))
    assert res["decided"] == []
    assert res["audit_records"][0]["action"] == "escalated_gate"


# ---- caps ----------------------------------------------------------------


def test_max_gate_calls_cuts(tmp_path, validator):
    calls = {"n": 0}

    def spy(prop, judged):
        calls["n"] += 1
        return _gr("ok", "GO", "high")

    props = FakeProposals([_borderline(f"furniture_program_r00{i}")
                           for i in range(3)])
    res = _drain(props, tmp_path, spy, caps={"max_gate_calls_per_drain": 1})
    assert calls["n"] == 1                              # only one gate call spent
    assert len(res["decided"]) == 1
    capped = [r for r in res["audit_records"] if r["action"] == "left_pending"]
    assert len(capped) == 2
    for r in capped:
        validator.validate(r)
        assert any("gate cap" in e for e in r["evidence"])
        assert r["decided_by"] == "auto_decider"       # never reached the gate


# ---- the RAIL ------------------------------------------------------------


def test_every_gate_record_is_machine_decided(tmp_path, validator):
    props = FakeProposals([_borderline()])
    res = _drain(props, tmp_path, lambda p, j: _gr("ok", "GO", "high"))
    for rec in res["audit_records"]:
        validator.validate(rec)
        assert rec["decided_by"] in ("auto_decider", "gate_mode_b")
        assert rec["decided_by"] != "Felipe"
