"""FP-033 — finding_router unit tests (pure, no SKP build)."""
from __future__ import annotations

import pytest

from tools import finding_router as fr


def _f(type_, **kw):
    return {"type": type_, "severity": "FAIL", "source": "deterministic",
            "evidence": "x", **kw}


# --- deterministic autofix ------------------------------------------------


@pytest.mark.parametrize("t", sorted(fr.AUTOFIX_TYPES))
def test_autofix_types_route_to_autofix(t):
    assert fr.classify(_f(t)) == fr.DETERMINISTIC_AUTOFIX


def test_routes_furniture_overlap_to_autofix():
    assert fr.classify(_f("furniture_overlap")) == fr.DETERMINISTIC_AUTOFIX


# --- appearance -> Felipe (never auto) ------------------------------------


@pytest.mark.parametrize("t", [
    "floating_door", "orphan_glass", "orphan_glass_panel", "bad_window_aperture",
    "position_fidelity", "misplaced_window", "full_height_window_void",
    "misplaced_soft_barrier", "missing_wall_continuation", "global_visual_fail",
])
def test_routes_appearance_types_to_felipe(t):
    assert fr.classify(_f(t, source="claude_bridge")) == fr.NEEDS_FELIPE


def test_appearance_verdict_is_never_auto():
    # even if some future caller mislabels it, the hard guard holds
    assert fr.classify(_f("appearance_verdict")) == fr.NEEDS_FELIPE
    assert fr.classify(_f("APPEARANCE_VERDICT")) == fr.NEEDS_FELIPE


# --- qualitative -> vision -------------------------------------------------


@pytest.mark.parametrize("t", ["global_visual", "scale_rotation", "wall_stub"])
def test_routes_global_visual_to_vision(t):
    assert fr.classify(_f(t, source="claude_bridge")) == fr.NEEDS_VISION


def test_visual_axis_routes_to_vision_even_with_unknown_type():
    # a finding on a qualitative axis routes to vision by axis
    assert fr.classify(_f("something_new", axis="global_visual")) == fr.NEEDS_VISION
    assert fr.classify(_f("something_new", axis="scale_rotation")) == fr.NEEDS_VISION


@pytest.mark.parametrize("t,axis", [
    ("wall_stub", None), ("global_visual", None), ("scale_rotation", None),
    ("something_new", "global_visual"),
])
def test_eye_confirmed_finding_never_routes_back_to_vision(t, axis):
    # anti-ping-pong: o que o próprio olho confirmou (source_check
    # visual_oracle) não volta pra fila do olho — vai pro humano
    f = _f(t, source="claude_bridge", source_check="visual_oracle")
    if axis:
        f["axis"] = axis
    assert fr.classify(f) == fr.NEEDS_FELIPE


# --- safe default ----------------------------------------------------------


def test_unknown_type_defaults_to_felipe_never_autofix():
    r = fr.classify(_f("brand_new_never_seen_type"))
    assert r == fr.NEEDS_FELIPE
    assert r != fr.DETERMINISTIC_AUTOFIX


def test_empty_or_malformed_finding_is_felipe():
    assert fr.classify({}) == fr.NEEDS_FELIPE
    assert fr.classify({"type": None}) == fr.NEEDS_FELIPE


# --- structural guarantees -------------------------------------------------


def test_every_route_is_a_valid_enum():
    for t in ["furniture_overlap", "global_visual", "floating_door", "???"]:
        assert fr.classify(_f(t)) in fr.ROUTES


def test_no_appearance_type_is_ever_autofix():
    for t in fr.NEEDS_FELIPE_TYPES:
        assert fr.classify(_f(t)) != fr.DETERMINISTIC_AUTOFIX


def test_autofix_and_felipe_sets_are_disjoint():
    assert not (fr.AUTOFIX_TYPES & fr.NEEDS_FELIPE_TYPES)
    assert not (fr.AUTOFIX_TYPES & fr.NEEDS_VISION_TYPES)


def test_classified_fills_route_without_mutating_input():
    src = [_f("furniture_overlap"), _f("floating_door")]
    src_copy = [dict(x) for x in src]
    out = fr.classified(src)
    assert [o["route"] for o in out] == [fr.DETERMINISTIC_AUTOFIX, fr.NEEDS_FELIPE]
    assert src == src_copy  # inputs untouched


def test_route_reason_is_nonempty_for_each_route():
    for t in ["furniture_overlap", "global_visual", "floating_door"]:
        assert fr.route_reason(_f(t)).strip()
