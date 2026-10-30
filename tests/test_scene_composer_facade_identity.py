"""R6 (#463): o SceneComposer vive em tools.orchestration.scene_composer; interior.composer.scene_composer e fachada de mesma identidade."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# SHA-256 de compose_scene(intent) gerados ANTES da movimentacao (develop@2e9aea9): a cena nao pode mudar.
GOLDEN = {
    "living_room_black_wood_gold_boutique.json": "057942447216556fcf16ce1a06e914b86cb69045738487f504b4ec2e1e3cc488",
    "living_room_modern_warm_minimal.json": "789592284d36676bcd36bd3c0ca8f98235631b6d48eabfd9ea058dc532c96a83",
}


def test_legacy_module_is_the_very_same_module_as_the_new_owner():
    assert importlib.import_module("interior.composer.scene_composer") is importlib.import_module("tools.orchestration.scene_composer")


def test_root_still_points_at_the_repository_after_the_move():
    from tools.orchestration.scene_composer import ROOT
    assert Path(ROOT).resolve() == REPO and (REPO / "interior/style_packs").is_dir()


@pytest.mark.parametrize("name", sorted(GOLDEN))
def test_composed_scene_is_byte_identical_to_the_pre_move_output(name):
    from tools.orchestration.scene_composer import compose_scene
    scene = compose_scene(json.loads((REPO / "fixtures/scene_intents" / name).read_text("utf-8")))
    assert hashlib.sha256(json.dumps(scene, sort_keys=True, default=str).encode()).hexdigest() == GOLDEN[name]


def test_facade_holds_no_logic_and_production_consumers_use_the_new_owner():
    text = (REPO / "interior/composer/scene_composer.py").read_text("utf-8")
    assert "importlib.import_module(_TARGET)" in text and len(text.splitlines()) < 30
    for rel in ("tools/validation/scene_spatial_gate.py", "tools/rooms/bathroom/capabilities/estudio_banheiro_scene.py"):
        assert "interior.composer" not in (REPO / rel).read_text("utf-8")
