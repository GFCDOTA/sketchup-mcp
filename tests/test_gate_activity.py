"""Visibilidade operacional do gate: fonte REAL (audit vs legacy) + estado honesto.

Os classificadores sao PUROS (recebem timestamps), entao testam a decisao sem
depender de I/O. test_activity_summary_contract roda contra o repo real (smoke).

Roda com pytest OU direto:  python tests/test_gate_activity.py   (da raiz do repo)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root no sys.path
from tools.claude_bridge.server import (  # noqa: E402
    _classify_gate_source, _classify_gate_state, activity_summary,
    GATE_IDLE_WARN_SEC, GATE_IDLE_BAD_SEC,
)

NOW = 1_000_000_000.0
H = 3600


# ---- fonte do gate (audit.jsonl vs questions/responses legacy) ----
def test_source_audit_newer_than_legacy_is_stale():
    # audit recente + legacy velho (>1h) -> mixed e legacy marcada STALE
    src, stale = _classify_gate_source(NOW, NOW - 100 * H)
    assert src == "mixed" and stale is True

def test_source_legacy_fresh_not_stale():
    src, stale = _classify_gate_source(NOW, NOW - 60)  # 1 min < margem
    assert src == "mixed" and stale is False

def test_source_audit_only():
    assert _classify_gate_source(NOW, None) == ("audit.jsonl", False)

def test_source_legacy_fallback_only():
    assert _classify_gate_source(None, NOW) == ("questions/responses legacy", False)

def test_source_unavailable_when_no_source():
    assert _classify_gate_source(None, None) == ("unavailable", False)

def test_source_legacy_newer_than_audit_not_stale():
    src, stale = _classify_gate_source(NOW - 100 * H, NOW)
    assert src == "mixed" and stale is False


# ---- estado honesto do gate (UP/DOWN nao basta) ----
def test_state_unknown_when_no_consult():
    assert _classify_gate_state(True, None, NOW, 0, 0, False) == ("UNKNOWN", "warn")

def test_state_down():
    assert _classify_gate_state(False, NOW, NOW, 0, 0, False) == ("DOWN", "bad")

def test_state_active_when_recent():
    assert _classify_gate_state(True, NOW - H, NOW, 0, 0, False) == ("ONLINE_ACTIVE", "ok")

def test_state_idle_warn_after_24h():
    st, sev = _classify_gate_state(True, NOW - (GATE_IDLE_WARN_SEC + H), NOW, 0, 0, False)
    assert (st, sev) == ("ONLINE_IDLE", "warn")

def test_state_idle_bad_after_72h():
    st, sev = _classify_gate_state(True, NOW - (GATE_IDLE_BAD_SEC + H), NOW, 0, 0, False)
    assert (st, sev) == ("ONLINE_IDLE", "bad")

def test_state_blocked_on_pending():
    assert _classify_gate_state(True, NOW - H, NOW, 1, 0, False) == ("BLOCKED", "bad")

def test_state_blocked_on_stalled():
    assert _classify_gate_state(True, NOW - H, NOW, 0, 2, False) == ("BLOCKED", "bad")

def test_state_stale_source_flagged_even_when_recent():
    assert _classify_gate_state(True, NOW - H, NOW, 0, 0, True) == ("STALE_SOURCE", "warn")


# ---- contrato do /api/activity (smoke contra o repo real) ----
def test_activity_summary_contract():
    a = activity_summary()
    req = ["gate_state", "gate_state_sev", "last_activity_age_sec", "last_gate_consult_age_sec",
           "last_gate_response_age_sec", "gate_idle_age_sec", "gate_source", "gate_source_stale",
           "stale_reason", "active_sessions_now", "stalled_sessions_now", "last_artifact_age_sec",
           "thresholds"]
    for k in req:
        assert k in a, "faltou chave: " + k
    assert a["gate_state"] in ("ONLINE_ACTIVE", "ONLINE_IDLE", "STALE_SOURCE", "BLOCKED", "DOWN", "UNKNOWN")
    assert a["gate_state_sev"] in ("ok", "warn", "bad")
    assert a["gate_source"] in ("audit.jsonl", "questions/responses legacy", "mixed", "unavailable")


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    ok = fail = 0
    for f in fns:
        try:
            f(); print("PASS", f.__name__); ok += 1
        except Exception:
            print("FAIL", f.__name__); traceback.print_exc(); fail += 1
    print("\n%d passed, %d failed" % (ok, fail))
    sys.exit(1 if fail else 0)
