"""P3a-02 — convencao do poligono de comodo nas fixtures sinteticas (FP-043).

Reproducao: o guarda-roupa da fixture sintetica `bedroom_medium_14m2` fica ~4,5 cm DENTRO da
parede oeste. Causa: o gerador pos o poligono no EIXO da parede; na planta_74 (consensus
curado) os vertices ficam na FACE INTERNA (meia espessura do eixo) e o planner afasta os
moveis do poligono. Nao e defeito do planner: a fixture antiga viola a convencao do consensus.
A fixture nova `*_inner_face` segue a convencao e os moveis ficam fora da parede.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.rooms.bedroom.capabilities.make_synthetic_bedrooms import classify_polygon_convention, rect_bedroom

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "fixtures/synthetic_rooms"
IN = 0.0254


def _load(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def test_planta_74_usa_poligono_na_face_interna():
    con = _load(ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
    # varanda/cozinha tem vertices a ~6 pts (soft barriers): ficam 'ambiguous'; o quarto de parede fechada nao.
    quartos = dict(con, rooms=[r for r in con["rooms"] if r["name"] == "SUITE 02"])
    assert classify_polygon_convention(quartos) == "inner_face"


def test_fixture_antiga_esta_no_eixo_e_a_nova_na_face_interna():
    assert classify_polygon_convention(_load(SYN / "bedroom_medium_14m2.json")) == "axis"
    assert classify_polygon_convention(_load(SYN / "bedroom_medium_14m2_inner_face.json")) == "inner_face"


def test_poligono_do_gerador_respeita_a_convencao_pedida():
    assert classify_polygon_convention(rect_bedroom("Q", 3.5, 4.0)) == "axis"
    assert classify_polygon_convention(rect_bedroom("Q", 3.5, 4.0, polygon_convention="inner_face")) == "inner_face"


@pytest.mark.parametrize("bad", [
    {},                                                                  # vazio
    {"walls": [], "rooms": [], "wall_thickness_pts": 5.4},               # sem parede
    {"walls": [{"start": [0, 0], "end": [9, 0]}], "rooms": [{"id": "r", "polygon_pts": [[0, 0], [1, 1]]}],
     "wall_thickness_pts": 5.4},                                         # poligono degenerado
    {"walls": [{"start": [0, 0], "end": [9, 0]}], "rooms": [{"id": "r", "polygon_pts": [[0, 0], [9, 0], [9, 9]]}],
     "wall_thickness_pts": 0},                                           # espessura invalida
])
def test_entrada_invalida_e_rejeitada_sem_adivinhar(bad):
    with pytest.raises(ValueError):
        classify_polygon_convention(bad)


def test_convencao_desconhecida_no_gerador_e_rejeitada():
    with pytest.raises(ValueError):
        rect_bedroom("Q", 3.5, 4.0, polygon_convention="outer")


SYN_SCALE = "0.03518518518518519"   # 5.4/0.19 m/pt: a escala dos shells sinteticos (core.scale default)
_PROBE = (
    "import json,sys;from core import scale;from tools.furnish_apartment import collect_boxes;"
    "c=json.load(open(sys.argv[1],encoding='utf-8'));b,_=collect_boxes(c);"
    "print('@@'+json.dumps({'face_in':c['wall_thickness_pts']/2*scale.PT_TO_M/0.0254,"
    "'boxes':[[x['kind'],x['label'],x['x0'],x['y0'],x['x1'],x['y1']] for x in b if not x.get('decorative')]}))"
)


def _plan(path: Path) -> dict:
    """Roda o planner de producao num processo limpo com a escala do shell sintetico (PT_TO_M e lido 1x por processo)."""
    import os
    import subprocess
    import sys
    env = {**os.environ, "PT_TO_M": SYN_SCALE, "PYTHONPATH": str(ROOT)}
    out = subprocess.run([sys.executable, "-c", "import sys;sys.path.insert(0,sys.argv[2]);" + _PROBE, str(path), str(ROOT)], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120, check=True).stdout
    return json.loads(out[out.index("@@") + 2:])


def test_planner_ignora_a_convencao_do_poligono_logo_ela_nao_causa_o_achado():
    """Refuta a hipotese 'polygon no eixo': o planner deriva o vao das PAREDES (compute_room_floors),
    entao eixo x face interna da o MESMO layout. A causa e o vao ser a LAJE (entra 0,4*t sob a parede)."""
    assert _plan(SYN / "bedroom_medium_14m2.json")["boxes"] == _plan(SYN / "bedroom_medium_14m2_inner_face.json")["boxes"]


def test_repro_moveis_entram_na_parede_na_fixture_sintetica():
    """Repro do achado L2 (guarda-roupa ~4,5 cm na parede oeste). Documenta o defeito do planner."""
    r = _plan(SYN / "bedroom_medium_14m2_inner_face.json")
    x0 = min(b[2] for b in r["boxes"])
    assert 0.03 < (r["face_in"] - x0) * IN < 0.06, (r["face_in"], x0)


@pytest.mark.xfail(strict=True, reason="FP-043 P3a-03: planner mobilia sobre a laje (tuck 0,4*t); trocar o vao global "
                                       "tira layout valido da SUITE 02 e quebra o anchor da pia -> correcao por ambiente")
def test_contrato_nenhum_movel_dentro_da_parede():
    r = _plan(SYN / "bedroom_medium_14m2_inner_face.json")
    assert min(b[2] for b in r["boxes"]) >= r["face_in"] - 1e-6


def test_circulacao_da_varanda_sintetica_segue_visivel_como_warn():
    """Sala media sintetica: o circulation_gate reprova a porta da varanda; o furnish so loga WARN.
    O teste trava que o achado NAO vira sucesso silencioso (se for corrigido, atualizar junto com P3a-03)."""
    import os
    import subprocess
    import sys
    env = {**os.environ, "PT_TO_M": SYN_SCALE}
    code = ("import sys;sys.path.insert(0,sys.argv[2]);import json;from tools.furnish_apartment import collect_boxes;"
            "collect_boxes(json.load(open(sys.argv[1],encoding='utf-8')))")
    out = subprocess.run([sys.executable, "-c", code, str(SYN / "living_medium_rect_18m2.json"), str(ROOT)], cwd=ROOT,
                         env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=120, check=True).stdout
    assert "circulation_gate" in out and "FAIL" in out and "WARN" in out, out
