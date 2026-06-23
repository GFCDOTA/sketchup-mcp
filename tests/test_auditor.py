"""Testes do Consistency/Gap Auditor (determinístico, propõe nunca muta). Paths em tmp."""
import json

import pytest

from tools.interior_studio import auditor, cycles, project_state as ps, proposals, reference_packs as rp


@pytest.fixture
def sb(tmp_path, monkeypatch):
    (tmp_path / "tools").mkdir()
    (tmp_path / "packs").mkdir()
    monkeypatch.setattr(ps, "ROOT", tmp_path)
    monkeypatch.setattr(auditor, "ROOT", tmp_path)
    monkeypatch.setattr(rp, "PACKS_DIR", tmp_path / "packs")
    monkeypatch.setattr(proposals, "PDIR", tmp_path / "proposals")
    monkeypatch.setattr(cycles, "CYCLES_DIR", tmp_path / "cycles")
    return tmp_path


def _pack(sb, asset, refs):
    (sb / "packs" / f"{asset}_reference_pack_001.json").write_text(
        json.dumps({"pack_id": f"{asset}_reference_pack_001", "references": refs}), "utf-8")


def _class(sb, asset):
    (sb / "tools" / f"{asset}_class.py").write_text("# class", "utf-8")


def test_detecta_principal_duplicado_no_pack(sb):
    _pack(sb, "sofa", [{"id": "a", "status": "main"}, {"id": "b", "status": "main"}])
    g = [x for x in auditor.audit() if x["kind"] == "duplicate_main"]
    assert g and g[0]["asset"] == "sofa"


def test_estado_avancado_sem_json_verdict_vira_gap(sb):
    _class(sb, "sofa")
    _pack(sb, "sofa", [{"id": "r1", "status": "main"}])
    d = sb / "artifacts/review/furniture/sofa"
    d.mkdir(parents=True)
    (d / "gpt_verdict.md").write_text("contexto: pass (parou de parecer caixa)", "utf-8")  # md frágil
    (d / "x_compare.png").write_bytes(b"x")
    assert ps.asset_state("sofa")["state"] == "vray_ready"
    g = [x for x in auditor.audit() if x["kind"] == "no_json_verdict" and x.get("asset") == "sofa"]
    assert g


def test_sidecar_json_resolve_o_gap(sb):
    _class(sb, "sofa")
    _pack(sb, "sofa", [{"id": "r1", "status": "main"}])
    ps.save_asset_verdict("sofa", "context", "PASS")     # emite o sidecar estruturado
    assert ps.asset_state("sofa")["state"] == "vray_ready"
    assert not any(x["kind"] == "no_json_verdict" and x.get("asset") == "sofa" for x in auditor.audit())


def test_programa_aprovado_que_viola_o_gate_vira_gap(sb):
    proposals.save({"id": "furniture_program_r004", "type": "furniture_program", "environment": "cozinha",
                    "items": [{"asset": "cama"}, {"asset": "bancada"}]})   # cama na cozinha = cross-cômodo
    proposals.approve("furniture_program_r004")
    g = [x for x in auditor.audit() if x["kind"] == "stale_program"]
    assert g and g[0]["environment"] == "cozinha"


def test_proposta_pendente_que_viola_o_gate_vira_gap(sb):
    proposals.save({"id": "furniture_program_r000", "type": "furniture_program", "environment": "suite",
                    "items": [{"asset": "wardrobe"}, {"asset": "mirror"}]})   # suíte SEM cama
    g = [x for x in auditor.audit() if x["kind"] == "buggy_pending_program"]
    assert g and g[0]["environment"] == "suite" and "cama" in g[0]["detail"]


def test_audit_and_save_salva_e_limpa_stale(sb):
    _pack(sb, "sofa", [{"id": "a", "status": "main"}, {"id": "b", "status": "main"}])
    r1 = auditor.audit_and_save()
    assert r1["found"] >= 1 and r1["saved"] >= 1
    assert any(p.get("kind") == "duplicate_main" for p in proposals.state()["pending"])
    # conserta o pack (1 principal) → o gap pending deixa de existir → é removido como stale
    _pack(sb, "sofa", [{"id": "a", "status": "main"}, {"id": "b", "status": "pending"}])
    auditor.audit_and_save()
    assert not any(p.get("kind") == "duplicate_main" for p in proposals.state()["pending"])
