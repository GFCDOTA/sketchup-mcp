"""Semi-autonomous pipeline (commit 3) — auto_decider carteiro (no gate yet).

Hermetic: a FakeProposals double (pending/approve/reject in memory), gates and
created_at injected, audit/DLQ in tmp_path. Locks: auto-approve of a clean
program, auto-reject of a FAIL, refuse-taste (machine never touches), the caps
param, idempotent re-run, append-only audit valid against the schema, and the
RAIL (no human-verdict literal, no human decided_by).
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools.interior_studio import auto_decider as ad
from tools.interior_studio import decision_judge as dj

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "decision_audit_record.schema.json"
FIXED_NOW = lambda pid: "2026-01-01T00:00:00Z"  # noqa: E731 — deterministic clock


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class FakeProposals:
    """In-memory stand-in for tools.interior_studio.proposals (no disk)."""

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


def _program(pid, items, env="sala", area=14.0):
    return {"id": pid, "type": "furniture_program", "environment": env,
            "room_id": pid.split("_")[-1], "room_name": "SALA",
            "area_m2": area, "items": items}


def _clean(pid="furniture_program_r002"):
    return _program(pid, [{"asset": "sofa", "priority": "core"}])


def _broken(pid="furniture_program_r003"):
    return _program(pid, [{"asset": "cama"}, {"asset": "sofa"}])


def _taste_gap(pid="gap_estilo_r004"):
    return {"id": pid, "type": "consistency_gap", "kind": "intern_estilo",
            "intern": "estilo", "severity": "med", "title": "cozinha — estilo WARN",
            "detail": "item fora do DNA"}


def _drain(props, tmp_path, **kw):
    kw.setdefault("gates_fn", lambda p: ("PASS", "PASS"))
    kw.setdefault("now_fn", FIXED_NOW)
    return ad.drain(proposals=props, out_dir=tmp_path, **kw)


# ---- the three actions ---------------------------------------------------


def test_clean_program_is_auto_approved(tmp_path, validator):
    props = FakeProposals([_clean()])
    res = _drain(props, tmp_path)
    assert res["decided"] == [{"decision_id": "furniture_program_r002",
                               "action": "auto_approve"}]
    assert "furniture_program_r002" in props.approved
    assert "furniture_program_r002" not in props.pending
    rec = res["audit_records"][0]
    validator.validate(rec)
    assert rec["classification"] == dj.STRONG_PASS
    assert rec["decided_by"] == "auto_decider"
    assert rec["created_at"] == "2026-01-01T00:00:00Z"


def test_fail_program_is_auto_rejected(tmp_path, validator):
    props = FakeProposals([_broken()])
    res = _drain(props, tmp_path)
    assert res["decided"][0]["action"] == "auto_reject"
    assert "furniture_program_r003" in props.rejected
    validator.validate(res["audit_records"][0])
    assert res["audit_records"][0]["classification"] == dj.STRONG_FAIL


def test_taste_gap_is_refused_and_never_touched(tmp_path, validator):
    props = FakeProposals([_taste_gap()])
    res = _drain(props, tmp_path)
    assert res["refused"] == ["gap_estilo_r004"]
    assert res["decided"] == []
    # NEVER moved out of pending — the machine does not act on taste
    assert "gap_estilo_r004" in props.pending
    assert "gap_estilo_r004" not in props.approved
    assert "gap_estilo_r004" not in props.rejected
    rec = res["audit_records"][0]
    validator.validate(rec)
    assert rec["action"] == "refused_taste"
    assert rec["decided_by"] == "auto_decider"


def test_borderline_program_left_pending_when_gate_disabled(tmp_path, validator):
    # clean interns but the injected overlap gate WARNs -> borderline; with the
    # gate disabled it simply stays pending (gated behaviour is commit-4 tests)
    props = FakeProposals([_clean("furniture_program_r002")])
    res = _drain(props, tmp_path, gates_fn=lambda p: ("PASS", "WARN"),
                 use_gate=False)
    assert res["left_pending"] == ["furniture_program_r002"]
    assert "furniture_program_r002" in props.pending
    rec = res["audit_records"][0]
    validator.validate(rec)
    assert rec["classification"] == dj.BORDERLINE
    assert rec["action"] == "left_pending"
    assert any("gate desabilitado" in e for e in rec["evidence"])


# ---- caps ----------------------------------------------------------------


def test_caps_param_limits_decisions(tmp_path, validator):
    props = FakeProposals([_clean(f"furniture_program_r00{i}") for i in range(5)])
    res = _drain(props, tmp_path, caps={"max_auto_decisions_per_drain": 2})
    assert len(res["decided"]) == 2
    assert len(res["left_pending"]) == 3
    # the 3 deferred ones stayed pending and carry a "capped" note
    assert len(props.approved) == 2
    capped = [r for r in res["audit_records"] if r["action"] == "left_pending"]
    assert len(capped) == 3
    for r in capped:
        validator.validate(r)
        assert any("capped" in e for e in r["evidence"])
        assert r["classification"] == dj.STRONG_PASS   # would-decide, but capped


def test_env_cap_is_read(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTO_DECIDER_MAX_DECISIONS", "1")
    props = FakeProposals([_clean(f"furniture_program_r00{i}") for i in range(3)])
    res = _drain(props, tmp_path)
    assert len(res["decided"]) == 1
    assert res["audit_records"][0]["caps_snapshot"]["max_auto_decisions_per_drain"] == 1


# ---- idempotency ---------------------------------------------------------


def test_rerun_does_not_redecide(tmp_path):
    props = FakeProposals([_clean(), _taste_gap()])
    first = _drain(props, tmp_path)
    assert len(first["decided"]) == 1 and first["refused"] == ["gap_estilo_r004"]
    audit_lines_1 = (tmp_path / ad.AUDIT_NAME).read_text("utf-8").splitlines()
    # second pass: approved one has left pending; taste re-seen but deduped
    second = _drain(props, tmp_path)
    assert second["decided"] == []                      # nothing new decided
    assert second["audit_records"] == []                # deduped, nothing appended
    audit_lines_2 = (tmp_path / ad.AUDIT_NAME).read_text("utf-8").splitlines()
    assert audit_lines_2 == audit_lines_1               # append-only, no growth


def test_audit_is_append_only_and_valid(tmp_path, validator):
    props = FakeProposals([_clean(), _broken(), _taste_gap()])
    _drain(props, tmp_path)
    lines = (tmp_path / ad.AUDIT_NAME).read_text("utf-8").splitlines()
    assert len(lines) == 3
    for ln in lines:
        rec = json.loads(ln)
        validator.validate(rec)
        assert rec["decided_by"] in ("auto_decider", "gate_mode_b")


# ---- the RAIL ------------------------------------------------------------


def test_auto_decider_never_writes_human_verdict():
    src = inspect.getsource(ad)
    assert not re.search(r"['\"](IMPROVED|SAME|WORSE)['\"]", src)
    assert "human_verdict" not in src


def test_no_audit_record_is_ever_decided_by_a_human(tmp_path):
    props = FakeProposals([_clean(), _broken(), _taste_gap()])
    res = _drain(props, tmp_path)
    for rec in res["audit_records"]:
        assert rec["decided_by"] != "Felipe"
        assert rec["decided_by"] in ("auto_decider", "gate_mode_b")
