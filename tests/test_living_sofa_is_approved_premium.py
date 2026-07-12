"""Regressão: o BUILDER DE PRODUÇÃO (`build_sofa(derive_living_sofa(...))`, o que
`furnish` e as cenas de sala usam) TEM que emitir o sofá premium APROVADO
(programa sofa_premium, alt_001-005), não o bloco antigo.

Este teste existe por causa de uma falha real (2026-07-12): a melhoria do sofá foi
validada só num harness isolado (renders "clay") e NUNCA foi dobrada no
`sofa_builder` de produção. Resultado: toda cena continuou saindo com o sofá velho
(pés soltos + almofadas empilhadas = as "caixas empilhadas" que o GPT reprova), e
nada gritou porque não havia teste ligando a APROVAÇÃO ao ARTEFATO que embarca.

Lição: uma melhoria aprovada num harness só conta quando um teste regressivo a trava
no builder de PRODUÇÃO — senão produção segue embarcando o antigo em silêncio.

RED até o premium (alt_001-005) ser integrado ao `sofa_builder`. Depois vira o
guarda-corpo contra regressão. Fonte da aprovação:
artifacts/review/sofa_premium/STATUS.md.
"""
from __future__ import annotations

import re

from tools.sofa_builder import build_sofa
from tools.sofa_class import derive_living_sofa

WIDTHS_M = [1.9, 2.1, 2.8]  # nichos reais de sala; a classe fixa só a largura


def _living_parts(width_m: float) -> list[dict]:
    parts, _ = build_sofa(derive_living_sofa(width_m))
    return parts


def test_seat_cushions_are_single_crowned_not_stacked_blocks() -> None:
    """alt_004 (APROVADO, IMPROVED blockiness 5->2): cada assento = UMA almofada
    coroada. O builder antigo empilha base + `_top` — a blockiness que o alt_004
    removeu. Se o empilhamento voltar (ou nunca sair), isto quebra."""
    for w in WIDTHS_M:
        stacked = sorted(
            p["label"] for p in _living_parts(w)
            if p["kind"] == "seat_cushion" and str(p["label"]).endswith("_top")
        )
        assert not stacked, (
            f"[w={w}m] sofá de produção ainda empilha almofadas ({stacked}); "
            "o premium aprovado (alt_004) usa almofada única coroada"
        )


def test_place_sofa_boxes_carries_profiles_for_curved_render() -> None:
    """O furnish (place_sofa_boxes) TEM que carregar o PERFIL (profile_world +
    extrude_vec, já no mundo) das peças curvas — senão o place_layout_skp.rb desenha
    CAIXA e o sofá vira 'quadrado zoado' na planta (bug 2026-07-12). Padrão p/ qualquer
    peça com profile, não só sofá."""
    from tools.sofa_builder import place_sofa_boxes

    parts, _ = build_sofa(derive_living_sofa(2.1))
    boxes = place_sofa_boxes(parts, (100.0, 100.0), (-1, 0))
    curved = [b for b in boxes if b.get("profile_world")]
    assert len(curved) >= 8, (
        f"só {len(curved)} peças carregam profile_world; o furnish vai achatar o sofá "
        "em caixa (as curvas — braços/base/almofadas — precisam do perfil no mundo)"
    )
    for b in curved:
        assert b.get("extrude_vec"), f"{b['label']} sem extrude_vec (não extruda)"
        assert len(b["profile_world"]) >= 3, f"{b['label']} face de perfil degenerada"


def test_composed_living_scene_sofa_is_premium() -> None:
    """OUTRO caminho de produção: o SceneComposer (intent → sofa_spec → build_sofa) —
    NÃO passa por derive_living_sofa. Bug 2026-07-12: o composer embarcava o sofá velho
    mesmo com o furnish já corrigido. A lição é que CADA caminho precisa da trava: aqui
    compomos a cena boutique real e exigimos o sofá premium (plinto, almofada única)."""
    import json

    from interior.composer.scene_composer import ROOT, compose_scene

    intent = json.loads(
        (ROOT / "fixtures/scene_intents/living_room_black_wood_gold_boutique.json")
        .read_text("utf-8")
    )
    sofa = [p for p in compose_scene(intent)["parts"] if p.get("item") == "sofa"]
    assert sofa, "cena composta sem sofá?"
    loose = [p["label"] for p in sofa if re.fullmatch(r"foot_\d+", str(p.get("label", "")))]
    tops = [p["label"] for p in sofa if str(p.get("label", "")).endswith("_top")]
    assert not loose, f"SceneComposer ainda emite pés de canto ({loose}); premium=plinto"
    assert not tops, f"SceneComposer ainda empilha almofadas ({tops}); premium=coroada"


def test_base_is_plinth_no_loose_feet() -> None:
    """alt_002 (APROVADO): base = plinto recuado, PÉS ELIMINADOS. O builder antigo
    emite foot_1..foot_4. Nota: o plinto também tem kind=='foot' (label 'plinth'),
    então checamos o LABEL foot_N (pé de canto solto), não o kind."""
    for w in WIDTHS_M:
        loose = [p["label"] for p in _living_parts(w)
                 if re.fullmatch(r"foot_\d+", str(p["label"]))]
        assert not loose, (
            f"[w={w}m] sofá de produção ainda tem pés de canto soltos ({loose}); "
            "o premium aprovado (alt_002) usa plinto (label 'plinth', sem foot_N)"
        )
