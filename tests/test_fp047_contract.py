"""FP-047/F1: contrato `room_regression_request.v1` fail-closed e estado final do relatorio (CA-01, CA-05, CA-17, CA-24).

So L1 e puro: nenhum SketchUp, nenhuma geometria. A comparacao de caixas e a F2.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.validation import room_regression as rr

ROOT = Path(__file__).resolve().parents[1]
ROOMS = rr.registry_rooms("planta_74")


def _scoped() -> dict:
    return {
        "schema_version": "room_regression_request.v1",
        "change_id": "fp047-d007-repro-001",
        "base_commit": "23939d9",
        "candidate_commit": "abcdef1",
        "fixture": "planta_74",
        "consensus_path": "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json",
        "pt_to_m": 0.0259,
        "change_mode": "scoped_change",
        "allowed_changes": [{
            "room_key": "r003", "part_keys": ["Guarda-roupa"], "allowed_effects": ["position"],
            "reason": "exemplo sujeito a revisao visual", "spec_rule": "FP-047/R-17", "visual_review_required": True}],
        "control_rooms": ["r004", "r001"],
        "protect_canonicals": True, "require_l2": True, "require_l3_if_visual_changed": True,
    }


def _strict() -> dict:
    c = _scoped()
    c.update(change_mode="strict_identity", allowed_changes=[])
    return c


def _validate(c: dict) -> dict:
    return rr.validate_contract(c, ROOMS, "planta_74")


def test_valid_scoped_contract_resolves_registry_ids_to_box_room_names():
    result = _validate(_scoped())
    assert result["state"] == rr.OK, result
    assert result["rooms"] == {"r003": "SUITE 02", "r004": "COZINHA", "r001": "A.S. | TERRACO SOCIAL | TERRACO TECNICO"}


def test_valid_strict_identity_contract_is_ok():
    assert _validate(_strict())["state"] == rr.OK


@pytest.mark.parametrize("mode", [None, "", "SCOPED_CHANGE", "refactor", 1])
def test_missing_or_unknown_change_mode_is_blocked_never_inferred(mode):
    c = _scoped()
    if mode is None:
        del c["change_mode"]
    else:
        c["change_mode"] = mode
    assert _validate(c)["state"] == rr.BLOCKED_CHANGE_MODE


def test_scoped_change_without_allowed_changes_is_blocked():
    for value in ([], None):
        c = _scoped()
        c["allowed_changes"] = value
        assert _validate(c)["state"] == rr.BLOCKED
    c = _scoped()
    del c["allowed_changes"]
    assert _validate(c)["state"] == rr.BLOCKED


def test_scoped_change_without_specific_parts_or_reason_is_invalid():
    c = _scoped()
    c["allowed_changes"][0]["part_keys"] = []
    assert _validate(c)["state"] == rr.INVALID_CONTRACT
    c = _scoped()
    c["allowed_changes"][0]["reason"] = "x"
    assert _validate(c)["state"] == rr.INVALID_CONTRACT


def test_strict_identity_forbids_allowed_changes():
    c = _strict()
    c["allowed_changes"] = _scoped()["allowed_changes"]
    result = _validate(c)
    assert result["state"] == rr.INVALID_CONTRACT
    assert result["errors"][0]["code"] == "STRICT_IDENTITY_FORBIDS_ALLOWED_CHANGES"


@pytest.mark.parametrize("field,value", [("protect_canonicals", False), ("pt_to_m", 0), ("change_id", "A"),
                                         ("surprise", 1), ("fixture", "")])
def test_invalid_fields_are_rejected(field, value):
    c = _scoped()
    c[field] = value
    assert _validate(c)["state"] == rr.INVALID_CONTRACT


def test_protect_canonicals_cannot_be_omitted():
    c = _scoped()
    del c["protect_canonicals"]
    assert _validate(c)["state"] == rr.INVALID_CONTRACT


@pytest.mark.parametrize("key", ["service", "SUITE 99", "kitchen2", ""])
def test_unresolvable_room_never_skips_the_check(key):
    c = _scoped()
    c["control_rooms"] = [key] if key else ["x"]
    c["control_rooms"] = [key or "x"]
    result = _validate(c)
    assert result["state"] == rr.INVALID_CONTRACT
    assert any(e["code"] in ("UNRESOLVED_ROOM", "SCHEMA") for e in result["errors"])


def test_service_alias_from_the_original_draft_does_not_resolve_but_area_servico_does():
    c = _scoped()
    c["control_rooms"] = ["service"]
    assert _validate(c)["state"] == rr.INVALID_CONTRACT
    c["control_rooms"] = ["area_servico"]
    assert _validate(c)["state"] == rr.OK


def test_display_name_alias_and_room_id_resolve_to_the_same_room():
    for key in ("r003", "suite_02", "SUITE 02"):
        assert rr.resolve_room(key, ROOMS, "planta_74") == "SUITE 02"


def test_control_room_cannot_also_be_allowed_to_change():
    c = _scoped()
    c["control_rooms"] = ["suite_02"]            # mesmo comodo que r003
    result = _validate(c)
    assert result["state"] == rr.INVALID_CONTRACT
    assert result["errors"][0]["code"] == "CONTROL_ROOM_ALSO_ALLOWED"


def test_synthetic_fixture_accepts_only_exact_snapshot_room_names():
    synthetic = {"bedroom_medium_14m2_inner_face"}
    assert rr.resolve_room("bedroom_medium_14m2_inner_face", synthetic, None) == "bedroom_medium_14m2_inner_face"
    with pytest.raises(rr.RoomUnresolved):
        rr.resolve_room("r003", synthetic, None)      # registry da planta_74 nao vale para outra fixture
    with pytest.raises(rr.RoomUnresolved):
        rr.resolve_room("bedroom", synthetic, None)


def test_non_object_contract_is_invalid():
    for bad in (None, [], "x", 3):
        assert rr.validate_contract(bad)["state"] == rr.INVALID_CONTRACT


def test_validator_does_not_mutate_the_contract():
    c = _scoped()
    before = copy.deepcopy(c)
    _validate(c)
    assert c == before


# --- estado final (nunca PASS por prova parcial) ---------------------------------------------------------------------

def _report(**over) -> dict:
    base = {
        "schema_version": "room_regression_report.v1", "change_id": "fp047-x-001", "mode": "scoped_change", "state": "PASS",
        "tests": {"l1": "PASS", "l2": "PASS", "l3": "NOT_APPLICABLE"}, "canonical_hashes_unchanged": True,
        "room_results": [{"room_key": "SUITE 02", "state": "PASS", "allowed_delta_count": 1, "unexpected_delta_count": 0}],
        "evidence": {}, "require_l2": True, "visual_changed": False,
    }
    base.update(over)
    return base


def test_complete_proof_is_the_only_pass():
    assert rr.aggregate_state(_report()) == ("PASS", [])


def test_l1_pass_without_sketchup_is_pending_sketchup_not_pass():
    state, why = rr.aggregate_state(_report(tests={"l1": "PASS", "l2": "NOT_RUN", "l3": "NOT_APPLICABLE"}))
    assert state == "PENDING_SKETCHUP" and why == ["L2_NOT_PROVEN"]


def test_l2_not_required_allows_pass_but_only_when_declared():
    assert rr.aggregate_state(_report(require_l2=False, tests={"l1": "PASS", "l2": "NOT_APPLICABLE", "l3": "NOT_APPLICABLE"}))[0] == "PASS"


def test_changed_appearance_without_human_verdict_is_pending_human():
    assert rr.aggregate_state(_report(visual_changed=True))[0] == "PENDING_HUMAN"
    assert rr.aggregate_state(_report(visual_changed=True, tests={"l1": "PASS", "l2": "PASS", "l3": "APPROVED"}))[0] == "PASS"


def test_rejected_visual_is_rejected_even_with_everything_else_green():
    assert rr.aggregate_state(_report(visual_changed=True, tests={"l1": "PASS", "l2": "PASS", "l3": "REJECTED"}))[0] == "REJECTED"


def test_canonical_change_is_absolute_fail_regardless_of_allowed_changes():
    state, why = rr.aggregate_state(_report(canonical_hashes_unchanged=False))
    assert state == "FAIL" and "CANONICAL_CHANGED" in why


def test_unverified_canonicals_cannot_pass():
    assert rr.aggregate_state(_report(canonical_hashes_unchanged=None))[0] == "BLOCKED"


def test_unexpected_delta_or_failed_room_fails():
    bad = [{"room_key": "COZINHA", "state": "PASS", "allowed_delta_count": 0, "unexpected_delta_count": 2}]
    assert rr.aggregate_state(_report(room_results=bad))[0] == "FAIL"


def test_missing_or_not_run_room_results_block():
    assert rr.aggregate_state(_report(room_results=[]))[0] == "BLOCKED"
    nr = [{"room_key": "COZINHA", "state": "NOT_RUN", "allowed_delta_count": 0, "unexpected_delta_count": 0}]
    assert rr.aggregate_state(_report(room_results=nr))[0] == "BLOCKED"


def test_l1_not_run_blocks_and_explicit_blocked_reasons_win():
    assert rr.aggregate_state(_report(tests={"l1": "NOT_RUN", "l2": "PASS", "l3": "NOT_APPLICABLE"}))[0] == "BLOCKED"
    assert rr.aggregate_state(_report(blocked=["BLOCKED_STALE_VISUAL_EVIDENCE"])) == ("BLOCKED", ["BLOCKED_STALE_VISUAL_EVIDENCE"])


def test_validate_report_rejects_a_declared_pass_the_proofs_do_not_support():
    forged = _report(tests={"l1": "PASS", "l2": "NOT_RUN", "l3": "NOT_APPLICABLE"})      # state continua "PASS"
    errors = rr.validate_report(forged)
    assert any("PASS declarado" in e for e in errors), errors
    assert rr.validate_report(_report()) == []


def test_spec_example_report_is_schema_valid_and_not_pass():
    report = {
        "schema_version": "room_regression_report.v1", "change_id": "fp047-d007-repro-001", "mode": "scoped_change",
        "state": "PENDING_SKETCHUP", "base_commit": "23939d9", "candidate_commit": None, "input_sha256": None,
        "canonical_hashes_unchanged": None,
        "room_results": [{"room_key": "SUITE 02", "state": "NOT_RUN", "allowed_delta_count": 0, "unexpected_delta_count": 0}],
        "tests": {"l1": "NOT_RUN", "l2": "PENDING_SKETCHUP", "l3": "PENDING_HUMAN"},
        "evidence": {"out_skp": None, "output_sha256": None, "sketchup_version": None},
    }
    assert rr.validate_report(report) == []
    assert rr.aggregate_state(report)[0] == "BLOCKED"


def test_cli_exit_codes(tmp_path):
    def run(contract):
        f = tmp_path / "c.json"
        f.write_text(json.dumps(contract), encoding="utf-8")
        return subprocess.run([sys.executable, "-m", "tools.validation.room_regression", "validate-contract", str(f)],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8").returncode

    assert run(_scoped()) == 0
    broken = _scoped()
    broken["control_rooms"] = ["service"]
    assert run(broken) == 1
    nomode = _scoped()
    del nomode["change_mode"]
    assert run(nomode) == 3
