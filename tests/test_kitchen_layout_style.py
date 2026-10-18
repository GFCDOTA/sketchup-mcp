"""Diretriz BLACK_WOOD_GOLD moody premium na cozinha (feedback Felipe 2026-07-27:
"muito branca, não tem pia, cooktop feio").

Trava os contratos DETERMINÍSTICOS da DesignDirectiveSpec no nível dos boxes:
- CHECK-1 zero-branco: nenhuma cor da paleta de cozinha lê como branco (exceto LED).
- Pia lê de CIMA: abertura escura undermount acima do plano do tampo, sem aro inox
  levantado; torneira em L (montante + bica) + aro bronze = o ÚNICO ponto de ouro.
- Cooktop vitrocerâmico: vidro FINO (≤10mm) quase flush, 4 zonas circulares
  (octógonos low-poly), não caixotes.
- Geladeira preto fosco (D8), NUNCA inox claro.
O veredito visual segue sendo humano/GPT — isto pina a GEOMETRIA/PALETA, não beleza.
"""
from __future__ import annotations

# Maioria destes testes usa M()/pecas sinteticas (escala nao importa pro
# contrato de paleta/geometria). Só test_filler_never_penetrates_neighbors
# carrega planta_74 real — marcado @pytest.mark.planta74_scale pelo
# tests/conftest.py (roda na invocacao `pytest -m planta74_scale` separada).
from shapely.geometry import box as sbox  # noqa: E402

from tools import kitchen_layout as kl  # noqa: E402

WS_V = {"orient": "v", "sgn": 1}
M2IN = kl.M2IN


def _pieces(kind, w_m, d_m, h_m, z0_m):
    shp = sbox(0, 0, kl.M(w_m), kl.M(d_m))
    return kl._kmod(kind, shp, h_m, [0, 0, 0], z0_m, WS_V)


def _tops_m(p):
    return (p["z0_in"] + p["h_in"]) / M2IN


def test_palette_has_no_white_surfaces_except_led():
    for name, rgb in kl._KC.items():
        if name == "led":   # highlight pontual permitido (CHECK-1 da diretriz)
            continue
        assert sum(rgb) / 3 <= 200, f"_KC[{name!r}]={rgb} lê como branco/creme"


def test_fridge_is_samsung_rt42_duplex_real_dims():
    # Felipe 2026-07-28 (foto): Samsung RT42 Evolution duplex — 700x672x1785mm
    # (âncora REAL, samsung.com/br). Inox ESCURO escovado, freezer em CIMA,
    # HANDLELESS (zero barra de puxador), friso claro na divisão.
    assert abs(kl.GEL_W - 0.700) < 0.01, f"largura {kl.GEL_W} != RT42 (0.700)"
    assert abs(kl.GEL_H - 1.785) < 0.01, f"altura {kl.GEL_H} != RT42 (1.785)"
    assert abs(kl.GEL_D - 0.672) < 0.01, f"prof {kl.GEL_D} != RT42 (0.672)"
    ps = _pieces("geladeira", kl.GEL_D, kl.GEL_W, kl.GEL_H, 0.0)
    body = [p for p in ps if p["kind"] == "kc_geladeira"]
    assert body, "geladeira sem corpo"
    for p in body:
        m = sum(p["rgb"]) / 3
        assert 90 <= m <= 160, f"fora do inox escuro escovado da foto: {p['rgb']}"
    assert not [p for p in ps if p["kind"] == "kc_puxador"], \
        "RT42 é handleless — nada de barra de puxador"
    friso = [p for p in ps if p["kind"] == "kc_inox"]
    assert friso, "sem o friso claro da divisão freezer/geladeira"


def test_cooktop_glass_is_thin_and_near_flush():
    ps = _pieces("cooktop", 0.46, 0.50, 0.02, kl.COOK_Z0)
    glass = [p for p in ps if p["kind"] == "kc_vidro"]
    assert glass, "cooktop sem vidro"
    for g in glass:
        assert g["h_in"] <= 10 / 25.4 + 1e-6, "vidro grosso demais (bloco, não vitro)"
        assert _tops_m(g) <= 0.90 + 0.008 + 1e-6, "vidro > 8mm acima do plano do tampo"
        assert _tops_m(g) >= 0.90, "vidro afundado (invisível sob o tampo)"


def test_cooktop_has_4_circular_zones():
    ps = _pieces("cooktop", 0.46, 0.50, 0.02, kl.COOK_Z0)
    discs = [p for p in ps if p["kind"] == "kc_boca"]
    assert len(discs) == 4, f"esperava 4 zonas, veio {len(discs)}"
    for d in discs:
        assert len(d["corners"]) >= 8, "boca quadrada — diretriz pede disco (octógono+)"


def test_sink_reads_from_top_without_raised_rim():
    ps = _pieces("pia", 0.50, 0.46, 0.02, 0.90)
    cuba_top = [p for p in ps if p["kind"] == "kc_cuba" and _tops_m(p) >= 0.90]
    assert cuba_top, "cuba invisível de cima (escondida sob o tampo sólido)"
    raised_inox = [p for p in ps if p["kind"] == "kc_inox" and _tops_m(p) > 0.90]
    assert not raised_inox, "undermount não tem aro inox levantado (D5)"


def test_upper_run_closes_to_ceiling_no_dust_gap():
    # Felipe 2026-07-28: "outra seção de armário em cima até o teto pra evitar
    # poeira" — maleiro fecha o vão acima do aéreo (topo >= teto-2cm), com
    # portas próprias em prumada (mesmo nº de módulos da seção de baixo).
    ps = _pieces("aereo", 0.33, 1.80, kl.AEREO_H, kl.AEREO_Z0)
    top = max(_tops_m(p) for p in ps)
    assert top >= kl.CEILING_H - 0.02, f"vão pega-poeira: topo em {top:.2f}m, teto {kl.CEILING_H}m"
    lower_doors = [p for p in ps if p["kind"] == "kc_porta_sup"
                   and p["z0_in"] / M2IN < kl.AEREO_Z0 + kl.AEREO_H]
    maleiro_doors = [p for p in ps if p["kind"] == "kc_porta_sup"
                     and p["z0_in"] / M2IN >= kl.AEREO_Z0 + kl.AEREO_H]
    assert maleiro_doors, "maleiro sem portas (virou tampão cego)"
    assert len(maleiro_doors) == len(lower_doors) + (1 if any(
        p["kind"] == "kc_niche_wood" for p in ps) else 0), \
        "prumada quebrada: módulos do maleiro != módulos de baixo"


def test_maleiro_projects_forward_of_lower_uppers():
    # Referência do Felipe (2026-07-28): "tem um armário que vem mais pra frente
    # em cima" — o maleiro OVERHANG é mais fundo que o aéreo recuado (gramática
    # da imagem: plano superior avança, LED lava o recuo por baixo).
    ps = _pieces("aereo", 0.33, 1.80, kl.AEREO_H, kl.AEREO_Z0)

    def depth(p):   # WS_V: profundidade = extensão em x (inches)
        return p["x1"] - p["x0"]

    split = kl.AEREO_Z0 + kl.AEREO_H
    lower = max(depth(p) for p in ps if p["kind"] == "kc_corpo_sup"
                and p["z0_in"] / M2IN < split)
    maleiro = max(depth(p) for p in ps if p["kind"] == "kc_corpo_sup"
                  and p["z0_in"] / M2IN >= split)
    assert maleiro >= lower + 0.15 * M2IN, \
        f"maleiro não avança sobre o aéreo: {maleiro:.1f}in vs {lower:.1f}in"


def test_filler_never_penetrates_neighbors():
    # Felipe 2026-07-28: "colocou um armário DENTRO da geladeira" — o gable era
    # CENTRADO na junção (metade dentro de cada vizinho). Filler só existe se
    # existe GAP, e mora só nele: interseção 3D com geladeira/bancada/aéreos <=1cm.
    import json
    from pathlib import Path
    con = json.loads(Path("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    boxes, out = kl.build_boxes(con, "r004")
    mods = {}
    for b in boxes:
        mods.setdefault(b.get("module", b["kind"]), []).append(b)
    if "filler" not in mods:
        return   # sem gap -> sem filler: exatamente o contrato

    def bb3(ps):
        return (min(p["x0"] for p in ps), min(p["y0"] for p in ps),
                max(p["x1"] for p in ps), max(p["y1"] for p in ps),
                min(p["z0_in"] for p in ps), max(p["z0_in"] + p["h_in"] for p in ps))

    fil = bb3(mods["filler"])
    for name in ("fridge", "base_cabinet_01", "upper_cabinet_01", "upper_cabinet_02"):
        if name not in mods:
            continue
        o = bb3(mods[name])
        dx = min(fil[2], o[2]) - max(fil[0], o[0])
        dy = min(fil[3], o[3]) - max(fil[1], o[1])
        dz = min(fil[5], o[5]) - max(fil[4], o[4])
        assert not (dx > 0.4 and dy > 0.4 and dz > 0.4), \
            f"filler penetra {name}: {round(dx,1)}x{round(dy,1)}x{round(dz,1)} in"


def test_fridge_tower_has_single_cabinet_to_ceiling():
    # Felipe 2026-07-28: "deixa só 1 armário em cima da geladeira" — porta ÚNICA,
    # do topo da geladeira até o teto; nada de seções empilhadas.
    h = (kl.CEILING_H - 0.01) - (kl.GEL_H - 0.05)
    ps = _pieces("aereo_fridge", kl.GEL_D, kl.GEL_W, h, kl.GEL_H - 0.05)
    doors = [p for p in ps if p["kind"] == "kc_porta_sup"]
    assert len(doors) == 2, f"torre com {len(doors)} folhas — referência 2 pede DUAS folhas num armário só"
    assert max(_tops_m(p) for p in ps) >= kl.CEILING_H - 0.02, "torre não fecha no teto"
    # "armário mais interessante": nicho de madeira aberto na base do armário.
    # (Proporção agora é ditada pela MEDIDA REAL da RS60 — 1.78m — não por estética.)
    assert any(p["kind"] == "kc_niche_wood" for p in ps), "sem nicho — voltou o blocão"


def test_faucet_is_L_shape_with_single_bronze_accent():
    ps = _pieces("pia", 0.50, 0.46, 0.02, 0.90)
    torneira = [p for p in ps if p["kind"] == "kc_torneira"]
    assert len(torneira) >= 2, "torneira precisa de montante + bica (forma em L)"
    zs = {round(p["z0_in"] / M2IN, 2) for p in torneira}
    assert len(zs) >= 2, "as peças da torneira não formam L (mesma base z)"
    bronze = [p for p in ps if p["kind"] == "kc_bronze"]
    assert len(bronze) == 1, "exatamente UM ponto de bronze (D4 — orçamento de ouro)"
