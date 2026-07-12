"""curation_review — laço autônomo de revisão de curadoria. Hermético: paths em
tmp, clock injetado (now/today), scorer INJETADO (nunca toca o GPT/:8899, git ou a
fila de produção). Cobre também o fix do bug do variant_id recursivo no feeder."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import curation_review as cr
from tools import feeder as nf
from tools.claude_bridge.noc_dispatcher import is_appearance_evidence_variant
from tools.gpt_docker_visual_score import VisualScore
from tools.jsonl_io import append_jsonl, read_jsonl

NOW = 1_783_200_000.0
TODAY = "20260712"

# variant_ids REAIS da fila de produção (2026-07-12): 4 lixo recursivo + os reais.
GARBAGE_IDS = [
    "planta_74__noc-nf-20260707-visdrain-planta_74__baseline__dark_walnut__l0__warm_compact__L0",
    "planta_74__noc-nf-20260708-sweep-planta_74__warm_compact__L0",
]
REAL_IDS = [
    "planta_74__baseline__warm_compact__L0",
    "planta_74__baseline__black_wood_gold__L0",
]


def _rec(vid, *, verdict="CANDIDATE", iso="x/iso.png", sha="sha-x",
         renderer="su-free", human=None, plant="planta_74") -> dict:
    r = {
        "schema": "judged_variant/1.0.0",
        "variant_id": vid,
        "plant": plant,
        "verdict": verdict,
        "render_refs": {"iso": iso, "sha256": sha, "renderer": renderer},
        "machine_score": {"value": 0.6, "label": "machine_provisional"},
        "human_verdict": human,
    }
    return r


def _score(nota, *, caminho="faça X depois Y", viewed=True) -> VisualScore:
    return VisualScore(url="https://raw/x.png", nota=nota, factivel_10="sim",
                       porque="luz estourada", caminho_pro_10=caminho,
                       image_viewed=viewed, raw_answer="...")


# ── o marcador de evidência sintética (fonte única) ──────────────────────────


def test_appearance_evidence_marker_flags_recursive_ids_not_real():
    for gid in GARBAGE_IDS:
        assert is_appearance_evidence_variant({"variant_id": gid}) is True
    for rid in REAL_IDS:
        assert is_appearance_evidence_variant({"variant_id": rid}) is False
    # também pega pelo renderer, mesmo sem '__noc-' no id
    assert is_appearance_evidence_variant(
        {"variant_id": "planta_74__x__y__L0",
         "render_refs": {"renderer": "noc-evidence"}}) is True


# ── fix do bug: feeder não re-enfileira evidência sintética (red→green) ───────


def test_feeder_pending_vision_excludes_synthetic_recursive_ids(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    rows = [_rec(g, verdict="PENDING_VISION", iso="", renderer="noc-evidence")
            for g in GARBAGE_IDS]
    rows.append(_rec(REAL_IDS[0], verdict="PENDING_VISION"))  # variante real drenável
    rows.append(_rec(REAL_IDS[1], verdict="CANDIDATE"))       # não é PENDING_VISION
    append_jsonl(corpus, rows)

    pend = nf.pending_vision_variants(corpus)
    assert pend == [REAL_IDS[0]]          # só a variante REAL PENDING_VISION
    for g in GARBAGE_IDS:
        assert g not in pend              # o lixo recursivo nunca mais é drenado


# ── select_items ─────────────────────────────────────────────────────────────


def test_select_skips_synthetic_no_render_human_decided():
    records = [
        _rec(REAL_IDS[0]),                                   # ✓ elegível
        _rec(GARBAGE_IDS[0], iso="", renderer="noc-evidence"),  # ✗ sintético
        _rec("planta_74__baseline__dark_walnut__L1", iso=""),   # ✗ sem render
        _rec("planta_74__baseline__dark_walnut__L2",
             human={"verdict": "IMPROVED"}),                 # ✓ julgado mas SEM review
    ]
    got = [r["variant_id"] for r in cr.select_items(records, reviews={})]
    # política 2026-07-12: humano-julgado sem review anterior TAMBÉM é notado
    # (sem sha de referência não há como saber que ele viu ESTE render)
    assert got == [REAL_IDS[0], "planta_74__baseline__dark_walnut__L2"]


def test_select_skips_already_reviewed_same_render_sha():
    rec = _rec(REAL_IDS[0], sha="sha-abc")
    reviews = {REAL_IDS[0]: {"render_sha": "sha-abc"}}
    assert cr.select_items([rec], reviews=reviews) == []      # mesmo render → skip
    reviews2 = {REAL_IDS[0]: {"render_sha": "sha-OLD"}}
    assert len(cr.select_items([rec], reviews=reviews2)) == 1  # render mudou → revisa


# ── decide_followup ──────────────────────────────────────────────────────────


def test_decide_done_when_nota_high():
    route, _ = cr.decide_followup({}, _score(8))
    assert route == cr.FOLLOWUP_DONE


def test_decide_fix_when_low_with_path():
    route, _ = cr.decide_followup({}, _score(4, caminho="troque a luz"))
    assert route == cr.FOLLOWUP_FIX


def test_decide_felipe_when_low_but_no_path():
    route, _ = cr.decide_followup({}, _score(4, caminho="   "))
    assert route == cr.FOLLOWUP_FELIPE


def test_decide_felipe_when_no_score_or_blind():
    assert cr.decide_followup({}, None)[0] == cr.FOLLOWUP_FELIPE
    assert cr.decide_followup({}, _score(5, viewed=False))[0] == cr.FOLLOWUP_FELIPE


# ── build_fix_task ───────────────────────────────────────────────────────────


def test_build_fix_task_schema():
    item = _rec(REAL_IDS[0])
    t = cr.build_fix_task(item, _score(4, caminho="mais luz quente"), TODAY)
    assert t["id"] == f"CR-{TODAY}-fix-{REAL_IDS[0]}"
    assert t["kind"] == "curation_fix" and t["safe"] is True
    assert t["variant_id"] == REAL_IDS[0] and t["gpt_nota"] == 4
    assert "mais luz quente" in t["gpt_caminho"]
    assert t["enqueued_by"] == "curation_review"


# ── run_batch (o laço) ───────────────────────────────────────────────────────


@pytest.fixture
def env(tmp_path):
    corpus = tmp_path / "sweep" / "corpus.jsonl"
    corpus.parent.mkdir(parents=True)
    queue = tmp_path / "noc" / "queue.jsonl"
    queue.parent.mkdir(parents=True)
    return {"corpus": corpus, "out": corpus.parent, "queue": queue}


def _run(env, scorer, **kw):
    return cr.run_batch(corpus_path=env["corpus"], out_dir=env["out"], scorer=scorer,
                        now=NOW, today=TODAY, queue_path=env["queue"], **kw)


def test_dry_run_writes_nothing_and_skips_gpt(env):
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0])])
    calls = []

    def scorer(item):
        calls.append(item["variant_id"])
        return _score(5)

    rep = _run(env, scorer, apply=False)
    assert rep["applied"] is False
    assert rep["would_review"] == [REAL_IDS[0]]
    assert calls == []                                   # GPT nunca chamado
    assert not (env["out"] / cr.STATUS_FILE).exists()
    assert not (env["out"] / cr.REVIEW_FILE).exists()


def test_apply_writes_live_status_review_and_enqueues_fix(env):
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0], sha="sha-1")])
    rep = _run(env, lambda it: _score(4, caminho="mais luz"), apply=True, enqueue_fix=True)

    assert rep["n_reviewed"] == 1
    # status: em_analise (vivo durante a chamada) → revisado → corrigindo
    statuses = [r["status"] for r in read_jsonl(env["out"] / cr.STATUS_FILE)]
    assert statuses == [cr.ST_ANALYZING, cr.ST_REVIEWED, cr.ST_FIXING]
    # review gravada com a nota + render_sha (chave de frescor)
    rev = read_jsonl(env["out"] / cr.REVIEW_FILE)
    assert rev[0]["nota"] == 4 and rev[0]["render_sha"] == "sha-1"
    # fix enfileirada
    q = read_jsonl(env["queue"])
    assert [t["id"] for t in q] == [f"CR-{TODAY}-fix-{REAL_IDS[0]}"]
    assert rep["enqueued_fixes"] == [f"CR-{TODAY}-fix-{REAL_IDS[0]}"]


def test_apply_high_nota_marks_done_no_fix(env):
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0])])
    rep = _run(env, lambda it: _score(9), apply=True, enqueue_fix=True)
    assert rep["results"][0]["card"] == cr.ST_DONE
    assert rep["enqueued_fixes"] == []
    assert not env["queue"].exists() or read_jsonl(env["queue"]) == []


def test_apply_oracle_offline_degrades_honestly(env):
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0])])
    rep = _run(env, lambda it: None, apply=True, enqueue_fix=True)      # oráculo mudo
    statuses = [r["status"] for r in read_jsonl(env["out"] / cr.STATUS_FILE)]
    assert statuses == [cr.ST_ANALYZING, cr.ST_ORACLE_OFFLINE]
    assert not (env["out"] / cr.REVIEW_FILE).exists()                   # nada fabricado
    assert rep["enqueued_fixes"] == []


def test_fix_dedup_against_known_ids(env):
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0])])
    fid = f"CR-{TODAY}-fix-{REAL_IDS[0]}"
    rep = _run(env, lambda it: _score(3, caminho="x"), apply=True, enqueue_fix=True,
               known_ids=frozenset({fid}))
    assert rep["enqueued_fixes"] == []                                  # já conhecido
    assert not env["queue"].exists() or read_jsonl(env["queue"]) == []


def test_idempotent_second_pass_skips_reviewed(env):
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0], sha="sha-1")])
    _run(env, lambda it: _score(8), apply=True)
    rep2 = _run(env, lambda it: _score(8), apply=True)                  # 2ª passada
    assert rep2["n_selected"] == 0                                      # mesmo render → nada


def test_run_log_written_per_apply_pass(env):
    """Visibilidade: cada passada aplicada grava 1 linha em curation_runs.jsonl
    (t/trigger/n_reviewed/reviewed[]) — inclusive a passada VAZIA (rodou às HH:MM
    é o ponto). Dry-run NÃO loga."""
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0], sha="sha-1")])
    _run(env, lambda it: _score(4, caminho="x"), apply=False)           # dry-run
    assert not (env["out"] / cr.RUNS_FILE).exists()
    _run(env, lambda it: _score(4, caminho="x"), apply=True)            # revisa 1
    _run(env, lambda it: _score(4, caminho="x"), apply=True)            # vazia
    runs = read_jsonl(env["out"] / cr.RUNS_FILE)
    assert len(runs) == 2
    assert runs[0]["n_reviewed"] == 1 and runs[0]["trigger"] == "auto"
    assert runs[0]["reviewed"][0]["variant_id"] == REAL_IDS[0]
    assert runs[0]["reviewed"][0]["nota"] == 4
    assert runs[1]["n_reviewed"] == 0 and runs[1]["n_selected"] == 0    # vazia também loga


def test_human_decided_rereviews_when_render_changed(env):
    """Gosto do Felipe é respeitado (nunca re-pedimos), mas a NOTA acompanha o
    RENDER: variante julgada por ele + render novo (sha mudou) → re-seleciona;
    mesmo render → pula."""
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0], sha="sha-old")])
    _run(env, lambda it: _score(2), apply=True)                     # nota no render velho
    append_jsonl(env["out"] / "human_verdicts.jsonl",
                 [{"variant_id": REAL_IDS[0],
                   "human_verdict": "WORSE", "t": "2026-07-12T18:00:00Z"}])
    rep = _run(env, lambda it: _score(2), apply=False)              # mesmo render
    assert rep["n_selected"] == 0                                   # humano falou → pula
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0], sha="sha-NEW")])  # render mudou (shell)
    rep2 = _run(env, lambda it: _score(5), apply=False)
    assert rep2["n_selected"] == 1                                  # nota re-acompanha


def test_human_decided_without_prior_review_still_gets_scored(env):
    """Gap real: variante julgada pelo humano SEM review anterior nunca ganhava
    nota (prev is None pulava). Sem sha de referência não dá pra saber que o
    humano viu ESTE render — a nota entra; na passada seguinte (mesmo sha) pula."""
    append_jsonl(env["corpus"], [_rec(REAL_IDS[0], sha="sha-1")])
    append_jsonl(env["out"] / "human_verdicts.jsonl",
                 [{"variant_id": REAL_IDS[0], "human_verdict": "WORSE",
                   "t": "2026-07-12T18:00:00Z"}])
    rep = _run(env, lambda it: _score(3), apply=True)
    assert rep["n_reviewed"] == 1                            # notou mesmo com WORSE
    rep2 = _run(env, lambda it: _score(3), apply=False)
    assert rep2["n_selected"] == 0                           # mesmo render → pula
