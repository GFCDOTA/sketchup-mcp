"""Testes de contrato do track Intent-to-Scene (slice 1):
schemas executaveis, decor builders, SceneComposer, SceneSpatialGate, harness.
Tudo SU-free e deterministico.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/scene_intents/living_room_modern_warm_minimal.json"

from interior.composer.scene_composer import (compose_scene, load_style_pack,   # noqa: E402
                                              place_parts, validate_furniture_intent,
                                              validate_scene_intent)
from interior.validators.scene_spatial_gate import _sabotages, scene_spatial_gate  # noqa: E402
from tools.decor_anatomy_spec import (DECOR_PLAUSIBLE_BBOX_M,                  # noqa: E402
                                      DECOR_REQUIRED_PARTS)
from tools.decor_builders import BUILDERS, build_decor                          # noqa: E402


@pytest.fixture(scope="module")
def intent():
    return json.loads(FIXTURE.read_text("utf-8"))


@pytest.fixture(scope="module")
def scene(intent):
    return compose_scene(intent)


# ------------------------------------------------------------------ schemas
def test_schema_files_parse():
    for name in ("scene_intent.schema.json", "furniture_intent.schema.json"):
        s = json.loads((ROOT / "interior/schemas" / name).read_text("utf-8"))
        assert s["type"] == "object" and s["required"]


def test_fixture_is_valid_scene_intent(intent):
    assert validate_scene_intent(intent) == []


def test_invalid_intents_are_rejected(intent):
    bad = copy.deepcopy(intent)
    del bad["hero_piece"]
    assert any("hero_piece" in e for e in validate_scene_intent(bad))

    bad = copy.deepcopy(intent)
    bad["openings"][0]["center_along_m"] = 99.0
    assert any("nao cabe" in e for e in validate_scene_intent(bad))

    bad = copy.deepcopy(intent)
    bad["furniture_intents"][0]["priority"] = 0
    assert any("priority" in e for e in validate_scene_intent(bad))

    bad = copy.deepcopy(intent)
    bad["room_dimensions"]["main_wall"] = "northeast"
    assert any("main_wall" in e for e in validate_scene_intent(bad))

    assert validate_furniture_intent({"type": "hammock", "role": "hero", "priority": 1})


def test_style_pack_contract():
    sp = load_style_pack("modern_warm_minimal")
    mats = sp["materials"]
    fab = mats["hero_fabric"]["rgb"]
    # invariante: charcoal QUENTE — furniture_visual_gate exige max-min >= 12
    assert max(fab) - min(fab) >= 12
    # todo role referenciado em material_defaults existe em materials
    refs = set()
    for v in sp["material_defaults"].values():
        refs.update(v.values() if isinstance(v, dict) else [v])
    assert refs <= set(mats), refs - set(mats)
    assert abs(sum(c["weight"] for c in sp["palette"]) - 1.0) < 0.01


# ------------------------------------------------------------------ builders
@pytest.mark.parametrize("kind", sorted(BUILDERS))
def test_decor_builder_contract(kind):
    parts, meta = build_decor(kind)
    kinds = {p["kind"] for p in parts}
    assert set(DECOR_REQUIRED_PARTS[kind]) <= kinds
    assert len(parts) >= 2, "anti bloco unico"
    for p in parts:
        assert len(p["rgb"]) == 3
        assert p["x1"] > p["x0"] and p["y1"] > p["y0"] and p["z1"] > p["z0"]
    (wlo, whi), (dlo, dhi), (hlo, hhi) = DECOR_PLAUSIBLE_BBOX_M[kind]
    w, d, h = meta["bbox_m"]
    assert wlo <= w <= whi and dlo <= d <= dhi and hlo <= h <= hhi


def test_place_parts_rotation_exact():
    parts = [{"label": "a", "kind": "k", "x0": 0.0, "y0": 0.0, "x1": 2.0, "y1": 1.0,
              "z0": 0.0, "z1": 0.5, "rgb": [1, 2, 3],
              "verts8": [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0),
                         (0, 0, 0.5), (2, 0, 0.5), (2, 1, 0.5), (0, 1, 0.5)]}]
    out = place_parts(parts, 90, (5.0, 5.0), z_off=0.1)
    p = out[0]
    # 2x1 girado 90 -> 1x2, centrado em (5,5), z deslocado
    assert (p["x1"] - p["x0"], p["y1"] - p["y0"]) == (1.0, 2.0)
    assert (p["x0"] + p["x1"]) / 2 == 5.0 and (p["y0"] + p["y1"]) / 2 == 5.0
    assert p["z0"] == 0.1 and p["z1"] == 0.6
    assert all(p["x0"] <= v[0] <= p["x1"] and p["y0"] <= v[1] <= p["y1"]
               for v in p["verts8"])
    with pytest.raises(ValueError):
        place_parts(parts, 45, (0, 0))


# ------------------------------------------------------------------ composer
def test_compose_scene_deterministic(intent):
    a = compose_scene(intent)
    b = compose_scene(intent)
    assert json.dumps(a["placements"], sort_keys=True) == \
        json.dumps(b["placements"], sort_keys=True)
    assert a["camera"] == b["camera"]


def test_composition_rules_satisfied(scene):
    d = scene["report"]["distances"]
    assert 0.35 <= d["coffee_table_gap_m"] <= 0.45
    assert all(o > 0 for o in d["rug_overhang_m"])
    assert abs(d["art_offset_along_m"]) <= 0.05
    assert 0.10 <= d["art_gap_above_hero_m"] <= 0.45
    assert abs(d["curtain_window_offset_m"]) <= 0.05
    types = {p["type"] for p in scene["placements"]}
    assert types == {fi["type"] for fi in scene["intent"]["furniture_intents"]}


def test_camera_keeps_window_wall_visible(scene):
    win_wall = scene["openings"][0]["wall"]
    assert win_wall not in scene["camera"]["hide_walls"]


def test_room_shell_preserves_sill_and_header(scene):
    """janela tem peitoril + verga (Hard Rule #2 espelhada na cena sintetica)."""
    east = [p for p in scene["parts"] if str(p["label"]).startswith("wall_east")]
    win = next(o for o in scene["openings"] if o["type"] == "window")
    sill = [p for p in east if p["z1"] == pytest.approx(win["sill_m"])
            and p["z0"] == pytest.approx(0.0)]
    head = [p for p in east if p["z0"] == pytest.approx(win["head_m"])]
    assert sill and head


# ------------------------------------------------------------------ gate
def test_gate_passes_canonical_scene(scene):
    r = scene_spatial_gate(scene, scene["parts"])
    assert r["result"] == "PASS", r["why"]
    assert all(r["checks"].values())


@pytest.mark.parametrize("idx", range(6))
def test_gate_fails_sabotages(scene, idx):
    name, expect, s = _sabotages(scene)[idx]
    r = scene_spatial_gate(s, None)
    assert r["result"] == expect, f"{name}: esperado {expect}, veio {r['result']} {r['why']}"


# ------------------------------------------------------------------ harness
def test_render_harness_smoke(tmp_path, scene):
    pytest.importorskip("matplotlib")
    from interior.composer.scene_composer import write_scene
    from tools.render_scene_views import render_views, scene_boxes
    out = write_scene(scene, tmp_path / "scene")
    m = render_views(out, su="off")
    for k in ("top_view", "three_quarter", "contact_sheet"):
        assert m["views"][k] and Path(m["views"][k]).exists()
    assert m["sketchup"]["status"] == "off"
    boxes = scene_boxes(scene["parts"])
    assert all(b["h_in"] > 0 and len(b["corners"]) == 4 for b in boxes)
