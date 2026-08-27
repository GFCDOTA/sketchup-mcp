"""FASE 2 — normalizador dos cinco formatos de gate deste repo.

As fixtures abaixo são as formas REAIS devolvidas hoje (copiadas dos `return`
dos módulos, não inventadas). Se um gate mudar de forma, o teste que casa com
ele quebra — que é o ponto: a UI não pode descobrir isso desenhando um nó verde
sobre um FAIL.
"""
from __future__ import annotations

import itertools

import pytest

from core import observability as obs
from core.observability.gates import (
    FAIL,
    INCOMPLETE,
    PASS,
    SKIPPED,
    UNKNOWN,
    WARN,
    emit_all,
    normalize,
    normalize_one,
    normalize_status,
    worst,
)
from core.observability.sink import MemorySink, set_sink

# ---------------------------------------------------------------------------
# formas reais
# ---------------------------------------------------------------------------

RUN_ALL = {                                   # tools/run_deterministic_gates.run_all
    "overall": "FAIL",
    "gates": {
        "opening_host": {"detector": "opening_host_consistency", "tol_pt": 6.0,
                         "width_factor": 0.5, "n_openings": 12, "n_fail": 2,
                         "overall": "FAIL"},
        "wall_overlap": {"overall": "PASS", "n_fail": 0},
        "wall_presence": {"verdict": "SKIPPED_NO_SIDECAR",
                          "sidecar": "model.png.proj.json",
                          "reason": "projection sidecar missing; rebuild or "
                                    "promote_canonical to emit it"},
    },
}

CIRCULATION = {                               # tools/circulation_gate
    "result": "FAIL",
    "room": "r004",
    "checks": {
        "atras_das_cadeiras": {
            "result": "FAIL", "min_m": 0.60,
            "cadeiras": [{"cadeira": [120.0, 80.0], "livre_atras_m": 0.54,
                          "atras_ok": False, "puxada_ok": True},
                         {"cadeira": [160.0, 80.0], "livre_atras_m": 0.71,
                          "atras_ok": True, "puxada_ok": True}],
        },
        "cadeira_puxada": {"result": "PASS", "recuo_m": 0.30},
    },
}

OVERLAP = {                                   # tools/furniture_overlap_gate
    "result": "WARN", "room": "r002", "room_name": "COZINHA", "n_modules": 9,
    "fails": [],
    "warns": ["Bancada × Geladeira: 180 cm² sobrepostos (4% do menor)"],
}

SEMANTIC = {                                  # tools/semantic_geometry_contract_gate
    "overall": "FAIL", "n_parts": 41, "n_fail": 3,
    "findings": [{"detail": "parte sem geometry_intent", "severity": "FAIL"},
                 {"detail": "interaction_policy ausente", "severity": "FAIL"},
                 {"detail": "bbox degenerada", "severity": "FAIL"}],
}

OPENING_HOST = RUN_ALL["gates"]["opening_host"]


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    ("PASS", PASS), ("pass", PASS), ("OK", PASS),
    ("FAIL", FAIL), ("failed", FAIL),
    ("WARN", WARN), ("WARNING", WARN),
    ("INCOMPLETE", INCOMPLETE),
    ("SKIPPED_NO_SIDECAR", SKIPPED), ("SKIPPED_OFFLINE", SKIPPED),
])
def test_status_aliases_normalize(raw, expected):
    assert normalize_status(raw)[0] == expected


def test_missing_verdict_is_unknown_never_pass():
    """Gate que mudou de formato tem que acender a luz, não sumir do radar."""
    status, reason = normalize_status(None)
    assert status is UNKNOWN
    assert reason and "veredito" in reason


def test_unrecognized_verdict_is_unknown_and_keeps_the_raw_value():
    status, reason = normalize_status("QUASE_PASSOU")
    assert status is UNKNOWN
    assert "QUASE_PASSOU" in reason


def test_skipped_is_not_pass():
    """LL-035: 'não conseguiu rodar' != 'rodou e aprovou'."""
    assert normalize_status("SKIPPED_NO_SIDECAR")[0] != PASS


def test_worst_ranks_unknown_above_warn():
    assert worst([PASS, WARN, UNKNOWN]) is UNKNOWN
    assert worst([PASS, WARN]) is WARN
    assert worst([FAIL, UNKNOWN]) is FAIL
    assert worst([PASS, SKIPPED]) is SKIPPED
    assert worst([]) is UNKNOWN


# ---------------------------------------------------------------------------
# cada formato real
# ---------------------------------------------------------------------------


def test_run_all_flattens_into_parent_plus_children():
    gates = normalize("run_deterministic_gates", RUN_ALL)
    names = [g.name for g in gates]
    assert names[0] == "run_deterministic_gates"
    assert set(names[1:]) == {"opening_host", "wall_overlap", "wall_presence"}
    assert gates[0].status is FAIL


def test_run_all_children_keep_their_own_verdicts():
    by_name = {g.name: g for g in normalize("run_deterministic_gates", RUN_ALL)}
    assert by_name["opening_host"].status is FAIL
    assert by_name["wall_overlap"].status is PASS
    assert by_name["wall_presence"].status is SKIPPED
    assert "sidecar missing" in by_name["wall_presence"].reason


def test_circulation_yields_the_measurement_card():
    """É este objeto que vira '0.54 m medido / 0.60 m exigido — FAIL' na UI."""
    g = normalize_one("circulation", CIRCULATION)
    assert g.status is FAIL
    assert g.room == "r004"
    atras = next(m for m in g.measurements if m.metric == "atras_das_cadeiras")
    assert atras.required == 0.60
    assert atras.measured == 0.54          # pior caso, não o primeiro nem a média
    assert atras.unit == "m"
    assert atras.status is FAIL
    assert atras.slack == pytest.approx(-0.06)


def test_circulation_passing_check_has_required_without_measured():
    """`cadeira_puxada` expõe o limite mas não o valor medido. `None`, nunca 0.0."""
    g = normalize_one("circulation", CIRCULATION)
    puxada = next(m for m in g.measurements if m.metric == "cadeira_puxada")
    assert puxada.required == 0.30
    assert puxada.measured is None
    assert puxada.slack is None


def test_overlap_warn_is_preserved_not_flattened_to_pass():
    g = normalize_one("furniture_overlap", OVERLAP)
    assert g.status is WARN
    assert g.counts["n_warns"] == 1
    assert g.counts["n_fails"] == 0
    assert g.counts["n_modules"] == 9
    assert "Bancada × Geladeira" in g.findings[0]


def test_semantic_contract_counts_findings():
    g = normalize_one("semantic_contract", SEMANTIC)
    assert g.status is FAIL
    assert g.counts["n_parts"] == 41
    assert g.counts["n_fail"] == 3
    assert len(g.findings) == 3
    assert "geometry_intent" in g.findings[0]


def test_opening_host_counts_are_carried():
    g = normalize_one("opening_host", OPENING_HOST)
    assert g.status is FAIL
    assert g.counts["n_openings"] == 12
    assert g.counts["n_fail"] == 2


def test_non_dict_result_is_unknown_not_a_crash():
    g = normalize_one("gate_estranho", "PASS")
    assert g.status is UNKNOWN
    assert "não é dict" in g.reason


def test_verdict_derived_from_subchecks_when_parent_omits_it():
    g = normalize_one("sem_veredito", {"checks": {
        "a": {"result": "PASS"}, "b": {"result": "FAIL"}}})
    assert g.status is FAIL
    assert "derivado" in g.reason


# ---------------------------------------------------------------------------
# payload do evento continua leve
# ---------------------------------------------------------------------------


def test_gate_meta_carries_numbers_not_the_finding_dump():
    meta = normalize_one("semantic_contract", SEMANTIC).to_meta()
    assert meta["verdict"] == FAIL
    assert meta["counts"]["n_parts"] == 41
    assert "findings" not in meta            # texto fica fora do evento
    assert len(str(meta)) < 800


# ---------------------------------------------------------------------------
# emissão
# ---------------------------------------------------------------------------


@pytest.fixture
def sink():
    obs.reset_for_tests()
    mem = MemorySink()
    ticks = itertools.count(1_800_000_000.0, 0.001)
    previous = obs.configure(sink=mem, clock=lambda: next(ticks))
    try:
        yield mem
    finally:
        set_sink(previous)
        obs.reset_for_tests()


def test_emit_all_maps_each_status_to_the_right_event(sink):
    with obs.run(run_id="run_gates"):
        emit_all("run_deterministic_gates", RUN_ALL)

    by_component = {e.component: e.name for e in sink.events
                    if e.name.startswith("gate.")}
    assert by_component["gate.opening_host"] == "gate.failed"
    assert by_component["gate.wall_overlap"] == "gate.passed"
    assert by_component["gate.wall_presence"] == "gate.skipped"


def test_unknown_gate_emits_incomplete_not_passed(sink):
    with obs.run(run_id="run_unknown"):
        emit_all("gate_novo", {"resultado_em_pt": "aprovado"})
    names = [e.name for e in sink.events if e.name.startswith("gate.")]
    assert names == ["gate.incomplete"]


def test_measurements_become_their_own_events(sink):
    with obs.run(run_id="run_medidas"):
        emit_all("circulation", CIRCULATION)

    measures = [e for e in sink.events if e.name == "gate.measurement"]
    assert len(measures) == 2
    atras = next(e for e in measures if e.meta["metric"] == "atras_das_cadeiras")
    assert atras.meta["measured"] == 0.54
    assert atras.meta["required"] == 0.60
    assert atras.meta["unit"] == "m"


def test_emit_all_is_noop_when_instrumentation_is_off():
    obs.reset_for_tests()
    previous = set_sink(None)
    try:
        gates = emit_all("circulation", CIRCULATION)
        assert len(gates) == 1            # normaliza mesmo desligado
    finally:
        set_sink(previous)


# ---------------------------------------------------------------------------
# contrato contra o gate REAL (não fixture) — a prova da Fase 2
# ---------------------------------------------------------------------------


def test_real_run_all_on_the_quadrado_fixture_normalizes():
    """Roda o `run_all` de verdade sobre a micro-fixture canônica do CI.

    É o teste que impede a normalização de divergir da saída real: se
    `run_deterministic_gates` mudar de formato, isto quebra antes da UI.
    """
    from tools.run_deterministic_gates import run_all

    raw = run_all(fixture="quadrado")
    gates = normalize("run_deterministic_gates", raw)

    assert len(gates) >= 2, "esperado o agregado + ao menos um sub-gate"
    assert gates[0].name == "run_deterministic_gates"
    assert gates[0].status in (PASS, WARN, FAIL, INCOMPLETE)
    assert all(g.status is not UNKNOWN for g in gates), (
        "algum gate real devolveu um veredito que o normalizador não reconhece: "
        f"{[(g.name, g.raw_verdict) for g in gates if g.status is UNKNOWN]}")
    assert {g.name for g in gates} >= {"opening_host", "wall_overlap"}
