"""Indice dos modulos de comodo na raiz: gerado das fontes reais e sem drift (README e tools/rooms/README.md)."""
from __future__ import annotations

from tools.navigation import rooms_index as ri


def test_committed_index_matches_the_sources():
    """Mudou perfil, catalogo, lacuna, fragmento ou arquivo de um comodo? Rodar `python -m tools.navigation.rooms_index --write`."""
    for path, text in ri.targets().items():
        assert path.read_bytes().decode("utf-8") == text, f"{path.name} desatualizado: rodar rooms_index --write"


def test_every_room_module_is_listed_with_its_folder_and_capability_states():
    data = ri.collect()
    assert list(data["rooms"]) == list(ri.ORDER)
    block = ri.render_root(data)
    for room in ri.ORDER:
        assert f"`tools/rooms/{room}/`" in block
    kitchen = data["rooms"]["kitchen"]
    assert {c["validation"] for c in kitchen["capabilities"]} >= {"L2_PASS"}
    assert {g["binding"] for g in kitchen["gaps"]} >= {"bind.kitchen.drawer", "bind.kitchen.countertop"}


def test_splice_is_idempotent_and_keeps_the_rest_of_the_readme():
    readme = "# t\n\nintro\n\n## Rodar\n\ncomandos\n"
    once = ri.splice(readme, ri.BEGIN + "\nX\n" + ri.END)
    assert ri.splice(once, ri.BEGIN + "\nX\n" + ri.END) == once
    assert once.startswith("# t\n\nintro") and once.endswith("## Rodar\n\ncomandos\n")
    assert ri.splice(once, ri.BEGIN + "\nY\n" + ri.END).count("Y") == 1


def test_every_tracked_root_entry_has_a_declared_role():
    """Complementa o guard da FP-044: alem de nao crescer, a raiz se explica (entrada sem papel = decidir antes de manter)."""
    block = ri.render_layout()
    assert "SEM PAPEL DEFINIDO" not in block
    assert "`scripts/`" not in block and "`docker-compose.yml`" not in block          # D-005 / D-002 resolvidas
    stale = sorted(set(ri.ROOT_ROLES) - {line.split("`")[1].rstrip("/") for line in block.splitlines() if line.startswith("| `")})
    assert stale == [], f"papel declarado para entrada que nao existe mais: {stale}"
