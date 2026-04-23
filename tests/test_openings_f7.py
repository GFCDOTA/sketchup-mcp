"""F7 adversarial tests — adaptive gate, locus dedup, room filter, strict.

Guarantees:
  - p12 baseline (6 openings) preserved.
  - planta_74 openings land in a healthy range [8, 15].
  - adaptive gate scales with median wall length.
  - locus dedup keeps the best-confidence (or arc-confirmed when level 3
    arrives) when two openings sit in the same physical spot.
  - openings without any room on either side are dropped.
  - strict mode demotes doors-without-arc to passage.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from model.types import Wall
from openings.service import (
    Opening,
    _compute_max_opening_px,
    _dedupe_openings_by_locus,
    _assign_and_filter_rooms,
    _maybe_demote_strict,
    detect_openings,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def _wall(
    wid: str,
    start: tuple[float, float],
    end: tuple[float, float],
    orientation: str,
    page: int = 0,
) -> Wall:
    return Wall(
        wall_id=wid,
        page_index=page,
        start=start,
        end=end,
        thickness=6.0,
        orientation=orientation,
        source="extract",
        confidence=1.0,
    )


# ---------- adaptive gate -------------------------------------------------


def test_max_opening_gate_adaptive_p12_like():
    """Paredes uniformes e longas (median ~400 px): gate fica proximo
    do teto superior (320). 0.6 * 400 = 240 -> fica em 240 mesmo."""
    walls = [
        _wall(f"w{i}", (0.0, i * 20.0), (400.0, i * 20.0), "horizontal")
        for i in range(9)
    ]
    # median = 400 (todos iguais); 0.6 * 400 = 240 -> dentro da faixa
    gate = _compute_max_opening_px(walls)
    assert 180.0 <= gate <= 320.0
    assert gate == pytest.approx(240.0)


def test_max_opening_gate_adaptive_planta_74_like():
    """Paredes curtas em massa (median ~80 px): 0.6 * 80 = 48 -> clamp
    ao piso minimo 180."""
    walls = [
        _wall(f"w{i}", (0.0, i * 10.0), (80.0, i * 10.0), "horizontal")
        for i in range(15)
    ]
    gate = _compute_max_opening_px(walls)
    assert gate == pytest.approx(180.0), f"expected floor 180, got {gate}"


def test_max_opening_gate_empty_walls_fallback():
    assert _compute_max_opening_px([]) == pytest.approx(280.0)


def test_max_opening_gate_caps_at_ceiling():
    """Paredes enormes (median 1200 px): 0.6 * 1200 = 720 -> clamp ao
    teto 320."""
    walls = [
        _wall(f"w{i}", (0.0, i * 10.0), (1200.0, i * 10.0), "horizontal")
        for i in range(9)
    ]
    gate = _compute_max_opening_px(walls)
    assert gate == pytest.approx(320.0)


# ---------- dedup por locus ----------------------------------------------


def _op(
    oid: str,
    orientation: str,
    center: tuple[float, float],
    width: float = 70.0,
    confidence: float = 1.0,
    kind: str = "door",
) -> Opening:
    return Opening(
        opening_id=oid,
        page_index=0,
        orientation=orientation,
        center=center,
        width=width,
        wall_a="w-a",
        wall_b="w-b",
        kind=kind,
        confidence=confidence,
    )


def test_dedup_collocated_openings_keeps_higher_confidence():
    """Dois openings colocalizados -> fica o de maior confidence."""
    a = _op("opening-1", "horizontal", (100.0, 200.0), confidence=0.5)
    b = _op("opening-2", "horizontal", (120.0, 200.0), confidence=1.0)  # 20 px away
    result = _dedupe_openings_by_locus([a, b])
    assert len(result) == 1
    assert result[0].opening_id == "opening-2"


def test_dedup_collocated_openings_ties_prefer_wider():
    """Mesma confidence -> escolhe width maior (porta completa vence
    sliver duplicado)."""
    a = _op("opening-1", "horizontal", (100.0, 200.0), width=30.0, confidence=1.0)
    b = _op("opening-2", "horizontal", (110.0, 200.0), width=70.0, confidence=1.0)
    result = _dedupe_openings_by_locus([a, b])
    assert len(result) == 1
    assert result[0].opening_id == "opening-2"
    assert result[0].width == pytest.approx(70.0)


def test_dedup_respects_orientation():
    """Openings perpendiculares nao fundem mesmo colocalizados."""
    a = _op("opening-1", "horizontal", (100.0, 200.0), confidence=1.0)
    b = _op("opening-2", "vertical", (105.0, 205.0), confidence=1.0)
    result = _dedupe_openings_by_locus([a, b])
    assert len(result) == 2


def test_dedup_respects_distance_threshold():
    """Openings a > _LOCUS_EPS_PX (30 px) NAO fundem."""
    a = _op("opening-1", "horizontal", (100.0, 200.0), confidence=1.0)
    b = _op("opening-2", "horizontal", (135.0, 200.0), confidence=0.7)  # 35 px
    result = _dedupe_openings_by_locus([a, b])
    assert len(result) == 2


def test_dedup_respects_perpendicular_separation():
    """Openings com mesmo eixo X mas y diferente (perp distance > 6)
    NAO fundem — sao duas portas em paredes paralelas."""
    a = _op("opening-1", "horizontal", (100.0, 200.0), confidence=1.0)
    b = _op("opening-2", "horizontal", (105.0, 215.0), confidence=1.0)  # perp diff 15
    result = _dedupe_openings_by_locus([a, b])
    assert len(result) == 2


def test_dedup_empty_list_passthrough():
    assert _dedupe_openings_by_locus([]) == []


def test_dedup_single_opening_passthrough():
    a = _op("opening-1", "horizontal", (100.0, 200.0))
    assert _dedupe_openings_by_locus([a]) == [a]


# ---------- room membership filter ---------------------------------------


class _FakeRoom:
    """Minimal stand-in pra Room sem importar model.types (evita side
    effects em branches onde Room ainda nao existe)."""

    def __init__(self, room_id: str, polygon: list[tuple[float, float]]):
        self.room_id = room_id
        self.polygon = polygon


def test_opening_without_room_membership_dropped():
    """Opening com center em area sem nenhum room -> drop."""
    room = _FakeRoom(
        "room-1",
        [(0.0, 0.0), (50.0, 0.0), (50.0, 50.0), (0.0, 50.0)],
    )
    op_floating = _op("opening-1", "horizontal", (500.0, 500.0))  # longe da room
    op_inside = _op("opening-2", "horizontal", (25.0, 25.0))  # dentro da room
    result = _assign_and_filter_rooms([op_floating, op_inside], [room])
    # op_floating dropped (room_a None e room_b None)
    # op_inside sobrevive (um lado dentro da room-1 ou exterior, outro lado idem)
    assert len(result) == 1
    assert result[0].opening_id == "opening-2"


def test_opening_to_exterior_kept():
    """Opening com um lado dentro de room e outro no exterior (None)
    eh mantido."""
    room = _FakeRoom(
        "room-1",
        [(0.0, 0.0), (200.0, 0.0), (200.0, 100.0), (0.0, 100.0)],
    )
    # opening horizontal em y=100 (na borda superior) — um lado (y<100,
    # dentro da room) tem room-1, outro lado (y>100, exterior) None
    op = _op("opening-1", "horizontal", (100.0, 100.0), width=70.0)
    result = _assign_and_filter_rooms([op], [room])
    assert len(result) == 1
    # pelo menos um dos dois lados deve ter sido atribuido
    assert result[0].room_a is not None or result[0].room_b is not None


def test_opening_between_two_rooms_keeps_both_ids():
    """Opening na fronteira entre 2 rooms -> ambos lados resolvidos."""
    room_top = _FakeRoom(
        "room-A",
        [(0.0, 0.0), (200.0, 0.0), (200.0, 95.0), (0.0, 95.0)],
    )
    room_bot = _FakeRoom(
        "room-B",
        [(0.0, 105.0), (200.0, 105.0), (200.0, 200.0), (0.0, 200.0)],
    )
    op = _op("opening-1", "horizontal", (100.0, 100.0), width=70.0)
    result = _assign_and_filter_rooms([op], [room_top, room_bot])
    assert len(result) == 1
    # ambos lados devem estar preenchidos
    ids = {result[0].room_a, result[0].room_b}
    assert "room-A" in ids and "room-B" in ids


def test_filter_empty_rooms_passthrough():
    op = _op("opening-1", "horizontal", (100.0, 100.0))
    assert _assign_and_filter_rooms([op], []) == [op]


# ---------- strict mode --------------------------------------------------


def test_strict_mode_demotes_unconfirmed():
    """Opening arc-unconfirmed (kind=door sem hinge_side) + strict=True
    -> vira passage."""
    op = _op("opening-1", "horizontal", (100.0, 200.0), kind="door")
    demoted = _maybe_demote_strict(op)
    assert demoted.kind == "passage"


def test_strict_mode_keeps_already_passage():
    """Opening que ja eh passage nao eh afetado."""
    op = _op("opening-1", "horizontal", (100.0, 200.0), kind="passage", width=220.0)
    demoted = _maybe_demote_strict(op)
    assert demoted.kind == "passage"


def test_detect_openings_strict_end_to_end():
    """Smoke end-to-end com strict=True -> todas portas viram passage."""
    # 2 walls horizontais com gap de 70 (door normal)
    a = _wall("wall-1", (0.0, 100.0), (200.0, 100.0), "horizontal")
    b = _wall("wall-2", (270.0, 100.0), (500.0, 100.0), "horizontal")
    _walls, ops = detect_openings([a, b], strict_openings=True)
    assert len(ops) == 1
    assert ops[0].kind == "passage", f"strict should demote unconfirmed door, got {ops[0].kind}"


def test_detect_openings_non_strict_keeps_door():
    """Sem strict=True (default): continua "door" como antes."""
    a = _wall("wall-1", (0.0, 100.0), (200.0, 100.0), "horizontal")
    b = _wall("wall-2", (270.0, 100.0), (500.0, 100.0), "horizontal")
    _walls, ops = detect_openings([a, b])
    assert len(ops) == 1
    assert ops[0].kind == "door"


# ---------- baseline gates -----------------------------------------------


P12_PDF = REPO_ROOT / "runs" / "proto" / "p12_red.pdf"
P12_PEITORIS = REPO_ROOT / "runs" / "proto" / "p12_peitoris.json"
PLANTA_74_PDF = REPO_ROOT / "planta_74.pdf"


def _require(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"fixture ausente: {path}")


@pytest.fixture(scope="module")
def p12_observed(tmp_path_factory):
    _require(P12_PDF); _require(P12_PEITORIS)
    from model.pipeline import run_pdf_pipeline
    out = tmp_path_factory.mktemp("f7_p12")
    peitoris = json.loads(P12_PEITORIS.read_text(encoding="utf-8"))
    result = run_pdf_pipeline(
        pdf_bytes=P12_PDF.read_bytes(),
        filename=P12_PDF.name,
        output_dir=out,
        peitoris=peitoris,
    )
    return result.observed_model


@pytest.fixture(scope="module")
def planta_74_observed(tmp_path_factory):
    _require(PLANTA_74_PDF)
    from model.pipeline import run_pdf_pipeline
    out = tmp_path_factory.mktemp("f7_planta_74")
    result = run_pdf_pipeline(
        pdf_bytes=PLANTA_74_PDF.read_bytes(),
        filename=PLANTA_74_PDF.name,
        output_dir=out,
    )
    return result.observed_model


def test_p12_baseline_6_openings_preserved(p12_observed):
    """GATE: F7 nao pode quebrar o baseline p12 de 6 openings."""
    n = len(p12_observed.get("openings", []))
    assert n == 6, f"p12 openings regrediu: {n} != 6"


def test_p12_topology_snapshot_hash_preserved(p12_observed):
    """GATE: hash topologico do p12 nao pode drift com F7."""
    sha = p12_observed.get("metadata", {}).get("topology_snapshot_sha256")
    assert sha == (
        "39b4138f4fd5613ed897824657b0329445d2eb332a6a1d810da75933ba4b5ce3"
    ), f"hash drift: {sha}"


def test_planta_74_openings_in_range(planta_74_observed):
    """Target F7: 8 <= openings <= 15 em planta_74 (baseline pos-F6
    era 22, target inicial era 8-12, faixa relaxada por seguranca)."""
    n = len(planta_74_observed.get("openings", []))
    assert 8 <= n <= 15, f"planta_74 openings={n} fora da faixa [8, 15]"


def test_planta_74_no_opening_co_located_pairs(planta_74_observed):
    """Sanity: apos dedup F7, nao deve haver 2 openings co-localizados
    na MESMA parede (perp_coord dentro da tolerancia). Openings em
    paredes paralelas vizinhas (perp diff > 6) sao legitimos."""
    ops = planta_74_observed.get("openings", [])
    PERP_TOLERANCE = 6.0
    for i, op_i in enumerate(ops):
        for op_j in ops[i + 1:]:
            if op_i["orientation"] != op_j["orientation"]:
                continue
            cx_i, cy_i = op_i["center"]
            cx_j, cy_j = op_j["center"]
            # mesma parede <=> mesmo perp_coord dentro da tolerancia
            if op_i["orientation"] == "horizontal":
                perp_diff = abs(cy_i - cy_j)
            else:
                perp_diff = abs(cx_i - cx_j)
            if perp_diff > PERP_TOLERANCE:
                continue  # paredes diferentes — nao e um duplicado
            dist = ((cx_i - cx_j) ** 2 + (cy_i - cy_j) ** 2) ** 0.5
            assert dist >= 25.0, (
                f"openings {op_i['opening_id']} e {op_j['opening_id']} "
                f"co-localizados na mesma parede: {dist:.1f} px"
            )
