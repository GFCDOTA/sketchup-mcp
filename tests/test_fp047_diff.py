"""FP-047/F2: snapshot e diff semantico por comodo/peca + autorizacao pelo contrato (CA-02..CA-08, CA-24, CA-28).

L1 puro sobre caixas sinteticas (sem SketchUp, sem arquivo canonico). A captura real da planta_74 roda na escala dela.
"""
import copy

import pytest

from tools.validation import room_regression as rr
from tools.validation import room_regression_diff as rd

PT_TO_M = 0.0259
CM_IN = 1 / 2.54


def _box(room, module, label, x0, y0, w=20.0, d=10.0, h=30.0, **extra):
    box = {"kind": label, "x0": x0, "y0": y0, "x1": x0 + w, "y1": y0 + d, "corners": [[x0, y0], [x0 + w, y0], [x0 + w, y0 + d], [x0, y0 + d]],
           "h_in": h, "rgb": [10, 20, 30], "label": label, "ambiguous": False, "decorative": False, "room": room, "module": module,
           "geometry_intent": "FURNITURE", "interaction_policy": {"circulation": "BLOCKING", "furniture_overlap": "EXCLUSIVE"},
           "host": {"relationship": "NONE"}, "z0_in": 0.0}
    box.update(extra)
    return box


def _boxes():
    return [_box("SUITE 02", "Guarda-roupa", "wardrobe", 100, 100), _box("SUITE 02", "Cama", "bed", 200, 100, w=60, d=80),
            _box("COZINHA", "Pia", "sink", 10, 10), _box("COZINHA", "Geladeira", "fridge", 50, 10, w=30, d=30, h=70)]


def _snap(boxes, fixture="synthetic", scale=PT_TO_M):
    return rd.snapshot(boxes, fixture=fixture, pt_to_m=scale)


def _contract(mode="scoped_change", **over):
    c = {"schema_version": "room_regression_request.v1", "change_id": "fp047-test-001", "fixture": "synthetic", "pt_to_m": PT_TO_M,
         "change_mode": mode, "control_rooms": ["COZINHA"], "protect_canonicals": True, "require_l2": False,
         "require_l3_if_visual_changed": True}
    if mode == "scoped_change":
        c["allowed_changes"] = [{"room_key": "SUITE 02", "part_keys": ["Guarda-roupa"], "allowed_effects": ["position"],
                                 "reason": "mover o guarda-roupa (teste)", "spec_rule": "FP-047/R-17", "visual_review_required": True}]
    c.update(over)
    return c


def _moved(dx_cm=0.0, dy_cm=0.0, module="Guarda-roupa"):
    boxes = _boxes()
    for b in boxes:
        if b["module"] == module:
            dx, dy = dx_cm * CM_IN, dy_cm * CM_IN
            b["x0"] += dx
            b["x1"] += dx
            b["y0"] += dy
            b["y1"] += dy
            b["corners"] = [[x + dx, y + dy] for x, y in b["corners"]]
    return boxes


def _compare(after_boxes, contract=None, **kw):
    return rd.compare(_snap(_boxes()), _snap(after_boxes), contract or _contract(), **kw)


def _canon(sha="a" * 64):
    return {"artifacts/planta_74/planta_74.skp": sha}


# --- snapshot -----------------------------------------------------------------------------------------------------------

def test_snapshot_is_deterministic_and_independent_of_dict_key_order():
    a = _snap(_boxes())
    shuffled = [dict(reversed(list(b.items()))) for b in _boxes()]
    assert a == _snap(shuffled) == _snap(_boxes())
    assert a["part_count"] == 4 and a["rooms"] == ["COZINHA", "SUITE 02"]


def test_duplicate_identity_groups_are_counted_not_hidden():
    boxes = _boxes() + [_box("SUITE 02", "Guarda-roupa", "wardrobe", 400, 100)]
    snap = _snap(boxes)
    assert snap["ambiguous_groups"] == 1
    assert [p["occurrence"] for p in snap["parts"] if p["group"][1] == "Guarda-roupa"] == [0, 1]


def test_snapshots_of_different_scale_or_fixture_are_incomparable():
    with pytest.raises(ValueError):
        rd.diff(_snap(_boxes(), scale=0.0259), _snap(_boxes(), scale=0.0352))
    with pytest.raises(ValueError):
        rd.diff(_snap(_boxes(), fixture="a"), _snap(_boxes(), fixture="b"))


# --- diff semantico -----------------------------------------------------------------------------------------------------

def test_identical_snapshots_have_no_delta_and_reorder_is_harmless():
    assert rd.diff(_snap(_boxes()), _snap(_boxes())) == []
    assert rd.diff(_snap(_boxes()), _snap(list(reversed(_boxes())))) == []


def test_swapping_two_identical_key_parts_is_harmless_but_moving_one_is_one_delta():
    twin = [_box("SUITE 02", "Cadeira", "leg", 10, 10), _box("SUITE 02", "Cadeira", "leg", 90, 10)]
    base = _snap(twin)
    assert rd.diff(base, _snap(list(reversed(twin)))) == []
    moved = [copy.deepcopy(twin[0]), _box("SUITE 02", "Cadeira", "leg", 95, 10)]
    deltas = rd.diff(base, _snap(moved))
    assert len(deltas) == 1 and deltas[0]["effects"] == ["position"]


def test_a_4_5_cm_move_is_a_position_delta_far_above_float_noise():
    deltas = rd.diff(_snap(_boxes()), _snap(_moved(dx_cm=4.5)))
    assert len(deltas) == 1
    d = deltas[0]
    assert (d["room"], d["module"], d["effects"]) == ("SUITE 02", "Guarda-roupa", ["position"])
    assert {"x0", "x1", "corners"} <= set(d["fields_changed"])


def test_float_noise_below_epsilon_is_not_a_delta_but_a_millimeter_is():
    noisy = _boxes()
    noisy[0]["x0"] += 1e-9
    assert rd.diff(_snap(_boxes()), _snap(noisy)) == []
    assert len(rd.diff(_snap(_boxes()), _snap(_moved(dx_cm=0.1)))) == 1


def test_resize_is_size_and_anchored_resize_is_size_plus_position():
    sym = _boxes()
    sym[0]["x0"] -= 2
    sym[0]["x1"] += 2
    assert rd.diff(_snap(_boxes()), _snap(sym))[0]["effects"] == ["size"]
    anch = _boxes()
    anch[0]["x1"] += 4
    assert rd.diff(_snap(_boxes()), _snap(anch))[0]["effects"] == ["position", "size"]


@pytest.mark.parametrize("field,value,effect", [
    ("rgb", [1, 2, 3], "material"), ("mat_name", "mdf", "material"),
    ("geometry_intent", "STRUCTURAL", "intent"), ("host", {"relationship": "WALL"}, "intent"),
    ("decorative", True, "tag"), ("product", "x", "tag"), ("unknown_new_field", 1, "tag"),
])
def test_same_bbox_with_different_material_intent_or_tag_is_still_a_delta(field, value, effect):
    after = _boxes()
    after[0][field] = value
    deltas = rd.diff(_snap(_boxes()), _snap(after))
    assert len(deltas) == 1 and deltas[0]["effects"] == [effect], deltas


def test_renaming_a_room_to_escape_the_comparison_shows_as_removed_plus_added():
    after = _boxes()
    for b in after:
        if b["room"] == "SUITE 02":
            b["room"] = "SUITE 03"
    kinds = sorted((d["room"], d["kind"]) for d in rd.diff(_snap(_boxes()), _snap(after)))
    assert kinds == [("SUITE 02", "removed")] * 2 + [("SUITE 03", "added")] * 2


# --- autorizacao pelo contrato ------------------------------------------------------------------------------------------

def test_strict_identity_fails_on_any_box_change_with_room_and_part():
    report = _compare(_moved(dx_cm=4.5), _contract("strict_identity"), l1_gates="PASS", canonical_before=_canon(), canonical_after=_canon())
    assert report["state"] == "FAIL"
    suite = next(r for r in report["room_results"] if r["room_key"] == "SUITE 02")
    assert suite["state"] == "FAIL" and suite["deltas"][0]["authorization"] == rd.BASELINE_MISMATCH
    assert suite["deltas"][0]["module"] == "Guarda-roupa"


def test_strict_identity_passes_only_with_every_proof():
    kw = dict(canonical_before=_canon(), canonical_after=_canon())
    clean = _compare(_boxes(), _contract("strict_identity"), l1_gates="PASS", **kw)
    assert clean["state"] == "PASS" and rr.validate_report(clean) == []
    assert _compare(_boxes(), _contract("strict_identity"), **kw)["state"] == "BLOCKED"           # L1 (F3) ainda nao rodou
    assert _compare(_boxes(), _contract("strict_identity"), l1_gates="PASS")["state"] == "BLOCKED"  # canonicos nao verificados


def test_authorized_move_is_clean_but_pending_human_because_appearance_changed():
    report = _compare(_moved(dx_cm=10), l1_gates="PASS", canonical_before=_canon(), canonical_after=_canon())
    assert report["visual_changed"] is True and report["state"] == "PENDING_HUMAN"
    suite = next(r for r in report["room_results"] if r["room_key"] == "SUITE 02")
    assert (suite["allowed_delta_count"], suite["unexpected_delta_count"]) == (1, 0)
    approved = _compare(_moved(dx_cm=10), l1_gates="PASS", l3="APPROVED", canonical_before=_canon(), canonical_after=_canon())
    assert approved["state"] == "PASS"


def test_change_in_unlisted_part_of_an_allowed_room_is_unauthorized_part_delta():
    report = _compare(_moved(dx_cm=10, module="Cama"), l1_gates="PASS", canonical_before=_canon(), canonical_after=_canon())
    assert report["state"] == "FAIL"
    bad = [d for r in report["room_results"] for d in r["deltas"] if d["authorization"]]
    assert [d["authorization"] for d in bad] == [rd.UNAUTHORIZED_PART_DELTA]


def test_change_in_a_control_or_unlisted_room_is_unauthorized_room_delta():
    report = _compare(_moved(dx_cm=10, module="Pia"), l1_gates="PASS", canonical_before=_canon(), canonical_after=_canon())
    assert report["state"] == "FAIL"
    cozinha = next(r for r in report["room_results"] if r["room_key"] == "COZINHA")
    assert cozinha["role"] == "control" and cozinha["deltas"][0]["authorization"] == rd.UNAUTHORIZED_ROOM_DELTA


def test_effect_outside_the_allowlist_is_unauthorized_even_on_the_allowed_part():
    after = _boxes()
    after[0]["rgb"] = [200, 0, 0]                           # so 'position' foi autorizado
    report = _compare(after, l1_gates="PASS", canonical_before=_canon(), canonical_after=_canon())
    assert report["state"] == "FAIL"
    assert any(d["authorization"] == rd.UNAUTHORIZED_EFFECT_DELTA for r in report["room_results"] for d in r["deltas"])


def test_move_plus_material_change_needs_both_effects_authorized():
    after = _moved(dx_cm=10)
    after[0]["rgb"] = [200, 0, 0]
    contract = _contract()
    contract["allowed_changes"][0]["allowed_effects"] = ["position", "material"]
    assert _compare(after, contract, l1_gates="PASS", canonical_before=_canon(), canonical_after=_canon())["state"] == "PENDING_HUMAN"


def test_added_and_removed_parts_need_explicit_effects():
    added = _boxes() + [_box("SUITE 02", "Guarda-roupa", "extra", 300, 300)]
    assert _compare(added, l1_gates="PASS", canonical_before=_canon(), canonical_after=_canon())["state"] == "FAIL"
    contract = _contract()
    contract["allowed_changes"][0]["allowed_effects"] = ["added"]
    ok = _compare(added, contract, l1_gates="PASS", canonical_before=_canon(), canonical_after=_canon())
    assert ok["state"] == "PENDING_HUMAN"


def test_canonical_change_is_absolute_fail_even_when_every_box_delta_is_authorized():
    report = _compare(_moved(dx_cm=10), l1_gates="PASS", l3="APPROVED", canonical_before=_canon("a" * 64), canonical_after=_canon("b" * 64))
    assert report["state"] == "FAIL" and "CANONICAL_CHANGED" in report["reasons"]


def test_nothing_in_a_listed_room_is_skipped_when_only_the_synthetic_may_change():
    only_synth = _contract(allowed_changes=[{"room_key": "SUITE 03", "part_keys": ["Cama"], "allowed_effects": ["position"],
                                             "reason": "apenas a sintetica pode mudar", "spec_rule": "FP-047/R-05",
                                             "visual_review_required": False}])
    report = _compare(_moved(dx_cm=10), only_synth, l1_gates="PASS")
    assert report["state"] == "BLOCKED" and any("UNRESOLVED_ROOM" in b for b in report["blocked"])   # SUITE 03 nem existe


def test_invalid_or_blocked_contract_yields_blocked_report_without_comparing():
    for bad in ({"change_mode": None}, {"allowed_changes": []}, {"control_rooms": ["NAO EXISTE"]}):
        report = _compare(_moved(dx_cm=50), _contract(**bad), l1_gates="PASS")
        assert report["state"] == "BLOCKED" and report["room_results"] == []
        assert rr.validate_report(report) == []


def test_run_twice_gives_the_same_report():
    args = dict(l1_gates="PASS", canonical_before=_canon(), canonical_after=_canon())
    assert _compare(_moved(dx_cm=10), **args) == _compare(_moved(dx_cm=10), **args)


# --- captura real (escala da planta_74, processo isolado) ---------------------------------------------------------------

@pytest.mark.planta74_scale
def test_real_planta74_snapshot_is_deterministic_and_matches_registry_rooms():
    from core.domain.room_registry import rooms_for_project

    a, b = rd.capture(), rd.capture()
    assert a == b and a["part_count"] == 402 and a["pt_to_m"] == 0.0259
    assert set(a["rooms"]) == {r.display_name for r in rooms_for_project("planta_74")}      # CA-24: nenhum comodo sem correspondencia
    assert a["ambiguous_groups"] > 0 and len(a["source_digests"]) == 5
    assert rd.diff(a, b) == []
    report = rd.compare(a, b, {**_contract("strict_identity"), "fixture": "planta_74", "control_rooms": ["r004"]},
                        canonical_before=a["source_digests"], canonical_after=b["source_digests"], l1_gates="PASS")
    assert report["state"] == "PASS" and rr.validate_report(report) == []


def test_capture_refuses_another_scale_in_the_same_process():
    from core.scale import PT_TO_M

    if abs(PT_TO_M - rd.PLANTA_74_PT_TO_M) < 1e-12:
        pytest.skip("processo ja esta na escala da planta_74")
    with pytest.raises(RuntimeError, match="PT_TO_M"):
        rd.capture()
