"""docs/specs/INDEX.md redireciona as SPECs que foram para o Plan2Space/engineering-specs; inventado continua falhando."""
from pathlib import Path

from tools.validation import spec_index as si

ROOT = Path(__file__).resolve().parents[1]

INDEX = """# Índice

SHA: `0123456789abcdef0123456789abcdef01234567`

| Caminho antigo | Caminho em engineering-specs |
|---|---|
| `docs/specs/FP-999_demo.md` | `sketchup-mcp/docs-specs/FP-999_demo.md` |
| `.claude/specs/x.md` | `sketchup-mcp/claude-specs/x.md` |
"""


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs/specs").mkdir(parents=True)
    (tmp_path / "docs/specs/INDEX.md").write_text(INDEX, encoding="utf-8")
    (tmp_path / "docs/specs/data.v1.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_moved_spec_resolves_and_invented_path_does_not(tmp_path):
    root = _repo(tmp_path)
    assert si.resolves("docs/specs/FP-999_demo.md", root)
    assert si.resolves("docs/specs/FP-999_demo.md#secao", root)
    assert si.resolves("docs/specs/data.v1.json", root)          # arquivo que ficou no produto
    assert not si.resolves("docs/specs/NAO_EXISTE.md", root)
    assert not si.resolves("", root)


def test_url_is_pinned_to_the_index_sha(tmp_path):
    root = _repo(tmp_path)
    assert si.pinned_sha(root) == "0123456789abcdef0123456789abcdef01234567"
    assert si.url(".claude/specs/x.md", root) == (
        "https://github.com/Plan2Space/engineering-specs/blob/0123456789abcdef0123456789abcdef01234567"
        "/sketchup-mcp/claude-specs/x.md")
    assert si.url("docs/specs/NAO_EXISTE.md", root) is None


def test_spec_names_feed_spec_labels(tmp_path):
    assert si.spec_names(_repo(tmp_path)) == {"FP-999_demo.md", "x.md"}


def test_without_index_nothing_is_redirected(tmp_path):
    assert si.moved_specs(tmp_path) == {}
    assert not si.resolves("docs/specs/FP-999_demo.md", tmp_path)


def test_local_text_reads_only_from_a_real_checkout(tmp_path, monkeypatch):
    root = _repo(tmp_path / "repo")
    clone = tmp_path / "clone"
    (clone / "sketchup-mcp/docs-specs").mkdir(parents=True)
    (clone / "sketchup-mcp/README.md").write_text("mapa", encoding="utf-8")
    (clone / "sketchup-mcp/docs-specs/FP-999_demo.md").write_text("texto", encoding="utf-8")
    monkeypatch.setenv("ENGINEERING_SPECS_DIR", str(clone))
    assert si.local_text("docs/specs/FP-999_demo.md", root) == "texto"
    assert si.local_text(".claude/specs/x.md", root) is None      # indexada, mas ausente no clone
    monkeypatch.setenv("ENGINEERING_SPECS_DIR", str(tmp_path / "nada"))
    assert si.local_text("docs/specs/FP-999_demo.md", root) is None


def test_real_index_maps_every_removed_spec_and_pins_a_sha():
    moved = si.moved_specs(ROOT)
    assert len(moved) == 82 and si.pinned_sha(ROOT)
    assert all(old.endswith(".md") and not (ROOT / old).exists() for old in moved)
    assert {old.split("/", 1)[0] for old in moved} == {"docs", ".claude", "interior"}
