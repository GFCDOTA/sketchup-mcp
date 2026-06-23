"""Testes determinísticos do validador por tema (fingerprint + schema de checks). NÃO chama o
LLM nem o modelo de visão (isso é integração). Imagens sintéticas em tmp."""
import numpy as np
import pytest
from PIL import Image

from tools.interior_studio import theme_registry as reg
from tools.interior_studio import theme_intern as ti
from tools.interior_studio.render_fingerprint import fingerprint


def _png(tmp, name, rgb, size=(80, 80)):
    arr = np.full((size[1], size[0], 3), rgb, dtype=np.uint8)
    p = tmp / name
    Image.fromarray(arr).save(p)
    return p


def test_fingerprint_preto_eh_escuro_sem_estouro(tmp_path):
    fp = fingerprint(_png(tmp_path, "black.png", [10, 10, 10]))
    assert fp["exposure"]["mean_lum"] < 15
    assert fp["clipped_pct"] == 0.0
    assert fp["near_black_pct"] > 90


def test_fingerprint_branco_estoura(tmp_path):
    fp = fingerprint(_png(tmp_path, "white.png", [255, 255, 255]))
    assert fp["clipped_pct"] > 99
    assert fp["exposure"]["mean_lum"] > 250


def test_fingerprint_calor_positivo_quando_vermelho_domina(tmp_path):
    assert fingerprint(_png(tmp_path, "warm.png", [200, 120, 40]))["warmth"] > 0   # R>B
    assert fingerprint(_png(tmp_path, "cold.png", [40, 120, 200]))["warmth"] < 0   # B>R


def test_eval_check_caverna_deterministica_reprova():
    check = next(c for c in reg.load_theme("black_wood_gold")["checks"] if c["id"] == "not_cave")
    fp = {"exposure": {"mean_lum": 26}}                       # v1-like = caverna
    r = reg.eval_check(check, fp, vision_answers={})
    assert r["status"] == "FAIL"


def test_blowout_deterministico_reprova_mas_so_visao_no_maximo_warn():
    check = next(c for c in reg.load_theme("black_wood_gold")["checks"] if c["id"] == "no_blowout")
    # clipado alto = estouro REAL determinístico -> FAIL
    assert reg.eval_check(check, {"clipped_pct": 5.0}, {})["status"] == "FAIL"
    # clipado 0 mas visão "acha" que estourou -> só WARN (determinístico não viu; visão é consultiva)
    assert reg.eval_check(check, {"clipped_pct": 0.0}, {"no_blowout": True})["status"] == "WARN"


def test_visao_nao_derruba_o_deterministico_so_escala_pra_warn():
    # not_cave: determinístico PASS (mean alto); visão grita caverna -> NO MÁXIMO WARN (não FAIL)
    check = next(c for c in reg.load_theme("black_wood_gold")["checks"] if c["id"] == "not_cave")
    r = reg.eval_check(check, {"exposure": {"mean_lum": 60}}, vision_answers={"not_cave": True})
    assert r["status"] == "WARN"


def test_check_advisory_de_visao_nunca_da_fail_sozinho():
    # no_fake_gold é só-visão (advisory): qwen2.5vl super-dispara -> cap em WARN, nunca FAIL
    check = next(c for c in reg.load_theme("black_wood_gold")["checks"] if c["id"] == "no_fake_gold")
    assert reg.eval_check(check, {}, {"no_fake_gold": True})["status"] == "WARN"


def test_warm_metals_frio_vira_warn():
    check = next(c for c in reg.load_theme("black_wood_gold")["checks"] if c["id"] == "warm_metals")
    assert reg.eval_check(check, {}, {"warm_metals": "prata frio"})["status"] == "WARN"
    assert reg.eval_check(check, {}, {"warm_metals": "bronze quente"})["status"] == "PASS"


def test_overall_status_pega_o_pior():
    assert ti.overall_status([{"status": "PASS"}, {"status": "WARN"}, {"status": "FAIL"}]) == "FAIL"
    assert ti.overall_status([{"status": "PASS"}, {"status": "WARN"}]) == "WARN"
    assert ti.overall_status([{"status": "PASS"}, {"status": "UNKNOWN"}]) == "PASS"


def test_registry_tema_carrega_com_estagiario_e_schema():
    t = reg.load_theme("BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE")   # alias/preset name resolve
    assert t["id"] == "black_wood_gold"
    assert t["intern"]["id"] == "intern-nero"
    assert any(c["id"] == "no_fake_gold" for c in t["checks"])
    assert len(reg.vision_questions(t)) >= 5


def test_validate_so_deterministico_sem_rede(tmp_path):
    # run_vision=False, run_intern=False -> nenhum LLM; checks de visão ficam UNKNOWN/sem sinal
    p = _png(tmp_path, "dark.png", [12, 11, 10])
    v = ti.validate(p, "black_wood_gold", run_intern=False, run_vision=False)
    assert v["theme"] == "black_wood_gold" and v["intern"] == "intern-nero"
    nc = next(c for c in v["checks"] if c["id"] == "not_cave")
    assert nc["status"] == "FAIL"        # mean_lum ~11 -> caverna determinística
