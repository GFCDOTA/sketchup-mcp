"""Testes do LEARNING_PATCH: resposta GPT → draft → diff → aprova/rejeita → DNA.

Garante a regra de ouro do GPT: NADA toca o DNA sem aprovação do Felipe. Paths em tmp (não toca o repo).
"""
import json

import pytest

from tools.interior_studio import cycles, learning_patch as lp
from tools.interior_studio import gpt_review_bundle as bundle
from tools.interior_studio.consult_gpt_bridge import ingest as ci

PARSED = {"verdict": "PASS", "question_id": "q1",
          "dna_updates": ["sofá não pode nascer de cubo com almofada simbólica"],
          "anti_patterns": ["sofa_box_block"],
          "next_microtask": {"id": "MT-SOFA-003", "title": "Gerar SOFA_BUILD_SPEC"}}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    dna = tmp_path / "dna.md"
    dna.write_text("# Felipe DNA\n", "utf-8")
    judge = tmp_path / "judge.json"
    judge.write_text(json.dumps({"anti_patterns": []}), "utf-8")
    monkeypatch.setattr(ci, "FELIPE_DNA", dna)
    monkeypatch.setattr(ci, "JUDGE_RULES", judge)
    monkeypatch.setattr(lp, "PATCHES_DIR", tmp_path / "patches")
    monkeypatch.setattr(cycles, "CYCLES_DIR", tmp_path / "cycles")
    monkeypatch.setattr(bundle, "_git_info", lambda: {"branch": "test", "sha": "abc12345",
                                                      "owner": None, "repo": None, "remote_url": None})
    return tmp_path


def _cycle():
    c = cycles.new_cycle(asset="sofa", microtask="MT-SOFA-001", mode="REFERENCE_PACK",
                         cycle_id="CYCLE-001", ts=1.0)
    c["references"]["main"] = ["r1"]
    cycles.save_cycle(c)
    return c


def test_from_answer_cria_draft_sem_tocar_dna(sandbox):
    c = _cycle()
    p = lp.from_answer(dict(PARSED), cycle=c, now="2026-01-01T00:00:00")
    assert p["status"] == "draft" and p["patch_id"].startswith("LP-SOFA-")
    assert p["proposed_changes"]["new_rules"] == PARSED["dna_updates"]
    assert p["branch"] == "test" and p["commit_sha"] == "abc12345"
    assert PARSED["dna_updates"][0] not in (sandbox / "dna.md").read_text("utf-8")   # NÃO aplicou


def test_diff_separa_novo_de_duplicado(sandbox):
    c = _cycle()
    (sandbox / "dna.md").write_text("# DNA\n- sofá não pode nascer de cubo com almofada simbólica\n", "utf-8")
    p = lp.from_answer({**PARSED, "dna_updates": ["sofá não pode nascer de cubo com almofada simbólica",
                                                  "braço mais leve que o encosto"]}, cycle=c)
    d = lp.compute_diff(p)
    assert "braço mais leve que o encosto" in d["rules_add"]
    assert "sofá não pode nascer de cubo com almofada simbólica" in d["rules_dup"]


def test_approve_aplica_no_dna_e_atualiza_ciclo(sandbox):
    c = _cycle()
    p = lp.from_answer(dict(PARSED), cycle=c)
    r = lp.approve(p["patch_id"])
    assert r["ok"] and PARSED["dna_updates"][0] in r["rules_added"]
    assert PARSED["dna_updates"][0] in (sandbox / "dna.md").read_text("utf-8")        # APLICOU
    judge = json.loads((sandbox / "judge.json").read_text("utf-8"))
    assert any(a["what"] == "sofa_box_block" for a in judge["anti_patterns"])
    cc = cycles.get_cycle("CYCLE-001")
    assert PARSED["dna_updates"][0] in cc["learning"]["new_rules"]
    assert lp.get_patch(p["patch_id"])["status"] == "applied"


def test_approve_idempotente(sandbox):
    c = _cycle()
    p = lp.from_answer(dict(PARSED), cycle=c)
    lp.approve(p["patch_id"])
    assert lp.approve(p["patch_id"])["ok"] is False   # já aplicado, não duplica


def test_reject_nao_toca_dna(sandbox):
    c = _cycle()
    p = lp.from_answer(dict(PARSED), cycle=c)
    lp.reject(p["patch_id"], "não curti")
    assert PARSED["dna_updates"][0] not in (sandbox / "dna.md").read_text("utf-8")
    assert lp.get_patch(p["patch_id"])["status"] == "rejected"


def test_derive_status_reflete_estado(sandbox):
    c = cycles.new_cycle(asset="sofa", microtask="MT", mode="REFERENCE_PACK", cycle_id="CYCLE-002", ts=1.0)
    assert cycles.derive_status(c) == "waiting_felipe_curation"
    c["references"]["main"] = ["r1"]
    cycles.save_cycle(c)
    assert cycles.derive_status(c) == "ready_for_sofa_build_spec_after_gpt_patch"
    c["learning"]["new_rules"] = ["x"]
    cycles.save_cycle(c)
    assert cycles.derive_status(c) == "ready_for_build_spec"
