"""Testes da state machine canônica + inventário por cômodo (GAP 1 do GPT).

Garante: as 11 fases derivadas dos sinais reais, a próxima ação resolvida, e o inventário por cômodo
(cada ambiente só com SEUS assets). Paths em tmp (não toca o repo).
"""
import json

import pytest

from tools.interior_studio import cycles, project_state as ps, reference_packs as rp


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    (tmp_path / "tools").mkdir()
    (tmp_path / "packs").mkdir()
    monkeypatch.setattr(ps, "ROOT", tmp_path)
    monkeypatch.setattr(cycles, "CYCLES_DIR", tmp_path / "cycles")
    monkeypatch.setattr(rp, "PACKS_DIR", tmp_path / "packs")
    return tmp_path


def _class(sb, asset):
    (sb / "tools" / f"{asset}_class.py").write_text("# class", "utf-8")


def _pack(sb, asset, refs):
    (sb / "packs" / f"{asset}_reference_pack_001.json").write_text(
        json.dumps({"pack_id": f"{asset}_reference_pack_001", "references": refs}), "utf-8")


def _verdict(sb, asset, text):
    d = sb / "artifacts/review/furniture" / asset
    d.mkdir(parents=True, exist_ok=True)
    (d / "gpt_verdict.md").write_text(text, "utf-8")
    (d / "x_compare.png").write_bytes(b"x")   # build_done


def test_sinais_case_idioma_insensiveis_nao_travam_estado(sandbox):
    """Regressão: verdict do GPT em minúsculas / idioma variante não pode deixar o asset travado
    em form_review/context_review quando na verdade foi aprovado."""
    _class(sandbox, "sofa")
    _pack(sandbox, "sofa", [{"id": "r1", "status": "main"}])
    _verdict(sandbox, "sofa", "Veredito: forma PASS. contexto: pass (parou de parecer caixa).")
    assert ps.asset_state("sofa")["state"] == "vray_ready"


def test_not_started_sem_classe_sem_pack(sandbox):
    assert ps.asset_state("nightstand")["state"] == "not_started"


def test_classe_sem_pack_eh_references_needed(sandbox):
    _class(sandbox, "rack")
    a = ps.asset_state("rack")
    assert a["state"] == "references_needed" and a["jump"] == "sec-refpack"


def test_pack_sem_principal_eh_curation_needed(sandbox):
    _class(sandbox, "sofa")
    _pack(sandbox, "sofa", [{"id": "r1", "status": "pending"}])
    assert ps.asset_state("sofa")["state"] == "curation_needed"


def test_principal_escolhido_eh_build_spec_ready(sandbox):
    _class(sandbox, "sofa")
    _pack(sandbox, "sofa", [{"id": "r1", "status": "main"}])
    assert ps.asset_state("sofa")["state"] == "build_spec_ready"


def test_kitchen_eh_frozen(sandbox):
    assert ps.asset_state("kitchen")["state"] == "frozen"


def test_next_action_sempre_resolvido(sandbox):
    for asset in ("nightstand", "rack", "kitchen"):
        a = ps.asset_state(asset)
        assert a["next"], f"{asset} sem próxima ação"


def test_pipeline_furniture_segue_o_estado(sandbox):
    _class(sandbox, "sofa")
    _pack(sandbox, "sofa", [{"id": "r1", "status": "main"}])   # build_spec_ready
    pipe = ps.pipeline_for("sofa")
    assert [p["status"] for p in pipe][:3] == ["done", "done", "doing"]   # refs+curadoria done, build_spec doing


def test_pipeline_kitchen_frozen_tudo_done(sandbox):
    pipe = ps.pipeline_for("kitchen")
    assert pipe and all(p["status"] == "done" for p in pipe)   # cozinha congelada = pipeline da cozinha 100%


def test_active_focuses_so_o_que_esta_em_andamento(sandbox):
    _class(sandbox, "sofa")
    _pack(sandbox, "sofa", [{"id": "r1", "status": "main"}])   # in progress
    _class(sandbox, "rack")                                     # references_needed = NÃO é foco
    foc = ps.active_focuses()
    assets = [f["asset"] for f in foc]
    assert "sofa" in assets and "rack" not in assets and "kitchen" not in assets
    sofa = next(f for f in foc if f["asset"] == "sofa")
    assert sofa["environment"] == "sala" and sofa["pipeline"] and sofa["next"]


def test_inventario_por_comodo_so_tem_seus_assets(sandbox):
    m = ps.project_state()
    keys = [r["key"] for r in m["rooms"]]
    assert {"sala", "suite", "cozinha", "banheiro"} <= set(keys)
    sala = next(r for r in m["rooms"] if r["key"] == "sala")
    sala_assets = [a["asset"] for a in sala["assets"]]
    assert "sofa" in sala_assets and "bed" not in sala_assets   # cada cômodo só com os SEUS
    cozinha = next(r for r in m["rooms"] if r["key"] == "cozinha")
    assert cozinha["assets"][0]["state"] == "frozen" and cozinha["done"] == 1
