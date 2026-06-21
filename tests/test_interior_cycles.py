"""Testes da esteira do Interior Studio: entidade CYCLE + Reference Pack + curadoria do Felipe.

Comportamento (não método): a regra-trava (Arquiteto bloqueado sem ⭐ principal), exclusividade do
principal, sincronização ciclo↔pack e idempotência. Paths redirecionados pra tmp (sem tocar o repo).
"""
import json

import pytest

from tools.interior_studio import cycles, reference_packs


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    packs = tmp_path / "packs"
    packs.mkdir()
    monkeypatch.setattr(cycles, "CYCLES_DIR", tmp_path / "cycles")
    monkeypatch.setattr(reference_packs, "PACKS_DIR", packs)
    monkeypatch.setattr(reference_packs, "FELIPE_DIR", tmp_path / "felipe")
    monkeypatch.setattr(reference_packs, "ROOT", tmp_path)
    return tmp_path


def _seed_pack(packs_dir):
    pack = {"pack_id": "p1", "asset": "sofa", "references": [
        {"id": "r1", "title": "Boa A", "type": "boutique_premium", "status": "pending"},
        {"id": "r2", "title": "Boa B", "type": "compact_premium", "status": "pending"},
        {"id": "r3", "title": "Caixa", "type": "anti_example", "status": "pending"},
    ]}
    (packs_dir / "p1.json").write_text(json.dumps(pack), "utf-8")


def _cycle_linked():
    c = cycles.new_cycle(asset="sofa", microtask="MT-SOFA-001", mode="REFERENCE_PACK",
                         cycle_id="CYCLE-001", ts=1000.0)
    c["references"]["pack_id"] = "p1"
    cycles.save_cycle(c)
    return c["cycle_id"]


def test_novo_ciclo_nasce_com_arquiteto_bloqueado(sandbox):
    cid = _cycle_linked()
    tl = {s["agent"]: s["status"] for s in cycles.timeline(cycles.get_cycle(cid))}
    assert tl["Architect"] == "blocked"
    assert cycles.architect_blocked(cycles.get_cycle(cid)) is True


def test_marcar_principal_desbloqueia_o_arquiteto(sandbox):
    _seed_pack(sandbox / "packs")
    cid = _cycle_linked()
    reference_packs.curate("p1", "r1", "main", cycle_id=cid)
    c = cycles.get_cycle(cid)
    assert c["references"]["main"] == ["r1"]
    assert cycles.architect_blocked(c) is False
    tl = {s["agent"]: s["status"] for s in cycles.timeline(c)}
    assert tl["Architect"] == "pending"   # destravado


def test_principal_e_exclusivo(sandbox):
    _seed_pack(sandbox / "packs")
    cid = _cycle_linked()
    reference_packs.curate("p1", "r1", "main", cycle_id=cid)
    reference_packs.curate("p1", "r2", "main", cycle_id=cid)
    pack = reference_packs.load_pack("p1")
    st = {r["id"]: r["status"] for r in pack["references"]}
    assert st["r1"] == "approved"   # rebaixado de principal
    assert st["r2"] == "main"


def test_anti_pattern_vai_pro_bucket_e_pro_ciclo(sandbox):
    _seed_pack(sandbox / "packs")
    cid = _cycle_linked()
    r = reference_packs.curate("p1", "r3", "anti", cycle_id=cid)
    assert r["ok"] and r["counts"]["anti"] == 1
    assert cycles.get_cycle(cid)["references"]["anti"] == ["r3"]
    assert (sandbox / "felipe" / "anti_patterns" / "r3.json").exists()


def test_clear_remove_verdito_e_volta_pendente(sandbox):
    _seed_pack(sandbox / "packs")
    cid = _cycle_linked()
    reference_packs.curate("p1", "r1", "approve", cycle_id=cid)
    assert (sandbox / "felipe" / "approved" / "r1.json").exists()
    reference_packs.curate("p1", "r1", "clear", cycle_id=cid)
    assert not (sandbox / "felipe" / "approved" / "r1.json").exists()
    assert reference_packs.load_pack("p1")["references"][0]["status"] == "pending"


def test_curadoria_idempotente(sandbox):
    _seed_pack(sandbox / "packs")
    cid = _cycle_linked()
    reference_packs.curate("p1", "r1", "approve", cycle_id=cid)
    r = reference_packs.curate("p1", "r1", "approve", cycle_id=cid)
    assert r["counts"]["approved"] == 1   # não duplica


def test_remover_referencia_tira_do_pack_e_do_ciclo(sandbox):
    """Link quebrado / inútil → remove de vez (some do pack + dos arrays do ciclo + verditos)."""
    _seed_pack(sandbox / "packs")
    cid = _cycle_linked()
    reference_packs.curate("p1", "r2", "approve", cycle_id=cid)
    r = reference_packs.curate("p1", "r2", "remove", cycle_id=cid)
    assert r["ok"] and r["removed"] == "r2"
    pack = reference_packs.load_pack("p1")
    assert all(x["id"] != "r2" for x in pack["references"])   # sumiu do pack
    assert "r2" not in cycles.get_cycle(cid)["references"]["approved"]
    assert not (sandbox / "felipe" / "approved" / "r2.json").exists()


def test_acao_invalida_nao_quebra(sandbox):
    _seed_pack(sandbox / "packs")
    r = reference_packs.curate("p1", "r1", "explode")
    assert r["ok"] is False and "inválida" in r["error"]


def test_timeline_deriva_arquiteto_ignora_status_congelado(sandbox):
    """Regressão: mesmo com 'blocked' GRAVADO na semente do ciclo, marcar ⭐ principal DESTRAVA
    (timeline deriva o status do estado atual, não lê o congelado — bug que travava o Felipe)."""
    _seed_pack(sandbox / "packs")
    cid = _cycle_linked()
    cycles.set_step(cid, "Architect", "blocked", "status congelado na semente")
    cycles.set_step(cid, "Felipe", "waiting", "congelado")
    reference_packs.curate("p1", "r1", "main", cycle_id=cid)
    tl = {s["agent"]: s["status"] for s in cycles.timeline(cycles.get_cycle(cid))}
    assert tl["Architect"] == "pending"   # derivou — NÃO leu o 'blocked' gravado
    assert tl["Felipe"] == "done"


def test_anti_exemplo_nao_vira_principal(sandbox):
    """Clicar ⭐ principal num anti-exemplo é misclick → roteia pra anti (não se constrói do que evitar)."""
    _seed_pack(sandbox / "packs")
    cid = _cycle_linked()
    r = reference_packs.curate("p1", "r3", "main", cycle_id=cid)   # r3 = anti_example
    assert r["ok"] and r["rerouted_anti"] is True and r["status"] == "anti"
    c = cycles.get_cycle(cid)
    assert c["references"]["main"] == []          # anti-exemplo NÃO entra em main
    assert c["references"]["anti"] == ["r3"]
    assert cycles.architect_blocked(c) is True    # segue bloqueado (sem principal válido)
