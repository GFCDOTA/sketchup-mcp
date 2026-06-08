"""Contrato do fidelity loop (alvo do GPT + ciclo medível). Hermético: tmp dirs +
PNGs minúsculos via PIL; NÃO toca .ai_bridge real, runs real, nem GPT."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools import fidelity_loop as fl


def _png(path: Path, size=(40, 30), color=(120, 120, 120)):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def test_register_ref_stores_target_and_meta(tmp_path):
    base = tmp_path / "fid"
    ref_img = tmp_path / "alvo.png"
    _png(ref_img, (60, 40), (200, 100, 50))
    r = fl.register_ref("SOFA-001", ref_img, room="sala", style="industrial", base=base)
    assert r["status"] == "REF_REGISTERED"
    meta = (base / "refs" / "SOFA-001" / "ref.json")
    assert meta.is_file()
    assert (base / "refs" / "SOFA-001" / "target.png").is_file()


def test_register_ref_missing_image_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        fl.register_ref("X", tmp_path / "nope.png", base=tmp_path / "fid")


def test_package_pairs_target_and_render(tmp_path):
    base = tmp_path / "fid"
    pkg_root = tmp_path / "runs"
    _png(tmp_path / "alvo.png", (60, 40), (200, 100, 50))
    fl.register_ref("SOFA-001", tmp_path / "alvo.png", room="sala", base=base)
    render = tmp_path / "render.png"
    _png(render, (50, 40))
    p = fl.build_validation_package("SOFA-001", render, attempt=1, base=base, pkg_root=pkg_root)
    assert p["status"] == "READY_FOR_GPT"
    assert p["attempt"] == 1
    assert Path(p["montage"]).is_file()
    assert (Path(p["package_dir"]) / "ask_gpt.md").is_file()
    assert (Path(p["package_dir"]) / "verdict_schema.json").is_file()


def test_package_without_ref_is_blocked(tmp_path):
    render = tmp_path / "r.png"
    _png(render)
    p = fl.build_validation_package("GHOST", render, base=tmp_path / "fid", pkg_root=tmp_path / "runs")
    assert p["status"] == "NO_REF"


def test_package_missing_render(tmp_path):
    base = tmp_path / "fid"
    _png(tmp_path / "alvo.png")
    fl.register_ref("SOFA-001", tmp_path / "alvo.png", base=base)
    p = fl.build_validation_package("SOFA-001", tmp_path / "missing.png", base=base, pkg_root=tmp_path / "runs")
    assert p["status"] == "NO_RENDER"


def test_record_verdict_appends_and_validates(tmp_path):
    base = tmp_path / "fid"
    r = fl.record_verdict("SOFA-001", "FAIL", attempt=1, base=base)
    assert r["status"] == "RECORDED" and r["verdict"] == "FAIL"
    assert (base / "ledger.jsonl").is_file()
    with pytest.raises(ValueError):
        fl.record_verdict("SOFA-001", "OTIMO", base=base)


def test_kpi_measures_fail_to_pass_cycle(tmp_path):
    base = tmp_path / "fid"
    fl.record_verdict("SOFA-001", "FAIL", attempt=1, base=base)
    fl.record_verdict("SOFA-001", "FAIL", attempt=2, base=base)
    fl.record_verdict("SOFA-001", "PASS", attempt=3, base=base)
    fl.record_verdict("CAMA-001", "FAIL", attempt=1, base=base)  # ainda não passou
    k = fl.kpi(base=base)
    agg = k["aggregate"]
    assert agg["objects"] == 2
    assert agg["reached_pass"] == 1
    assert k["objects"]["SOFA-001"]["reached_pass"] is True
    assert k["objects"]["SOFA-001"]["attempts"] == 3
    assert k["objects"]["SOFA-001"]["cycle_time_s"] is not None
    assert k["objects"]["CAMA-001"]["reached_pass"] is False


def test_auto_attempt_increments(tmp_path):
    base = tmp_path / "fid"
    pkg_root = tmp_path / "runs"
    _png(tmp_path / "alvo.png")
    fl.register_ref("SOFA-001", tmp_path / "alvo.png", base=base)
    render = tmp_path / "render.png"
    _png(render)
    fl.record_verdict("SOFA-001", "FAIL", attempt=1, base=base)
    p = fl.build_validation_package("SOFA-001", render, base=base, pkg_root=pkg_root)
    assert p["attempt"] == 2  # próximo após attempt 1 no ledger
