"""FP-034 — eixos tipados do variant sweep (deterministicos, fontes vivas).
Hermetico: le so dados TRACKED read-only (style_spec, themes/*.json); zero
escrita fora de tmp, zero rede, zero SketchUp."""
from __future__ import annotations

from tools.style_spec import STYLE_TOKENS
from tools.variant_axes import Variant, default_axes, layout_axis, style_axis, theme_axis
from tools.variant_sweep import expand_axes


def test_expand_axes_is_deterministic_and_ordered():
    a = expand_axes()
    b = expand_axes()
    assert a == b
    assert len(a) == (len(style_axis()) * len(theme_axis()) * len(layout_axis()))
    # ordem canonica do produto: style mais lento, layout mais rapido
    n_layout = len(layout_axis())
    assert [v.layout_seed for v in a[:n_layout]] == layout_axis()
    assert all(v.style is None for v in a[:n_layout])


def test_expand_axes_n_limits_cells():
    full = expand_axes()
    four = expand_axes(n=4)
    assert len(four) == 4
    assert four == full[:4]  # prefixo do grid, nao amostra aleatoria


def test_variant_id_is_stable_for_same_params():
    v1 = Variant(plant="planta_74", style="industrial", theme="dark_walnut",
                 layout_seed=2)
    v2 = Variant(plant="planta_74", style="industrial", theme="dark_walnut",
                 layout_seed=2)
    assert v1.variant_id == v2.variant_id
    assert v1 == v2
    ids = {v.variant_id for v in expand_axes()}
    assert len(ids) == len(expand_axes())  # params distintos -> ids distintos
    # baseline legivel: None/"" nao viram "None"/"" no id
    v0 = Variant(plant="planta_74", style=None, theme="", layout_seed=0)
    assert v0.variant_id == "planta_74__baseline__warm_compact__L0"


def test_style_axis_reads_style_tokens_source():
    assert style_axis() == [None] + sorted(STYLE_TOKENS)


def test_theme_axis_reads_real_presets():
    # 4 presets tracked em artifacts/reference_lab/themes -> 4 tokens KITCHEN_THEME
    # ('' = warm_compact default primeiro; demais ordenados)
    assert theme_axis() == ["", "black_wood_gold", "dark_walnut", "hotel_boutique"]


def test_default_axes_shape():
    ax = default_axes()
    assert set(ax) == {"style", "theme", "layout"}
    assert ax["layout"] == [0, 1, 2]
