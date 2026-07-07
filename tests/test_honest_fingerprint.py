"""FP-039 Honest Visual Fingerprint v2 — taxonomia CONFIAVEL/ADVISORY/PROIBIDO. O gate decide SO com
o tier confiavel (funcao pura) e NUNCA emite julgamento estetico. Micro-fixtures deterministicas."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from tools.flat_white_gate import (
    NEUTRAL_DOM_WARN,
    WHITE_FRAC_FAIL,
    flat_white_check,
    verdict_from_reliable,
)
from tools.interior_studio.render_fingerprint import (
    FORBIDDEN_JUDGMENT_TERMS,
    METRIC_TIERS,
    fingerprint,
    large_flat_area_frac,
)

ROOT = Path(__file__).resolve().parents[1]
TEX_DIR = ROOT / "assets/textures/procedural"
_W, _H = 800, 600


def _white(p):
    a = np.full((_H, _W, 3), (247, 247, 245), np.uint8)
    a[200:400, 200:600] = (238, 236, 232)
    Image.fromarray(a).save(p)
    return p


def _monotone(p):
    rng = np.random.default_rng(7)
    a = np.clip(np.array([182, 176, 168]) + rng.normal(0, 3, (_H, _W, 3)), 0, 255).astype(np.uint8)
    Image.fromarray(a).save(p)
    return p


def _textured(p):
    a = np.full((_H, _W, 3), (176, 174, 170), np.uint8)
    for (x0, y0, x1, y1), png in [((100, 60, 700, 220), "concrete.png"),
                                  ((150, 320, 450, 520), "fabric_charcoal.png"),
                                  ((500, 350, 700, 500), "wood_dark.png")]:
        t = np.asarray(Image.open(TEX_DIR / png).convert("RGB"))
        th, tw = t.shape[:2]
        h, w = y1 - y0, x1 - x0
        a[y0:y1, x0:x1] = np.tile(t, (h // th + 1, w // tw + 1, 1))[:h, :w]
    Image.fromarray(a).save(p)
    return p


def _varied(p):
    a = np.full((_H, _W, 3), (120, 140, 90), np.uint8)
    a[60:280, 60:380] = (40, 90, 180)
    a[60:280, 420:760] = (190, 70, 50)
    a[320:560, 60:400] = (60, 160, 80)
    Image.fromarray(a).save(p)
    return p


# ---------------------------------------------------------------- contrato dos TIERS
def test_metric_tiers_partition():
    rel = set(METRIC_TIERS["reliable"])
    adv = set(METRIC_TIERS["advisory"])
    assert rel and adv
    assert rel.isdisjoint(adv), "uma metrica nao pode ser confiavel E advisory"


def test_large_flat_area_is_advisory_not_reliable():
    # calibracao demoveu: parede/piso/blocos coloridos legitimos sao solidos -> confunde
    assert "large_flat_area_frac" in METRIC_TIERS["advisory"]
    assert "large_flat_area_frac" not in METRIC_TIERS["reliable"]


def test_fingerprint_exposes_both_tiers(tmp_path):
    fp = fingerprint(_textured(tmp_path / "t.png"))
    assert set(fp["reliable"]) == set(METRIC_TIERS["reliable"])
    assert set(fp["advisory"]) == set(METRIC_TIERS["advisory"])


# ---------------------------------------------------------------- veredito = funcao PURA do confiavel
def test_verdict_is_pure_function_of_reliable():
    # verdict_from_reliable NEM ACEITA advisory -> impossivel a advisory influenciar o veredito.
    base = {"near_white_frac": 0.0, "neutral_dominance": 0.5, "contrast_std": 40.0}
    assert verdict_from_reliable(base)["result"] == "PASS"
    assert verdict_from_reliable({**base, "near_white_frac": 0.6})["result"] == "FAIL"
    # neutro_monotono exige neutro ALTO E contraste baixo (senao e greyscale detalhado, ok):
    assert verdict_from_reliable({**base, "neutral_dominance": 0.95, "contrast_std": 10.0})["result"] == "WARN"
    assert verdict_from_reliable({**base, "neutral_dominance": 0.95})["result"] == "PASS"  # contraste 40 = detalhado


def test_gate_result_equals_verdict_of_reliable(tmp_path):
    for b in (_white, _monotone, _textured, _varied):
        p = b(tmp_path / f"{b.__name__}.png")
        fp = fingerprint(p)
        assert flat_white_check(p)["result"] == verdict_from_reliable(fp["reliable"])["result"]


def test_verdict_ignores_advisory_even_when_extreme():
    # INJETA advisory EXTREMO num input -> veredito TEM que ser identico (verdict_from_reliable so le
    # as chaves reliable). Se algum dia a func ler uma chave advisory, este teste FALHA (trava a pureza).
    rel = {"near_white_frac": 0.1, "neutral_dominance": 0.4, "contrast_std": 30.0}
    poisoned = {**rel, "texture_frac": 1.0, "edge_frac": 1.0, "palette_entropy": 9.9,
                "large_flat_area_frac": 1.0}
    assert verdict_from_reliable(rel) == verdict_from_reliable(poisoned)


def _all_strings(obj):
    """Todas as strings (chaves + valores, recursivo) de um dict/list — pra varrer o output inteiro."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out += _all_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += _all_strings(v)
    elif isinstance(obj, str):
        out.append(obj)
    return out


# ---------------------------------------------------------------- PROIBIDO: nada de estetica
def test_gate_never_emits_aesthetic_judgment(tmp_path):
    for b in (_white, _monotone, _textured, _varied):
        r = flat_white_check(b(tmp_path / f"{b.__name__}.png"))
        blob = " ".join(_all_strings(r)).lower()   # varre TODO o output (chaves + valores, recursivo)
        for term in FORBIDDEN_JUDGMENT_TERMS:
            assert term not in blob, f"gate emitiu julgamento estetico proibido: {term!r}"


# ---------------------------------------------------------------- sinais confiaveis (micro-fixture)
def test_white_still_fails(tmp_path):
    r = flat_white_check(_white(tmp_path / "w.png"))
    assert r["result"] == "FAIL" and "chapado_de_branco" in r["flags"]


def test_neutral_dominance_warns_on_monotone(tmp_path):
    r = flat_white_check(_monotone(tmp_path / "m.png"))
    assert r["result"] in ("WARN", "FAIL") and "neutro_monotono" in r["flags"]
    assert r["reliable"]["neutral_dominance"] >= NEUTRAL_DOM_WARN


def test_textured_deliverable_not_false_failed(tmp_path):
    # o proprio artefato do FP-036/037 (parede/madeira/tecido) NAO pode ser FALHADO
    assert flat_white_check(_textured(tmp_path / "t.png"))["result"] != "FAIL"


def test_varied_colorful_passes(tmp_path):
    assert flat_white_check(_varied(tmp_path / "v.png"))["result"] == "PASS"


# ---------------------------------------------------------------- compat + determinismo
def test_fingerprint_backward_compatible(tmp_path):
    fp = fingerprint(_textured(tmp_path / "t.png"))
    for k in ("exposure", "clipped_pct", "near_black_pct", "warmth", "palette", "zones",
              "near_white_pct", "texture_frac"):
        assert k in fp, f"chave antiga {k} sumiu (quebraria render_judge / gate v1)"


def test_advisory_metrics_present(tmp_path):
    fp = fingerprint(_varied(tmp_path / "v.png"))
    for k in ("texture_frac", "edge_frac", "palette_entropy", "large_flat_area_frac"):
        assert k in fp["advisory"]


def test_large_flat_area_frac_deterministic(tmp_path):
    arr = np.asarray(Image.open(_varied(tmp_path / "v.png")).convert("RGB")).astype(float)
    assert large_flat_area_frac(arr) == large_flat_area_frac(arr)
