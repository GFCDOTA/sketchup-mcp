"""Aba Arquivos: descricao EXTRAIDA do proprio arquivo (nunca inventada) + contrato.

Roda com pytest OU direto:  python tests/test_recent_files.py  (da raiz do repo)
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.claude_bridge.server import _py_desc, _md_desc, recent_files  # noqa: E402


def _tmp(name, content):
    p = Path(tempfile.mkdtemp()) / name
    p.write_text(content, encoding="utf-8")
    return p


def test_py_desc_pega_docstring():
    p = _tmp("x.py", '"""Faz a coisa X.\nlinha 2 ignorada"""\nimport os\n')
    assert _py_desc(p) == "Faz a coisa X."

def test_py_desc_vazio_sem_docstring():
    assert _py_desc(_tmp("y.py", "import os\nx = 1\n")) == ""

def test_py_desc_nao_quebra_em_syntax_error():
    assert _py_desc(_tmp("z.py", "def (:\n  pass\n")) == ""  # nao explode

def test_md_desc_pega_heading():
    assert _md_desc(_tmp("a.md", "\n# Titulo do doc\ncorpo\n")) == "Titulo do doc"

def test_md_desc_pula_frontmatter_e_branco():
    assert _md_desc(_tmp("b.md", "---\n\n## Segundo nivel\n")) == "Segundo nivel"

def test_recent_files_contract():
    d = recent_files(limit=15)
    assert "files" in d and "total" in d and "shown" in d
    for f in d["files"]:
        for k in ("path", "kind", "age_sec", "desc"):
            assert k in f, "faltou chave: " + k
        assert f["kind"] in ("py", "md")
    # ordenado por mtime desc (idade crescente)
    ages = [f["age_sec"] for f in d["files"]]
    assert ages == sorted(ages), "deveria estar ordenado por mais recente primeiro"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    ok = fail = 0
    for f in fns:
        try:
            f(); print("PASS", f.__name__); ok += 1
        except Exception:
            print("FAIL", f.__name__); traceback.print_exc(); fail += 1
    print("\n%d passed, %d failed" % (ok, fail))
    sys.exit(1 if fail else 0)
