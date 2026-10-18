"""commit 8 — o WRITE-BACK do gosto no RAG (o "buraco central"), camada PURA.

Deterministico e HERMETICO (roda SEMPRE no CI, zero infra): o record carimba o
corpus_version atual no write; materializar um verdict sob
references/felipe/verdicts/*.json MUDA o corpus_version e faz o reindex chunkar +
marcar embedded=0; positive/negative_patterns vem SO do humano (nunca de
design_patterns_observed da maquina); idempotencia por id+conteudo; vocabulario
estrito; drain casa com a galeria e ignora o scratch.

O recall REAL (materialize -> embed -> retrieve traz o conteudo aprendido) vive
em test_taste_writeback_recall.py (integracao, skip-guarded — commit 9).
"""
from __future__ import annotations

import inspect
import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools import rag_freshness as rf
from tools import taste_writeback as tw

ROOT = Path(__file__).resolve().parents[1]
WB_SCHEMA = json.loads(
    (ROOT / "schemas/rag_writeback_record.schema.json").read_text("utf-8"))

T0 = "2026-07-07T10:00:00Z"
T1 = "2026-07-07T11:00:00Z"


# --------------------------------------------------------------------------- helpers
def _write(root: Path, rel: str, content: str, mtime: float = 1_700_000_000) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def _base_source(root: Path) -> None:
    """Uma fonte base pra o corpus_version nascer != vazio (token de cozinha)."""
    _write(root, "references/tokens/hot_tower_niche.json", json.dumps({
        "name": "hot_tower_niche",
        "rule": "coluna piso-teto agrupando forno, micro-ondas e airfryer em "
                "nichos quentes na altura ergonomica.",
        "anti_pattern": "forno embaixo do cooktop.",
        "applies_to_kinds": ["kc_niche_wood"]}))


def _corpus_rec(vid: str = "planta_74__kc_v1", **over) -> dict:
    """Registro de galeria (variant_sweep-like) COM um campo de MAQUINA
    (design_patterns_observed) — o teste prova que ele NUNCA vira pattern."""
    rec = {
        "variant_id": vid, "run_id": "run1", "plant": "planta_74",
        "room_id": "r004", "room_type": "KITCHEN",
        "params": {"style": "black_wood_gold", "theme": "dark_walnut"},
        "render_refs": {"iso": f"{vid}/iso.png", "sha256": "ab" * 32,
                        "renderer": "su-free"},
        "created_at": "2026-07-01T12:00:00Z",
        # sinal da MAQUINA — proibido de virar positive/negative_pattern:
        "design_patterns_observed": ["machine_saw_tower", "machine_saw_backsplash"],
        "human_verdict": None,
    }
    rec.update(over)
    return rec


def _curadoria(vid: str = "planta_74__kc_v1", verdict: str = "IMPROVED",
               liked=None, tags=None, note: str = "", batch: str = "b1",
               t: str = T0) -> dict:
    return {"variant_id": vid, "human_verdict": verdict, "liked": liked,
            "tags": tags or [], "note": note, "batch_id": batch, "t": t}


@pytest.fixture
def con(tmp_path):
    c = rf.connect(tmp_path / "rag_freshness.db")
    yield c
    c.close()


# =========================================================================== PURO
def test_writeback_stamps_current_corpus_version_at_write(tmp_path, con):
    root = tmp_path / "repo"
    _base_source(root)
    rf.reindex(con, root=root, now_iso=T0)
    v0 = rf.current_corpus_version(con)
    assert v0 and len(v0) == 64
    out = tw.materialize(_curadoria(note="torre quente perfeita"), _corpus_rec(),
                         con, verdicts_dir=tmp_path / "vout")
    rec = json.loads(out.read_text("utf-8"))
    assert rec["corpus_version"] == v0        # carimbado com o corpus ATUAL do write


def test_writeback_record_validates_against_schema(tmp_path, con):
    Draft202012Validator.check_schema(WB_SCHEMA)
    out = tw.materialize(
        _curadoria(liked=True, tags=["madeira quente"], note="gostei da torre"),
        _corpus_rec(), con, verdicts_dir=tmp_path / "vout")
    rec = json.loads(out.read_text("utf-8"))
    errors = list(Draft202012Validator(WB_SCHEMA).iter_errors(rec))
    assert not errors, "; ".join(e.message for e in errors)
    # os campos da galeria foram puxados (nao ficaram vazios):
    assert rec["room_type"] == "KITCHEN" and rec["style_profile"] == "black_wood_gold"
    assert rec["image_path"] == "planta_74__kc_v1/iso.png"


def test_materialized_verdict_changes_corpus_version_and_reindex_marks_embedded_zero(
        tmp_path, con):
    root = tmp_path / "repo"
    _base_source(root)
    rf.reindex(con, root=root, now_iso=T0)
    v0 = rf.current_corpus_version(con)
    # materializa DENTRO do root (source registrado) -> vira fonte do corpus
    vdir = root / "references" / "felipe" / "verdicts"
    tw.materialize(_curadoria(liked=True, tags=["torre quente marcada"],
                              note="marcenaria planejada da cozinha impecavel"),
                   _corpus_rec(), con, verdicts_dir=vdir)
    # 1) o corpus_version MUDA (o veredito e' uma fonte nova)
    v1 = rf.compute_corpus_version(rf.discover_sources(root))
    assert v1 != v0, "materializar um verdict deveria mudar o corpus_version"
    # 2) o reindex CHUNKA o verdict e marca embedded=0 (pendente pro backend embed)
    rep = rf.reindex(con, root=root, now_iso=T1)
    assert rep["corpus_version"] == v1
    assert rep["chunks_reindexed"] >= 1
    pending = con.execute(
        "SELECT COUNT(*) FROM chunk WHERE document_id LIKE ? AND embedded=0 "
        "AND is_active=1", ("references/felipe/verdicts/%",)).fetchone()[0]
    assert pending >= 1, "o chunk do verdict deveria estar embedded=0"


def test_positive_negative_patterns_only_from_human_never_machine(tmp_path, con):
    rec = _corpus_rec()                         # carrega design_patterns_observed (maquina)
    machine = set(rec["design_patterns_observed"])
    # liked=True -> tags+comentario do humano viram POSITIVOS
    out = tw.materialize(
        _curadoria(liked=True, tags=["gostei da luz", "madeira nogueira"],
                   note="a torre quente ficou otima"),
        rec, con, verdicts_dir=tmp_path / "vout")
    r = json.loads(out.read_text("utf-8"))
    assert "gostei da luz" in r["positive_patterns"]
    assert "madeira nogueira" in r["positive_patterns"]
    assert "a torre quente ficou otima" in r["positive_patterns"]
    assert r["negative_patterns"] == []
    # nenhum sinal da MAQUINA vazou pros patterns
    assert machine.isdisjoint(set(r["positive_patterns"]) | set(r["negative_patterns"]))

    # liked=False -> os MESMOS insumos humanos viram NEGATIVOS (polaridade=liked)
    out2 = tw.materialize(
        _curadoria(vid="planta_74__kc_v2", liked=False, tags=["escuro demais"],
                   note="coluna some no preto"),
        _corpus_rec("planta_74__kc_v2"), con, verdicts_dir=tmp_path / "vout")
    r2 = json.loads(out2.read_text("utf-8"))
    assert r2["negative_patterns"] == ["escuro demais", "coluna some no preto"]
    assert r2["positive_patterns"] == []

    # liked=None (nao sinalizado) -> nao fabrica polaridade; tags seguem em `tags`
    out3 = tw.materialize(
        _curadoria(vid="planta_74__kc_v3", liked=None, tags=["talvez"], note="hmm"),
        _corpus_rec("planta_74__kc_v3"), con, verdicts_dir=tmp_path / "vout")
    r3 = json.loads(out3.read_text("utf-8"))
    assert r3["positive_patterns"] == [] and r3["negative_patterns"] == []
    assert r3["tags"] == ["talvez"] and r3["felipe_comment"] == "hmm"


def test_materialize_is_idempotent_by_id_and_content(tmp_path, con):
    vdir = tmp_path / "vout"
    cur = _curadoria(liked=True, tags=["x"], note="y")
    a = tw.materialize(cur, _corpus_rec(), con, verdicts_dir=vdir)
    bytes_a = a.read_bytes()
    mtime_a = a.stat().st_mtime_ns
    b = tw.materialize(cur, _corpus_rec(), con, verdicts_dir=vdir)
    assert a == b                               # mesmo id -> mesmo arquivo
    assert b.read_bytes() == bytes_a            # conteudo deterministico
    assert b.stat().st_mtime_ns == mtime_a      # nao reescreveu bytes iguais (mtime estavel)


def test_machine_vocabulary_is_rejected(tmp_path, con):
    # so verdict CURADO (IMPROVED|SAME|WORSE) materializa; vocabulario da maquina nao
    with pytest.raises(ValueError):
        tw.materialize(_curadoria(verdict="CANDIDATE"), _corpus_rec(), con,
                       verdicts_dir=tmp_path / "vout")
    with pytest.raises(ValueError):
        tw.materialize(_curadoria(verdict=None), _corpus_rec(), con,
                       verdicts_dir=tmp_path / "vout")


def test_drain_matches_gallery_and_ignores_scratch(tmp_path, con):
    # corpus (galeria) com 2 variantes
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        json.dumps(_corpus_rec("planta_74__A")) + "\n"
        + json.dumps(_corpus_rec("planta_74__B")) + "\n", encoding="utf-8")
    # human_verdicts.jsonl (o LOTE que o BFF grava) — scratch com ruido:
    hv = tmp_path / "human_verdicts.jsonl"
    hv.write_text("\n".join(json.dumps(r) for r in [
        _curadoria("planta_74__A", "SAME", note="1a impressao", t="2026-07-04T10:00Z"),
        _curadoria("planta_74__A", "IMPROVED", note="ULTIMO clique vence",
                   t="2026-07-04T10:05Z"),          # last-wins por variant_id
        {"variant_id": "planta_74__B", "human_verdict": "CANDIDATE"},  # MAQUINA -> ignora
        _curadoria("fantasma", "WORSE"),             # sem galeria -> ignora
    ]) + "\n", encoding="utf-8")
    vdir = tmp_path / "vout"
    n = tw.drain_new_verdicts(corpus, con, verdicts_dir=vdir)
    assert n == 1                                    # so o A curado (humano) materializou
    got = json.loads((vdir / "planta_74__A.json").read_text("utf-8"))
    assert got["human_verdict"] == "IMPROVED"        # last-wins
    assert not (vdir / "planta_74__B.json").exists()
    assert not (vdir / "fantasma.json").exists()
    # idempotente: 2a passada nao reconta
    assert tw.drain_new_verdicts(corpus, con, verdicts_dir=vdir) == 0


def test_taste_writeback_is_deterministic_no_clock():
    # inspeciona os CORPOS das funcoes (nao o docstring do modulo, que menciona
    # "sem clock/random" em prosa) — sem wall-clock nem random na logica.
    src = "".join(inspect.getsource(fn) for fn in
                  (tw.materialize, tw.drain_new_verdicts, tw._split_patterns))
    assert "datetime.now" not in src and "time.time" not in src
    assert "random" not in src
