"""Testes do furniture_program por Arquiteto: fila de proposals (save/approve/reject) + extração do JSON
do deepseek-r1 (que cospe <think>…</think> antes do JSON). NÃO chama o LLM (isso é integração)."""
import pytest

from tools.interior_studio import architect_program as ap
from tools.interior_studio import proposals


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(proposals, "PDIR", tmp_path / "proposals")
    return tmp_path


def test_save_marca_requires_approval_e_fica_pending(store):
    proposals.save({"id": "furniture_program_r002", "type": "furniture_program",
                    "environment": "sala", "items": [{"asset": "sofa"}]})
    s = proposals.state()
    assert len(s["pending"]) == 1 and s["pending"][0]["requires_approval"] is True


def test_approve_move_pra_approved_e_some_do_pending(store):
    proposals.save({"id": "furniture_program_r002", "type": "furniture_program",
                    "environment": "sala", "items": [{"asset": "sofa"}]})
    proposals.approve("furniture_program_r002")
    s = proposals.state()
    assert not s["pending"] and len(s["approved"]) == 1
    assert proposals.approved_program("sala")["environment"] == "sala"


def test_reject_move_pra_rejected(store):
    proposals.save({"id": "x", "type": "furniture_program", "environment": "cozinha", "items": []})
    proposals.reject("x")
    s = proposals.state()
    assert len(s["rejected"]) == 1 and not s["pending"]


def test_extract_json_tira_o_think_do_deepseek():
    raw = ('<think>a sala combina sofa com rack, preciso decidir...</think>\nResposta final:\n'
           '{"environment":"sala","items":[{"asset":"sofa","priority":"core","reason":"estar"}]}')
    p = ap._extract_json(raw)
    assert p and p["items"][0]["asset"] == "sofa"


def test_extract_json_sem_json_retorna_none():
    assert ap._extract_json("o arquiteto divagou e nao deu json") is None


# --- SPEC-C: gate deterministico do programa (LLM propoe, gate garante o invariante) ---

def test_normalize_injeta_cama_quando_suite_esquece():
    items, gate = ap.normalize_program(
        [{"asset": "guarda_roupa"}, {"asset": "criado_mudo"}], "suite")
    assert any("cama" in i["asset"] for i in items)          # cama injetada
    assert "cama" in gate["injected"]


def test_normalize_remove_item_de_outro_comodo_da_cozinha():
    items, gate = ap.normalize_program(
        [{"asset": "cama"}, {"asset": "bancada"}, {"asset": "cooktop"}, {"asset": "geladeira"}],
        "cozinha")
    names = [i["asset"] for i in items]
    assert "cama" not in names                               # cross-comodo removido
    assert any(r["asset"] == "cama" for r in gate["removed"])
    assert {"bancada", "cooktop", "geladeira"} <= set(names)  # CORE da cozinha preservado


def test_normalize_salva_asset_bom_tirando_prefixo_de_outro_comodo():
    # bug real: Arquiteto prefixou itens da cozinha com 'banheiro_'
    items, _ = ap.normalize_program(
        [{"asset": "banheiro_cooktop"}, {"asset": "banheiro_bancada"}, {"asset": "banheiro_geladeira"}],
        "cozinha")
    names = [i["asset"] for i in items]
    assert "cooktop" in names and "bancada" in names and "geladeira" in names
    assert not any(n.startswith("banheiro_") for n in names)


def test_normalize_e_idempotente():
    once, _ = ap.normalize_program([{"asset": "sofa"}], "sala")
    twice, _ = ap.normalize_program(once, "sala")
    assert [i["asset"] for i in once] == [i["asset"] for i in twice]


# --- FP-035: injeção do DesignSpecBundle recuperado no prompt do Arquiteto ---

def test_render_bundle_for_prompt_e_estruturado_nao_dna_cru():
    bundle = {
        "confidence": "LOW",
        "tokens": [{"name": "hot_tower_niche", "builder_kinds": ["kc_niche_wood"]},
                   {"name": "coordinated_medium_dark_wood_base", "builder_kinds": ["kc_corpo"]}],
        "anti_patterns": ["Micro na bancada come área de trabalho."],
        "layout_hints": ["hot_tower_niche: ponta oposta à geladeira"],
    }
    block = ap.render_bundle_for_prompt(bundle)
    assert "hot_tower_niche" in block
    assert "coordinated_medium_dark_wood_base" in block
    assert "ANTI-PADRÕES" in block and "Micro na bancada" in block
    assert "LAYOUT" in block


def test_render_bundle_vazio_quando_sem_tokens():
    assert ap.render_bundle_for_prompt(None) == ""
    assert ap.render_bundle_for_prompt({"tokens": []}) == ""


def test_architect_prompt_injects_bundle(monkeypatch):
    # room_context da cozinha injeta o bloco estruturado do bundle recuperado
    # (tokens canônicos), não só o dna cru truncado.
    fake_bundle = {
        "confidence": "LOW",
        "tokens": [{"name": "hot_tower_niche", "builder_kinds": ["kc_niche_wood"]}],
        "anti_patterns": ["forno embaixo do cooktop perde ergonomia"],
        "layout_hints": [],
    }
    monkeypatch.setattr(ap, "_retrieve_bundle", lambda room_key: fake_bundle)
    # rooms() pode não achar consensus real no worktree; testa o wiring direto.
    monkeypatch.setattr(ap, "rooms", lambda: [
        {"id": "r004", "name": "COZINHA", "area_m2": 8.0, "w_m": 3.0, "d_m": 2.5,
         "key": "cozinha"}])
    ctx = ap.room_context("r004")
    assert ctx is not None
    assert ctx["design_bundle"] is fake_bundle
    assert "hot_tower_niche" in ctx["design_spec"]


def test_retrieve_bundle_degrada_para_none_em_erro(monkeypatch):
    # RETROCOMPAT: se retrieve estoura, _retrieve_bundle devolve None (cai no dna cru)
    import tools.reference_db as rdb

    def _boom(*a, **k):
        raise RuntimeError("db off")

    monkeypatch.setattr(rdb, "retrieve", _boom)
    assert ap._retrieve_bundle("cozinha") is None


def test_retrieve_bundle_none_para_comodo_sem_mapa():
    assert ap._retrieve_bundle(None) is None
    assert ap._retrieve_bundle("") is None
