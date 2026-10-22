"""T0.1 (R-18 transitivo): a prova L2 cobre o fecho estatico dos simbolos, nao so o corpo da funcao listada.

Antes: `symbol_digest` hasheava so o corpo de `plan_cabinet`; mudar `assembly.build_parts` (a geometria do gabinete)
mantinha o `L2_PASS` antigo. Agora cada evidencia guarda `closure_digests`, calculados NO COMMIT da prova, e o gate do
catalogo acusa fecho velho.
"""
from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest

from tools.rooms import capability_catalog as cc
from tools.rooms import evidence_closure as ec

ROOT = Path(__file__).resolve().parents[1]

PKG = {
    "tools/__init__.py": "",
    "tools/rooms/__init__.py": "",
    "tools/rooms/demo/__init__.py": "from .geom import box as box  # re-export\n",
    "tools/rooms/demo/geom.py": "SIZE = 0.3\n\ndef box(w):\n    return w * SIZE\n\ndef unused():\n    return 1\n",
    "tools/rooms/demo/helpers.py": "def k(x):\n    return x + 1\n",
    "tools/rooms/demo/plan.py": (
        "import json\n"
        "from . import helpers as hp\n"
        "from tools.rooms.demo import box\n"
        "from .geom import SIZE\n\n"
        "TABLE = {'a': 1}\n\n"
        "def _local(v):\n    return TABLE[v]\n\n"
        "def plan(v):\n"
        "    def inner():\n        return hp.k(v)\n"
        "    return json.dumps([box(v), _local('a'), inner(), SIZE])\n"),
}


def _write(root: Path, files: dict) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def test_closure_follows_local_calls_constants_relative_and_reexported_imports(tmp_path):
    _write(tmp_path, PKG)
    members = ec.closure("tools.rooms.demo.plan.plan", ec.WorktreeSource(tmp_path))
    assert members == sorted([
        "tools.rooms.demo.plan.plan", "tools.rooms.demo.plan._local", "tools.rooms.demo.plan.TABLE",
        "tools.rooms.demo.helpers.k", "tools.rooms.demo.geom.box", "tools.rooms.demo.geom.SIZE"])
    assert "tools.rooms.demo.geom.unused" not in members                       # so o que e alcancado
    assert not any(m.startswith("json") for m in members)                       # fora do escopo tools.rooms/core


def test_helper_change_changes_the_closure_digest_but_comments_do_not(tmp_path):
    _write(tmp_path, PKG)
    src = ec.WorktreeSource(tmp_path)
    before = ec.closure_digest("tools.rooms.demo.plan.plan", src)
    _write(tmp_path, {"tools/rooms/demo/geom.py": PKG["tools/rooms/demo/geom.py"].replace("# x", "") + "\n# comentario\n\n"})
    assert ec.closure_digest("tools.rooms.demo.plan.plan", ec.WorktreeSource(tmp_path)) == before
    _write(tmp_path, {"tools/rooms/demo/geom.py": PKG["tools/rooms/demo/geom.py"].replace("w * SIZE", "w * SIZE * 2")})
    assert ec.closure_digest("tools.rooms.demo.plan.plan", ec.WorktreeSource(tmp_path)) != before
    _write(tmp_path, {"tools/rooms/demo/geom.py": PKG["tools/rooms/demo/geom.py"].replace("SIZE = 0.3", "SIZE = 0.4")})
    assert ec.closure_digest("tools.rooms.demo.plan.plan", ec.WorktreeSource(tmp_path)) != before   # constante tambem
    assert ec.closure_digest("tools.rooms.demo.plan.nao_existe", src) is None


def test_git_source_reads_the_code_of_the_evidence_commit(tmp_path):
    _write(tmp_path, PKG)
    git = ["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t"]
    subprocess.check_call(git + ["init", "-q"])
    subprocess.check_call(git + ["add", "."])
    subprocess.check_call(git + ["commit", "-q", "-m", "x"])
    sha = subprocess.check_output(git + ["rev-parse", "--short", "HEAD"], text=True).strip()
    at_commit = ec.closure_digest("tools.rooms.demo.plan.plan", ec.GitSource(tmp_path, sha))
    assert at_commit == ec.closure_digest("tools.rooms.demo.plan.plan", ec.WorktreeSource(tmp_path))
    _write(tmp_path, {"tools/rooms/demo/helpers.py": "def k(x):\n    return x + 2\n"})            # muda so no disco
    assert ec.closure_digest("tools.rooms.demo.plan.plan", ec.WorktreeSource(tmp_path)) != at_commit
    assert ec.closure_digest("tools.rooms.demo.plan.plan", ec.GitSource(tmp_path, sha)) == at_commit


def test_real_cabinet_plan_reaches_the_geometry_it_proves():
    """O caso que motivou a T0.1: a geometria do gabinete esta no fecho de `plan_cabinet`."""
    members = ec.closure("tools.rooms.shared.cabinet.plan.plan_cabinet", ec.WorktreeSource(ROOT))
    assert {"tools.rooms.shared.cabinet.assembly.build_parts", "tools.rooms.shared.cabinet.model.parse_request",
            "tools.rooms.shared.cabinet.validation.validate_plan"} <= set(members)


def _real_catalog():
    return json.loads((ROOT / "tools/rooms/capability_catalog.v1.json").read_text(encoding="utf-8"))


def test_every_current_l2_proof_carries_closure_digests_that_still_match():
    res = cc.verify(_real_catalog())
    assert res["result"] == "PASS", res["errors"]
    for cap in _real_catalog()["capabilities"]:
        if cap["validation"]["state"] == "L2_PASS":
            for ev in cap["validation"]["evidence"]:
                py = {k for k in ev["symbol_digests"] if k.startswith("python:")}
                assert py <= set(ev.get("closure_digests", {})), cap["id"]


def test_gate_flags_a_stale_or_missing_closure():
    cat = _real_catalog()
    cap = next(c for c in cat["capabilities"] if c["id"] == "shared.cabinet.parametric")
    key = next(k for k in cap["validation"]["evidence"][0]["closure_digests"])
    stale = copy.deepcopy(cat)
    sc = next(c for c in stale["capabilities"] if c["id"] == "shared.cabinet.parametric")
    sc["validation"]["evidence"][0]["closure_digests"][key] = "0" * 64
    assert any(key in m for m in cc.verify(stale)["errors"].get("EVIDENCE_CLOSURE_STALE", []))
    missing = copy.deepcopy(cat)
    mc = next(c for c in missing["capabilities"] if c["id"] == "shared.cabinet.parametric")
    mc["validation"]["evidence"][0].pop("closure_digests")
    assert any("shared.cabinet.parametric" in m for m in cc.verify(missing)["errors"].get("L2_CLOSURE_WITHOUT_PROOF", []))


def test_backfill_refuses_to_record_a_closure_that_differs_from_the_evidence_commit(monkeypatch):
    cat = _real_catalog()
    real = ec.closure_digest
    monkeypatch.setattr(ec, "closure_digest", lambda ref, src: ("OUTRO" if isinstance(src, ec.GitSource) else real(ref, src)))
    report = ec.backfill(cat, ROOT)
    assert report["mismatch"] and not report["written"]
    for cap in cat["capabilities"]:
        for ev in cap["validation"]["evidence"]:
            assert "closure_digests" not in ev or ev["closure_digests"] == _evidence(cap["id"], ev["commit"])


def _evidence(cid, commit):
    cap = next(c for c in _real_catalog()["capabilities"] if c["id"] == cid)
    return next(e for e in cap["validation"]["evidence"] if e["commit"] == commit).get("closure_digests")


@pytest.mark.parametrize("ref", ["tools.rooms.kitchen.capabilities.shaker_flow.run_request",
                                 "tools.rooms.kitchen.capabilities.cabinet_flow.run_request"])
def test_flow_closures_include_the_gatekeeper_they_rely_on(ref):
    members = ec.closure(ref, ec.WorktreeSource(ROOT))
    assert "tools.rooms.specialists.plan" in members                        # mudar o gate tambem derruba a prova do fluxo


class _Overlay(ec.WorktreeSource):
    """Codigo real com UM arquivo trocado em memoria (nao mexe no disco)."""

    def __init__(self, root, rel, text):
        super().__init__(root)
        self.rel, self.text = rel, text

    def read(self, rel):
        return self.text if rel == self.rel else super().read(rel)


def test_the_motivating_hole_a_helper_change_only_shows_up_in_the_closure():
    rel = "tools/rooms/shared/cabinet/assembly.py"
    real = (ROOT / rel).read_text(encoding="utf-8")
    edited = real.replace("return p.depth - p.front - p.front_clearance", "return p.depth - p.front - 2 * p.front_clearance")
    assert edited != real
    ref = "tools.rooms.shared.cabinet.plan.plan_cabinet"
    plan_text = (ROOT / "tools/rooms/shared/cabinet/plan.py").read_text(encoding="utf-8")
    assert "carcass_depth" in plan_text or "build_parts" in plan_text           # plan_cabinet nao muda de corpo...
    assert ec.closure_digest(ref, _Overlay(ROOT, rel, edited)) != ec.closure_digest(ref, ec.WorktreeSource(ROOT))  # ...o fecho sim
