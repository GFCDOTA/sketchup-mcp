"""FP-042 P3: planners de quarto com fonte única sem mudar a API legada."""
import ast
from pathlib import Path

from tools.rooms.bedroom import designer as bedroom_designer
from tools.rooms.bedroom import layout as bedroom_layout
from tools.rooms.bedroom import designer, layout
from tools.rooms.shared import geometry


def test_bedroom_layout_legacy_aliases():
    assert bedroom_layout.run is layout.run
    assert bedroom_layout.plot is layout.plot
    assert bedroom_layout.main is layout.main
    assert bedroom_layout._headboard_candidates is layout._headboard_candidates
    assert bedroom_layout._fbox is geometry._fbox
    assert bedroom_layout._wall_setup is geometry._wall_setup


def test_bedroom_designer_legacy_aliases():
    assert bedroom_designer.run is designer.run
    assert bedroom_designer._items_to_boxes is designer._items_to_boxes
    assert bedroom_designer.build_layout is designer.build_layout
    assert bedroom_designer.build_skp is designer.build_skp
    assert bedroom_designer._window_zones is geometry._window_zones


def test_designer_path_and_same_room_imports():
    root = Path(__file__).resolve().parents[1]
    assert Path(designer.__file__).resolve().parents[3] == root
    source = Path(designer.__file__).read_text("utf-8")
    assert "from tools.rooms.bedroom.layout import _headboard_candidates, wall_footprint" in source
    assert "root = Path(__file__).resolve().parents[3]" in source


def test_owners_hold_the_implementation_and_the_cli():
    # as fachadas bedroom_layout/bedroom_designer sairam na FP-044/F6; o dono tem a implementacao e a CLI
    for owner, names in ((layout, ("run", "plot", "main")), (designer, ("run", "build_layout", "build_skp"))):
        tree = ast.parse(Path(owner.__file__).read_text("utf-8"))
        defs = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert set(names) <= defs
        assert "if __name__ == \"__main__\":" in Path(owner.__file__).read_text("utf-8")
