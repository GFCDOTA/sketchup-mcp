"""Testes do furniture_program por Arquiteto: fila de proposals (save/approve/reject) + extração do JSON
do deepseek-r1 (que cospe <think>…</think> antes do JSON). NÃO chama o LLM (isso é integração)."""
import pytest

from tools.interior_studio import architect_program as ap, proposals


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
