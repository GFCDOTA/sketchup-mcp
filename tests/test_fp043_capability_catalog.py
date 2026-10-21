"""FP-043/P5 — o catalogo de capacidades e o gate que o protege.

Positivo: o catalogo real passa. Negativos: cada defeito nomeado na spec (duplicata, simbolo inexistente, source
quebrada, evidencia velha, ferramenta fora da allowlist) reprova por um codigo proprio, sem tocar o catalogo real.
Estes testes provam INTEGRIDADE declarativa — nao geometria nem L2 novo.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.rooms import capability_catalog as cc
from tools.rooms import specialists as sp

ROOT = Path(__file__).resolve().parents[1]
CATALOG = cc.load_catalog()
PROFILES = {room: sp.load_profile(room) for room in cc.ROOMS}


def _verify(mutator) -> dict:
    cat = copy.deepcopy(CATALOG)
    mutator(cat)
    return cc.verify(cat, copy.deepcopy(PROFILES))


def _cap(cat, cid):
    return next(c for c in cat["capabilities"] if c["id"] == cid)


def test_catalogo_real_passa_e_cobre_as_nove_categorias():
    res = cc.verify()
    assert res["result"] == "PASS", res
    assert {c["room"] for c in CATALOG["capabilities"]} >= {"kitchen", "living", "bedroom", "bathroom", "service", "circulation"}
    assert {b["room"] for b in CATALOG["bindings"]} == set(cc.ROOMS) - {"service"} | {"service"}


def test_quatro_dimensoes_de_estado_sao_independentes_no_esquema():
    c = _cap(CATALOG, "kitchen.layout.galley")
    assert c["implementation"]["state"] == "IMPLEMENTED"
    assert c["validation"]["state"] == "L2_PASS"
    assert c["visual"]["state"] == "NOT_REVIEWED"           # L2_PASS nao implica aprovacao visual
    assert c["validation"]["evidence"][0]["sketchup_version"] == "26.0.429"


def test_capacidade_duplicada_reprova():
    res = _verify(lambda cat: cat["capabilities"].append(copy.deepcopy(_cap(cat, "kitchen.layout.galley"))))
    assert "DUPLICATE_CAPABILITY_ID" in res["errors"]


def test_binding_duplicado_reprova():
    res = _verify(lambda cat: cat["bindings"].append(copy.deepcopy(cat["bindings"][0])))
    assert "DUPLICATE_BINDING_ID" in res["errors"]


def test_simbolo_python_inexistente_reprova():
    def mutate(cat):
        _cap(cat, "kitchen.layout.galley")["implementation"]["symbols"][0]["ref"] = "tools.rooms.kitchen.layout.nao_existe"
    assert "SYMBOL_MISSING" in _verify(mutate)["errors"]


def test_simbolo_ruby_inexistente_reprova():
    def mutate(cat):
        _cap(cat, "kitchen.layout.galley")["implementation"]["symbols"][1]["ref"] = "tools/sketchup/furnish/nao_existe.rb"
    assert "SYMBOL_MISSING" in _verify(mutate)["errors"]


def test_source_quebrada_reprova():
    def mutate(cat):
        cat["bindings"][0]["source_ids"] = ["fonte-que-nao-existe"]
    assert "SOURCE_NOT_FOUND" in _verify(mutate)["errors"]


def test_recipe_quebrada_reprova():
    def mutate(cat):
        cat["bindings"][0]["recipe_ids"] = ["recipe.que.nao.existe"]
    assert "RECIPE_NOT_FOUND" in _verify(mutate)["errors"]


def test_evidencia_velha_reprova_quando_o_codigo_do_simbolo_muda():
    def mutate(cat):
        ev = _cap(cat, "kitchen.layout.galley")["validation"]["evidence"][0]
        key = next(iter(ev["symbol_digests"]))
        ev["symbol_digests"][key] = "0" * 64                  # digest do tempo da prova != codigo atual
    assert "EVIDENCE_STALE" in _verify(mutate)["errors"]


def test_l2_sem_evidencia_reprova():
    def mutate(cat):
        _cap(cat, "kitchen.layout.galley")["validation"]["evidence"] = []
    assert "L2_WITHOUT_EVIDENCE" in _verify(mutate)["errors"]


def test_l2_com_simbolo_sem_prova_reprova():
    def mutate(cat):
        ev = _cap(cat, "kitchen.layout.galley")["validation"]["evidence"][0]
        ev["symbol_digests"].pop(next(k for k in ev["symbol_digests"] if k.startswith("ruby:")))
    assert "L2_SYMBOL_WITHOUT_PROOF" in _verify(mutate)["errors"]


def test_validacao_afirmada_sobre_capacidade_planejada_reprova():
    def mutate(cat):
        _cap(cat, "shared.cabinet.parametric")["implementation"]["state"] = "PLANNED"      # afirma L1_PASS sobre algo so planejado
    assert "VALIDATION_CLAIM_WITHOUT_IMPLEMENTATION" in _verify(mutate)["errors"]


def test_implementada_sem_simbolo_reprova():
    def mutate(cat):
        _cap(cat, "kitchen.sink-anchor-guard")["implementation"]["symbols"] = []
    assert "IMPLEMENTED_WITHOUT_SYMBOL" in _verify(mutate)["errors"]


def test_l1_pass_sem_teste_ou_com_teste_inexistente_reprova():
    def sem_teste(cat):
        _cap(cat, "kitchen.sink-anchor-guard")["validation"]["tests"] = []

    def teste_fantasma(cat):
        _cap(cat, "kitchen.sink-anchor-guard")["validation"]["tests"] = ["tests/test_que_nao_existe.py"]
    assert "VALIDATION_WITHOUT_TEST" in _verify(sem_teste)["errors"]
    assert "FIXTURE_OR_TEST_MISSING" in _verify(teste_fantasma)["errors"]


def test_ferramenta_fora_da_allowlist_do_perfil_reprova():
    def mutate(cat):
        _cap(cat, "kitchen.layout.galley")["tools"].append("mcp:su_apply_edits")
    assert "TOOL_NOT_ALLOWLISTED" in _verify(mutate)["errors"]


def test_tecnica_ausente_sem_lacuna_declarada_reprova():
    def mutate(cat):
        next(b for b in cat["bindings"] if b["id"] == "bind.kitchen.drawer")["gap"] = ""
    assert "ABSENT_CAPABILITY_WITHOUT_GAP" in _verify(mutate)["errors"]


def test_binding_para_capacidade_inexistente_reprova():
    def mutate(cat):
        cat["bindings"][0]["capability_id"] = "kitchen.nao.existe"
    assert "CAPABILITY_NOT_FOUND" in _verify(mutate)["errors"]


def test_schema_rejeita_estado_fora_do_vocabulario_e_politica_trocada():
    def estado(cat):
        _cap(cat, "kitchen.layout.galley")["validation"]["state"] = "PROVEN"      # selo unico nao existe

    def politica(cat):
        cat["policy"] = "AUTHORIZE_EXECUTION"
    assert "SCHEMA" in _verify(estado)["errors"]
    assert "SCHEMA" in _verify(politica)["errors"]


def test_o_gate_roda_como_cli():
    import subprocess
    import sys
    done = subprocess.run([sys.executable, "-m", "tools.rooms.capability_catalog"], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0 and json.loads(done.stdout)["result"] == "PASS", done.stdout + done.stderr


@pytest.mark.parametrize("lang,ref", [("python", "tools.rooms.kitchen.layout.build_boxes"), ("ruby", "tools/sketchup/furnish/place_layout_skp.rb")])
def test_digest_do_simbolo_e_deterministico(lang, ref):
    s = {"lang": lang, "ref": ref}
    assert cc.symbol_digest(s) == cc.symbol_digest(s) and len(cc.symbol_digest(s)) == 64
