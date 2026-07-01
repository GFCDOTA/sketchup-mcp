"""FP-038 Fatia 0 — bbox por comodo + config de cameras (Python puro, sem SketchUp)."""
from __future__ import annotations

import json
from pathlib import Path

from tools.material_review import (
    OUT_DIR,
    ROOM_CAMERAS,
    build_cameras_env,
    group_name,
    output_path,
    room_bbox,
    validate_cameras,
)

ROOT = Path(__file__).resolve().parents[1]


def _box(room, module, x0, y0, x1, y1):
    return {"room": room, "module": module, "kind": "top",
            "corners": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            "x0": x0, "y0": y0, "x1": x1, "y1": y1}


# boxes sinteticos espelhando os nomes reais da planta_74 (do log FP-036)
_BOXES = [
    _box("SALA DE JANTAR | SALA DE ESTAR", "Sofa", 100, 100, 300, 250),
    _box("SALA DE JANTAR | SALA DE ESTAR", "Rack TV", 320, 110, 480, 200),
    _box("COZINHA", "sink_module", 900, 500, 1000, 620),
    _box("SUITE 01", "Cama", 600, 900, 800, 1100),
]


def test_group_name_matches_rb_convention():
    assert group_name(_BOXES[0]) == "SALA DE JANTAR | SALA DE ESTAR · Sofa"
    assert group_name({"kind": "x"}) == "Apto · x"


def test_room_bbox_from_boxes():
    living = room_bbox(_BOXES, "SALA")
    assert living == (100.0, 100.0, 480.0, 250.0)   # sofa + rack, so da sala
    kitchen = room_bbox(_BOXES, "COZINHA")
    assert kitchen == (900.0, 500.0, 1000.0, 620.0)


def test_living_bbox_excludes_kitchen():
    living = room_bbox(_BOXES, "SALA")
    kitchen = room_bbox(_BOXES, "COZINHA")
    # a sala nao pode engolir a cozinha (comodos disjuntos)
    assert living[2] < kitchen[0] or living[0] > kitchen[2] or living[3] < kitchen[1]


def test_sofa_closeup_isolates_sofa_module():
    bb = room_bbox(_BOXES, "· Sofa")
    assert bb == (100.0, 100.0, 300.0, 250.0)        # so o sofa, nao o rack


def test_room_bbox_none_when_no_match():
    assert room_bbox(_BOXES, "GARAGEM") is None


def test_room_cameras_config_valid():
    assert validate_cameras() == []


def test_output_paths_predictable():
    names = {c["name"]: output_path(c).name for c in ROOM_CAMERAS}
    assert names["living"] == "living_material_proof.png"
    assert names["kitchen"] == "kitchen_material_proof.png"
    assert names["bedroom"] == "bedroom_material_proof.png"
    assert names["living_sofa_closeup"] == "living_sofa_closeup.png"
    for c in ROOM_CAMERAS:
        assert output_path(c).parent == OUT_DIR


def test_build_cameras_env_absolute_paths():
    payload = json.loads(build_cameras_env())
    assert len(payload) == len(ROOM_CAMERAS)
    for p in payload:
        assert p["out"].endswith(".png") and "/" in p["out"]         # path absoluto forward-slash
        assert "material_review/" in p["out"]                        # sob material_review/
        assert set(p) >= {"name", "match", "mode", "exclude", "out"}


# ---- CONTRATO-TEXTO do .rb (nao roda headless aqui) — FLAG: confirmar imagens em build SU real ----
def test_material_review_rb_contract():
    rb = (ROOT / "tools/material_review.rb").read_text("utf-8")
    assert "view.write_image" in rb, "o .rb precisa renderizar cada camera"
    assert "MR_CAMERAS" in rb and "MR_LOG" in rb, ".rb nao le o contrato de ENV"
    assert "g.hidden = !keep" in rb, "o .rb precisa esconder moveis de outros comodos (isolar)"
    assert "MR_SHELL_PREFIXES" in rb and "g.hidden = true" in rb, \
        "o .rb precisa esconder TODO o shell (sem oclusao de parede)"
    assert "ex.none?" in rb, "o .rb precisa excluir os modulos pedidos do frame"
    assert "view.zoom(shown" in rb, "o .rb precisa enquadrar so os moveis visiveis"
    assert "g.hidden = false" in rb, "o .rb precisa restaurar a visibilidade entre cameras"
    assert "model.save" not in rb, "o .rb NAO pode salvar o .skp (so renderiza)"
