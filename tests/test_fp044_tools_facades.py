"""FP-044/F6 — fachadas de `tools/*.py`: as publicas continuam o MESMO modulo do dono; as removidas nao voltam.

Fonte da verdade: docs/specs/fp044_tools_facades.v1.json (acao por arquivo). Contrato publico: tools/PUBLIC_API.md.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "docs/specs/fp044_tools_facades.v1.json").read_text("utf-8"))
ENTRIES = MANIFEST["entries"]
PUBLIC = [e for e in ENTRIES if e["action"] == "KEEP_PUBLIC"]
REMOVED = [e for e in ENTRIES if e["action"] == "REMOVED"]
CODE = (".py", ".rb", ".ps1", ".psm1", ".cmd", ".bat", ".sh", ".yml", ".yaml", ".toml")
PUBLIC_NAMES = ("furnish_apartment", "geometry_sanity", "furniture_overlap_gate", "finding_router", "circulation_gate",
                "correction_loop", "spatial_model", "room_type")


def _tracked() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    return [f for f in out if f]


def _target(path: Path) -> str:
    m = re.search(r'^_TARGET = "([\w.]+)"$', path.read_text("utf-8"), re.M)
    assert m, f"{path} nao e fachada _TARGET"
    return m.group(1)


def test_as_oito_publicas_sao_exatamente_as_do_contrato():
    assert sorted(Path(e["path"]).stem for e in PUBLIC) == sorted(PUBLIC_NAMES)
    doc = (ROOT / "tools/PUBLIC_API.md").read_text("utf-8")
    for name in PUBLIC_NAMES:
        assert f"`tools.{name}`" in doc and f"`{_target(ROOT / 'tools' / (name + '.py'))}`" in doc, name


def test_publicas_importam_e_sao_o_mesmo_modulo_do_dono():
    pairs = [(f"tools.{n}", _target(ROOT / "tools" / f"{n}.py")) for n in PUBLIC_NAMES]
    code = ("import importlib, sys; sys.path.insert(0, sys.argv[1]); pairs = " + repr(pairs) + "\n"
            "bad = [p for p in pairs if importlib.import_module(p[0]) is not importlib.import_module(p[1])]\n"
            "print('OK' if not bad else bad)")
    done = subprocess.run([sys.executable, "-c", code, str(ROOT)], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    assert done.stdout.strip() == "OK", (done.stdout, done.stderr[-1500:])


@pytest.mark.parametrize("entry", REMOVED, ids=lambda e: e["path"])
def test_fachada_removida_nao_tem_arquivo_nem_consumidor_em_codigo(entry):
    assert not (ROOT / entry["path"]).exists()
    name = re.escape(Path(entry["path"]).stem)
    pat = re.compile(r"(?<![\w.])tools\." + name + r"(?!\w)|(?<![\w/.\\-])tools[/\\]" + name + r"\.py(?!\w)")
    hits = [f for f in _tracked() if f.endswith(CODE) and not f.startswith(("artifacts/", "docs/archive/"))  # historico
            and pat.search((ROOT / f).read_text("utf-8", errors="replace"))]
    assert hits == [], hits
