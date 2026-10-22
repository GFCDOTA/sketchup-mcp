"""`tools.navigation.register_evidence`: registro FP-042 sem edicao manual — num repo git temporario, nunca nos manifestos reais."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.navigation import register_evidence as reg


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    specs = tmp_path / "docs/specs"
    specs.mkdir(parents=True)
    doc = {"path": "docs/a.md", "domain": "documentation_or_agent", "disposition": "retain_path_with_explicit_owner",
           "phase": "P5", "status": "VERIFIED_PATH_BASED_OWNER_CLASSIFICATION", "document_owner": "project_documentation"}
    old = {"path": "artifacts/review/x/old.json", **reg.P6_CANONICAL}
    for name, key, rows in ((reg.INVENTORY, "entries", [doc, old]), (reg.REFERENCES, "entries", []), (reg.ASSETS, "assets", [])):
        text = json.dumps({"schema_version": "t", key: rows}, indent=2, ensure_ascii=False) + "\n"
        (tmp_path / name).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))     # CRLF como os manifestos reais
    return tmp_path


def _write(repo: Path, rel: str, data: bytes) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_bytes(data)
    _git(repo, "add", rel)


def _load(repo: Path, name: str) -> dict:
    return json.loads((repo / name).read_bytes().decode("utf-8"))


def test_evidence_goes_to_inventory_references_and_binary_also_to_assets(repo):
    _write(repo, "artifacts/review/x/new/README.md", b"# prova\n")
    _write(repo, "artifacts/review/x/new/top.png", b"\x89PNG fake")
    report = reg.register(repo, ["artifacts/review/x/new/README.md", "artifacts/review/x/new/top.png"])
    assert [r["inventory"] for r in report] == ["added", "added"] and report[1]["assets"] == "added" and "assets" not in report[0]
    inv = [e["path"] for e in _load(repo, reg.INVENTORY)["entries"]]
    assert inv.index("artifacts/review/x/new/README.md") == inv.index("artifacts/review/x/old.json") + 1   # junto do vizinho
    refs = {e["path"]: e for e in _load(repo, reg.REFERENCES)["entries"]}
    sha = _git(repo, "ls-files", "-s", "artifacts/review/x/new/README.md").split()[1]
    assert refs["artifacts/review/x/new/README.md"] == {"path": "artifacts/review/x/new/README.md", "blob_sha": sha,
                                                        "blob_size": 8, "owner_group": "artifacts"}
    assert b"\r\n" in (repo / reg.INVENTORY).read_bytes()                                                 # preserva CRLF


def test_rerun_is_idempotent_and_refreshes_the_blob_after_an_edit(repo):
    _write(repo, "artifacts/review/x/new/README.md", b"v1\n")
    reg.register(repo, ["artifacts/review/x/new/README.md"])
    before = (repo / reg.INVENTORY).read_bytes()
    assert reg.register(repo, ["artifacts/review/x/new/README.md"])[0] == {
        "path": "artifacts/review/x/new/README.md", "inventory": "unchanged", "references": "unchanged"}
    _write(repo, "artifacts/review/x/new/README.md", b"v2 maior\n")
    assert reg.register(repo, ["artifacts/review/x/new/README.md"])[0]["references"] == "refreshed"
    assert (repo / reg.INVENTORY).read_bytes() == before
    assert len(_load(repo, reg.REFERENCES)["entries"]) == 1


def test_like_copies_the_classification_and_keeps_dot_directories(repo):
    _write(repo, ".claude/skills/s/SKILL.md", b"x")
    row = reg.register(repo, ["./.claude/skills/s/SKILL.md"], like="docs/a.md")[0]
    assert row == {"path": ".claude/skills/s/SKILL.md", "inventory": "added"}                          # doc: nao vira P6
    entry = next(e for e in _load(repo, reg.INVENTORY)["entries"] if e["path"] == ".claude/skills/s/SKILL.md")
    assert entry["document_owner"] == "project_documentation" and entry["phase"] == "P5"


@pytest.mark.parametrize("paths, like, msg", [
    (["docs/novo.md"], None, "exige --like"),
    (["artifacts/review/x/fora_do_indice.md"], None, "git add"),
    (["artifacts/review/x/nao_existe.md"], None, "nao existe"),
    (["docs/novo.md"], "docs/nao_inventariado.md", "path modelo"),
])
def test_refuses_instead_of_guessing(repo, paths, like, msg):
    (repo / "docs/novo.md").write_text("x", encoding="utf-8")
    (repo / "artifacts/review/x").mkdir(parents=True)
    (repo / "artifacts/review/x/fora_do_indice.md").write_text("x", encoding="utf-8")
    before = {n: (repo / n).read_bytes() for n in (reg.INVENTORY, reg.REFERENCES, reg.ASSETS)}
    with pytest.raises(reg.RegistrationError, match=msg):
        reg.register(repo, paths, like=like)
    assert {n: (repo / n).read_bytes() for n in before} == before                                       # nada escrito
