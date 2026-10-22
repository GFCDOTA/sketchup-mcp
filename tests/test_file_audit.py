"""Auditoria por arquivo + revisao de imports: logica num repo git sintetico; trava de imports no repo real."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.navigation import file_audit as fa

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "tools/__init__.py": "",
    "tools/rooms/__init__.py": "",
    "tools/rooms/kitchen/__init__.py": "",
    "tools/rooms/kitchen/used.py": "def f():\n    return 1\n",
    "tools/rooms/kitchen/user.py": "from tools.rooms.kitchen.used import f\n\n\ndef g():\n    return f()\n",
    "tools/rooms/kitchen/cli_doc.py": "def main():\n    pass\n\n\nif __name__ == '__main__':\n    main()\n",
    "tools/rooms/kitchen/cli_ci.py": "def main():\n    pass\n\n\nif __name__ == '__main__':\n    main()\n",
    "tools/rooms/kitchen/orphan.py": "def lonely():\n    return 0\n",
    "tools/rooms/kitchen/cyc_a.py": "from tools.rooms.kitchen import cyc_b  # noqa: F401\n",
    "tools/rooms/kitchen/cyc_b.py": "from tools.rooms.kitchen import cyc_a  # noqa: F401\n",
    "tools/rooms/kitchen/broken.py": "from tools.nao_existe import x  # noqa: F401\n",
    "tools/rooms/kitchen/optional.py": "try:\n    from tools.talvez import y  # noqa: F401\nexcept ImportError:\n    y = None\n",
    "tools/rooms/kitchen/agent_cited.py": "X = 1\n",
    "docs/guide.md": "Rode `python -m tools.rooms.kitchen.cli_doc`.\n",
    ".github/workflows/ci.yml": "run: python -m tools.rooms.kitchen.cli_ci\n",
    ".claude/skills/s/SKILL.md": "Use `tools/rooms/kitchen/agent_cited.py`.\n",
    "docs/archive/old.md": "usa :8765\n",
    "docs/stale.md": "# T\nPergunte ao :8765 POST /ask\n",
    "artifacts/review/x/proof.json": "{}\n",
    "tests/test_x.py": "from tools.rooms.kitchen.user import g\n",
}


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    root = tmp_path_factory.mktemp("repo")
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git = ["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.check_call(git + ["init", "-q"])
    subprocess.check_call(git + ["add", "."])
    subprocess.check_call(git + ["commit", "-q", "-m", "x"])
    return fa.audit(root, with_ruff=False), root


def _rec(report, path):
    return next(r for r in report[0]["records"] if r["path"] == path)


@pytest.mark.parametrize("path, status", [
    ("tools/rooms/kitchen/used.py", "ACTIVE_IMPORTED"),
    ("tools/rooms/kitchen/user.py", "ACTIVE_IMPORTED"),                 # importado pelo teste
    ("tools/rooms/kitchen/cli_ci.py", "ACTIVE_ENTRYPOINT"),             # citado pelo CI
    ("tools/rooms/kitchen/agent_cited.py", "ACTIVE_ENTRYPOINT"),        # citado por skill (".claude/" nao perde o ponto)
    ("tools/rooms/kitchen/cli_doc.py", "CLI_DOC_ONLY"),                 # so documentacao cita: nao conta como uso
    ("tools/rooms/kitchen/orphan.py", "ORPHAN_CANDIDATE"),
    ("tools/rooms/kitchen/__init__.py", "PACKAGE_MARKER"),
    ("docs/archive/old.md", "HISTORICAL"),
    ("artifacts/review/x/proof.json", "EVIDENCE_OR_DATA"),
    ("tests/test_x.py", "TEST"),
])
def test_each_file_gets_a_status_with_reason_and_next_action(report, path, status):
    rec = _rec(report, path)
    assert rec["status"] == status, rec
    assert rec["reason"] and rec["next_action"] and rec["room"] in ("kitchen", "docs", "repo", "tests", "agent")


def test_stale_doc_is_flagged_but_history_is_not(report):
    assert "removido" in _rec(report, "docs/stale.md")["reason"]
    assert _rec(report, "docs/archive/old.md")["status"] == "HISTORICAL"


def test_import_review_finds_cycles_and_broken_but_not_optional_imports(report):
    imports = report[0]["imports"]
    assert imports["cycles"] == [["tools.rooms.kitchen.cyc_a", "tools.rooms.kitchen.cyc_b"]]
    assert imports["broken"] == [("tools/rooms/kitchen/broken.py", "tools.nao_existe")]       # try/except ImportError e opcional


def test_tarjan_handles_self_loops_and_dags():
    assert fa.scc_cycles({"a": {"b"}, "b": {"c"}, "c": set()}) == []
    assert fa.scc_cycles({"a": {"a"}}) == [["a"]]
    assert fa.scc_cycles({"a": {"b"}, "b": {"a"}, "c": {"a"}}) == [["a", "b"]]


def test_writes_one_handoff_per_area_deterministically(report, tmp_path):
    fa.write(report[0], tmp_path / "a")
    fa.write(report[0], tmp_path / "b")
    a = sorted(p.name for p in (tmp_path / "a/areas").iterdir())
    assert "kitchen.md" in a and a == sorted(p.name for p in (tmp_path / "b/areas").iterdir())
    assert (tmp_path / "a/areas/kitchen.md").read_text(encoding="utf-8") == (tmp_path / "b/areas/kitchen.md").read_text(encoding="utf-8")
    assert "`tools/rooms/kitchen/orphan.py` | ORPHAN_CANDIDATE" in (tmp_path / "a/areas/kitchen.md").read_text(encoding="utf-8")


def test_real_repo_import_graph_stays_clean():
    """Trava da revisao de imports: codigo vivo sem ciclo de topo, sem import quebrado, sem `import *`, sem import nao usado."""
    rep = fa.audit(ROOT)
    imports = rep["imports"]
    assert imports["cycles"] == [], imports["cycles"]
    assert imports["broken"] == [], imports["broken"]
    assert imports["star"] == [], imports["star"]
    assert imports["ruff_checked"] and imports["unused"] == [], imports["unused"][:10]
    assert not [r["path"] for r in rep["records"] if r["status"] == "BROKEN"]
