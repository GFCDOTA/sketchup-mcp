"""Contract tests do gate hidráulico encapsulado por kitchen."""
from unittest.mock import Mock

import pytest

from tools.rooms.kitchen.validation import require_kitchen_anchor, validate_kitchen_anchor


def test_pass_calls_legacy_validator_once(monkeypatch, capsys):
    import tools.rooms.kitchen.anchor_rules as legacy
    report = {"result": "PASS", "lines": ["KITCHEN_VALIDATION:"],
              "checks": {"sink_wall": "LEFT"}}
    mock = Mock(return_value=report)
    monkeypatch.setattr(legacy, "validate", mock)
    con = {"rooms": []}
    assert require_kitchen_anchor(con, "r004") is report
    mock.assert_called_once_with(con, "r004")
    assert "kitchen_validation => PASS" in capsys.readouterr().out


def test_failure_blocks_render_and_preserves_reason(monkeypatch):
    import tools.rooms.kitchen.anchor_rules as legacy
    monkeypatch.setattr(legacy, "validate", lambda *args: {
        "result": "FAIL", "lines": [], "checks": {"sink_wall": "RIGHT"}
    })
    with pytest.raises(SystemExit, match="cozinha reprovou o anchor da pia \\(RIGHT\\)"):
        require_kitchen_anchor({}, "r004")


def test_boundary_is_thin_adapter(monkeypatch):
    import tools.rooms.kitchen.anchor_rules as legacy
    report = {"result": "PASS", "lines": [], "checks": {}}
    monkeypatch.setattr(legacy, "validate", lambda *_: report)
    assert validate_kitchen_anchor({}, "r004") is report
