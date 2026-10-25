"""FP-055 P1/P3 (#423 #424 #425 #427): o caminho legado nao escreve no oficial sem flag, nao pula o pre-voo e nao descarta/ignora em silencio."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.sketchup.output_policy import OfficialWriteBlocked, is_official, resolve_output_dir

ROOT = Path(__file__).resolve().parents[1]


def test_official_folders_need_the_flag_and_scratch_does_not():
    default = ROOT / "runs/x"
    assert resolve_output_dir(ROOT, None, default) == default.resolve()
    with pytest.raises(OfficialWriteBlocked):
        resolve_output_dir(ROOT, "artifacts/planta_74/furnished", default)
    with pytest.raises(OfficialWriteBlocked):
        resolve_output_dir(ROOT, ROOT / "fixtures/planta_74", default)
    assert resolve_output_dir(ROOT, "artifacts/planta_74/furnished", default, allow_official_write=True).name == "furnished"
    assert is_official(ROOT / "artifacts/a", ROOT) and not is_official(ROOT / "runs/a", ROOT)
    assert not is_official(ROOT.parent / "artifacts/a", ROOT)           # fora do repo nao e o oficial do repo


# --- daqui para baixo: importa o orquestrador legado (planta_74), processo proprio com PT_TO_M=0.0259 ----------------
planta = pytest.mark.planta74_scale


@planta
def test_legacy_default_output_is_scratch_and_the_official_folder_is_refused_without_the_flag(tmp_path, capsys):
    from tools.orchestration import furnish_apartment as fa
    assert "runs" in fa.DEFAULT_OUT_DIR.parts and not is_official(fa.DEFAULT_OUT_DIR, fa.ROOT)
    with pytest.raises(SystemExit) as exc:
        fa.main(["--out-dir", "artifacts/planta_74/furnished"])
    assert exc.value.code == 2 and "BLOQUEADO" in capsys.readouterr().out


@planta
def test_legacy_entrypoint_runs_the_mandatory_preflight_and_never_launches_sketchup_when_it_blocks(tmp_path, monkeypatch, capsys):
    from tools.orchestration import furnish_apartment as fa
    from tools.validation import layout_preflight
    monkeypatch.setattr(fa, "collect_boxes", lambda con: ([{"room": "X"}], [("r0", "X", "service", "OK", 1)]))
    monkeypatch.setattr(layout_preflight, "preflight", lambda con, boxes, rooms, twin=None: {
        "status": "FAIL", "rooms": [], "blocking": [{"room_id": "r0", "gate": "room_collisions", "status": "FAIL",
                                                      "reasons": {"barrier_penetration": ["h_sb001:Jardineira"]}}]})
    monkeypatch.setattr(fa.subprocess, "Popen", lambda *a, **k: pytest.fail("SketchUp lancado apesar do pre-voo FAIL"))
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as exc:
        fa.main(["--out-dir", str(out)])
    assert exc.value.code == 1 and "PRE-VOO FAIL" in capsys.readouterr().out
    assert not out.exists()                    # nada gravado antes do pre-voo passar


@planta
def test_wet_room_guard_blocks_instead_of_only_logging(monkeypatch):
    import json

    from tools.orchestration import furnish_apartment as fa
    from tools.rooms.bathroom import validation as bv
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    monkeypatch.setattr(bv, "unexpected_wet_room_kinds", lambda boxes: ["sofa"])
    with pytest.raises(fa.WetRoomViolation, match="sofa"):
        fa.collect_boxes_ex(con)


@planta
def test_functional_interfaces_declared_by_the_brains_are_surfaced_not_dropped():
    import contextlib
    import io
    import json

    from tools.orchestration import furnish_apartment as fa
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, summary, interfaces = fa.collect_boxes_ex(con)
        legacy_boxes, legacy_summary = fa.collect_boxes(con)
    assert interfaces and {"r005", "r006", "r007"} <= set(interfaces)             # banhos e lavabo declaram F1C
    assert len(boxes) == len(legacy_boxes) and summary == legacy_summary          # o retorno legado nao mudou


@planta
def test_bake_theme_refuses_the_official_folder_without_the_flag(monkeypatch):
    from tools.rooms.kitchen.capabilities import bake_theme
    monkeypatch.setenv("BAKE_OUT_DIR", "artifacts/planta_74/furnished")
    monkeypatch.delenv("BAKE_ALLOW_OFFICIAL_WRITE", raising=False)
    monkeypatch.setattr(bake_theme, "launch_owned", lambda *a, **k: pytest.fail("SketchUp lancado"))
    with pytest.raises(OfficialWriteBlocked):
        bake_theme.main()


# --- FP-055 #490: nenhum escritor NOVO de pasta oficial passa em silencio ---------------------------------------------------
# Escritores conhecidos que ainda definem a saida em artifacts/, com o motivo (so PNG de revisao/render, nunca .skp canonico):
_OFFICIAL_OUTPUT_ALLOWLIST = {
    "tools/rendering/material_review.py": "PNG de revisao de material (nao grava .skp)",
    "tools/rendering/batch_theme_render.py": "le kitchen_angles (entrada), nao grava .skp",
    "tools/rooms/kitchen/capabilities/vray.py": "render V-Ray em kitchen_angles (PNG)",
    "tools/orchestration/furnish_apartment.py": "OFFICIAL_OUT_DIR so com --allow-official-write",
}


def test_no_tool_defines_an_official_output_dir_without_going_through_the_policy():
    import ast

    names = {"OUT_DIR", "OUTPUT_DIR", "OUT"}
    offenders = []
    for path in sorted((ROOT / "tools").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in _OFFICIAL_OUTPUT_ALLOWLIST:
            continue
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets):
                if any(isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.startswith(("artifacts/", "fixtures/"))
                       and not c.value.startswith("artifacts/review")          # evidencia datada: pasta propria para isso
                       for c in ast.walk(node.value)):
                    offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, f"escritor de pasta oficial fora da politica de saida: {offenders}"


def test_bedroom_designer_refuses_the_official_folder_without_the_flag(monkeypatch):
    from tools.rooms.bedroom import designer
    monkeypatch.setattr("sys.argv", ["designer", "--synthetic", "--out-dir", "artifacts/planta_74/furnished"])
    with pytest.raises(SystemExit) as exc:
        designer.main()
    assert "BLOQUEADO" in str(exc.value)
