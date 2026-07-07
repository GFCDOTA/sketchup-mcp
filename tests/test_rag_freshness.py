"""FP-037 Camada 1 — freshness, cache-invalidation e source-registry do RAG.

Determinísticos e HERMÉTICOS: corpus em tmp_path (fontes fake), DB em tmp_path,
zero rede, zero clock/random real (now_iso é sempre INJETADO). Provam:

  - corpus_version ESTÁVEL quando nada muda; MUDA quando um documento muda
    (token/anti-pattern/consensus/semantic_zones/learning_patch);
  - chunk mudado ganha chunk_hash novo e é reindexado; chunk igual é REUSADO
    (não re-embeda); chunk sumido vira is_active=false (soft-delete);
  - freshness_guard rejeita chunk inativo / de corpus_version antigo, e sinaliza
    STALE quando a fonte é mais nova que o índice (não usa silenciosamente);
  - cache do arquiteto: document update -> corpus_version novo -> MISS automático.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import rag_freshness as rf

T0 = "2026-07-07T10:00:00Z"
T1 = "2026-07-07T11:00:00Z"
T2 = "2026-07-07T12:00:00Z"


# --------------------------------------------------------------------------- corpus fake
def _write(root: Path, rel: str, content: str, mtime: float | None = None) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    if mtime is not None:
        import os
        os.utime(p, (mtime, mtime))
    return p


@pytest.fixture
def corpus(tmp_path) -> Path:
    """Mini-corpus com uma fonte de cada estratégia relevante (mtime FIXO)."""
    root = tmp_path / "repo"
    mt = 1_700_000_000  # epoch fixo -> updated_at determinístico
    _write(root, ".claude/memory/felipe_style_dna.md",
           "# DNA\nindustrial boutique preto madeira dourado.\n\n"
           "## Cozinha\ntorre quente obrigatória.", mt)
    _write(root, "references/tokens/hot_tower_niche.json", json.dumps({
        "name": "hot_tower_niche", "title": "torre quente",
        "rule": "coluna piso-teto com forno + micro + airfryer em nichos.",
        "anti_pattern": "forno embaixo do cooktop perde ergonomia.",
        "cost_relative": "alto", "applies_to_kinds": ["kc_niche_wood"],
        "params": {"tower_width_cm": 62}}), mt)
    _write(root, "references/tokens/matte_black_cabinetry.json", json.dumps({
        "name": "matte_black_cabinetry", "rule": "marcenaria preta fosca.",
        "cost_relative": "medio", "applies_to_kinds": ["kc_corpo"]}), mt)
    _write(root, "references/felipe/anti_patterns/sofa-anti.json", json.dumps({
        "id": "sofa-anti", "avoid": "sofá povison brega."}), mt)
    _write(root, "references/design_rules/furniture_rule_cards.json", json.dumps(
        [{"card_id": "rc1", "rule": "sofá encosta na parede da TV."}]), mt)
    _write(root, "fixtures/planta_74/semantic_zones.json", json.dumps(
        {"zones": [{"id": "z1", "name": "estar"}]}), mt)
    _write(root, "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json",
           json.dumps({"rooms": [{"id": "r004", "name": "COZINHA", "area_pts2": 900}],
                       "walls": [1, 2, 3], "openings": [1]}), mt)
    _write(root, ".ai_bridge/learning_patches/LP-SOFA-001.json", json.dumps(
        {"id": "LP-SOFA-001", "rule": "per_seat >= 0.75m."}), mt)
    return root


@pytest.fixture
def db(tmp_path):
    con = rf.connect(tmp_path / "rag_freshness.db")
    yield con
    con.close()


# --------------------------------------------------------------------------- source registry
def test_discover_sources_finds_all_registered(corpus):
    docs = rf.discover_sources(corpus)
    ids = {d.document_id for d in docs}
    assert ".claude/memory/felipe_style_dna.md" in ids
    assert "references/tokens/hot_tower_niche.json" in ids
    assert "fixtures/planta_74/semantic_zones.json" in ids
    assert ".ai_bridge/learning_patches/LP-SOFA-001.json" in ids
    # cada doc tem hash + version + updated_at
    for d in docs:
        assert d.content_hash and d.document_version == d.content_hash
        assert d.updated_at.endswith("Z")


def test_discover_sources_is_sorted_and_deterministic(corpus):
    a = [d.document_id for d in rf.discover_sources(corpus)]
    b = [d.document_id for d in rf.discover_sources(corpus)]
    assert a == b == sorted(a)


# --------------------------------------------------------------------------- corpus_version
def test_corpus_version_stable_when_nothing_changes(corpus):
    v1 = rf.compute_corpus_version(rf.discover_sources(corpus))
    v2 = rf.compute_corpus_version(rf.discover_sources(corpus))
    assert v1 == v2 and len(v1) == 64


@pytest.mark.parametrize("rel,new", [
    ("references/tokens/hot_tower_niche.json",
     json.dumps({"name": "hot_tower_niche", "rule": "MUDOU a regra da torre."})),
    ("references/felipe/anti_patterns/sofa-anti.json",
     json.dumps({"id": "sofa-anti", "avoid": "OUTRO anti-padrão."})),
    ("fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json",
     json.dumps({"rooms": [{"id": "r004", "name": "COZINHA", "area_pts2": 999}],
                 "walls": [1, 2, 3, 4], "openings": [1]})),
    ("fixtures/planta_74/semantic_zones.json",
     json.dumps({"zones": [{"id": "z1", "name": "estar"}, {"id": "z2", "name": "jantar"}]})),
    (".ai_bridge/learning_patches/LP-SOFA-001.json",
     json.dumps({"id": "LP-SOFA-001", "rule": "per_seat >= 0.80m (MUDOU)."})),
])
def test_corpus_version_changes_when_a_source_changes(corpus, rel, new):
    before = rf.compute_corpus_version(rf.discover_sources(corpus))
    _write(corpus, rel, new, mtime=1_700_000_500)
    after = rf.compute_corpus_version(rf.discover_sources(corpus))
    assert before != after, f"corpus_version deveria mudar ao editar {rel}"


def test_corpus_version_changes_on_add_and_remove(corpus):
    before = rf.compute_corpus_version(rf.discover_sources(corpus))
    added = _write(corpus, "references/tokens/new_token.json",
                   json.dumps({"name": "new_token", "rule": "novo."}), mtime=1_700_000_600)
    after_add = rf.compute_corpus_version(rf.discover_sources(corpus))
    assert before != after_add
    added.unlink()
    after_rm = rf.compute_corpus_version(rf.discover_sources(corpus))
    assert after_rm == before  # remoção volta ao hash original


# --------------------------------------------------------------------------- reindex incremental
def test_reindex_populates_chunks_and_corpus_version(corpus, db):
    rep = rf.reindex(db, root=corpus, now_iso=T0)
    assert rep["chunks_reindexed"] > 0
    assert rep["chunks_reused"] == 0  # primeira vez: tudo novo
    assert rf.current_corpus_version(db) == rep["corpus_version"]
    # todos os chunks recém-criados são embedded=0 (pendentes pro backend embed)
    n_pending = db.execute("SELECT COUNT(*) FROM chunk WHERE embedded=0").fetchone()[0]
    assert n_pending == rep["chunks_reindexed"]


def test_reindex_reuses_unchanged_chunks(corpus, db):
    rf.reindex(db, root=corpus, now_iso=T0)
    rep2 = rf.reindex(db, root=corpus, now_iso=T1)
    # nada mudou no disco -> tudo REUSADO, zero reindexado
    assert rep2["chunks_reindexed"] == 0
    assert rep2["chunks_reused"] > 0
    assert rep2["chunks_deactivated"] == 0


def test_reindex_changed_chunk_gets_new_hash(corpus, db):
    rf.reindex(db, root=corpus, now_iso=T0)
    before = db.execute(
        "SELECT chunk_hash FROM chunk WHERE document_id=? AND chunk_index=0",
        ("references/tokens/matte_black_cabinetry.json",)).fetchone()["chunk_hash"]
    _write(corpus, "references/tokens/matte_black_cabinetry.json", json.dumps({
        "name": "matte_black_cabinetry", "rule": "REGRA NOVA da marcenaria preta.",
        "cost_relative": "alto", "applies_to_kinds": ["kc_corpo"]}), mtime=1_700_000_700)
    rep = rf.reindex(db, root=corpus, now_iso=T1)
    after = db.execute(
        "SELECT chunk_hash, embedded FROM chunk WHERE document_id=? AND chunk_index=0",
        ("references/tokens/matte_black_cabinetry.json",)).fetchone()
    assert after["chunk_hash"] != before          # hash mudou
    assert after["embedded"] == 0                 # marcado pra re-embedar
    assert rep["chunks_reindexed"] >= 1


def test_reindex_removed_document_soft_deletes_chunks(corpus, db):
    rf.reindex(db, root=corpus, now_iso=T0)
    (corpus / "references/tokens/matte_black_cabinetry.json").unlink()
    rep = rf.reindex(db, root=corpus, now_iso=T1)
    assert rep["docs_deactivated"] == 1
    assert rep["chunks_deactivated"] >= 1
    # soft-delete: as linhas continuam no .db, só is_active=0 (histórico preservado)
    rows = db.execute(
        "SELECT is_active FROM chunk WHERE document_id=?",
        ("references/tokens/matte_black_cabinetry.json",)).fetchall()
    assert rows and all(r["is_active"] == 0 for r in rows)


def test_reindex_is_deterministic_no_clock():
    import inspect
    src = inspect.getsource(rf.reindex) + inspect.getsource(rf.compute_corpus_version)
    assert "datetime.now" not in src and "time.time" not in src
    assert "random" not in src


# --------------------------------------------------------------------------- freshness guard
def test_guard_returns_only_active_current_chunks(corpus, db):
    rf.reindex(db, root=corpus, now_iso=T0)
    cv = rf.current_corpus_version(db)
    chunks = rf.active_chunks(db, cv)
    res = rf.freshness_guard(db, chunks, root=corpus)
    assert len(res.fresh_chunks) == len(chunks)
    assert not res.rejected and not res.stale


def test_guard_rejects_inactive_chunk(corpus, db):
    rf.reindex(db, root=corpus, now_iso=T0)
    cv = rf.current_corpus_version(db)
    chunks = rf.active_chunks(db, cv)
    victim = chunks[0]
    db.execute("UPDATE chunk SET is_active=0 WHERE chunk_id=?", (victim["chunk_id"],))
    db.commit()
    res = rf.freshness_guard(db, chunks, root=corpus)
    assert any(r["chunk_id"] == victim["chunk_id"] and r["reason"] == "inactive"
               for r in res.rejected)
    assert victim["chunk_id"] not in {c["chunk_id"] for c in res.fresh_chunks}


def test_guard_rejects_stale_corpus_version(corpus, db):
    rf.reindex(db, root=corpus, now_iso=T0)
    cv_old = rf.current_corpus_version(db)
    # muda uma fonte -> corpus_version novo; os chunks antigos não-mudados são
    # RECARIMBADOS pro novo corpus (reuse), mas simulamos um candidato preso na
    # geração antiga passando o snapshot antigo e forçando o hash de um chunk.
    _write(corpus, "references/tokens/hot_tower_niche.json",
           json.dumps({"name": "hot_tower_niche", "rule": "MUDANÇA total."}),
           mtime=1_700_001_000)
    rf.reindex(db, root=corpus, now_iso=T1)
    cv_new = rf.current_corpus_version(db)
    assert cv_new != cv_old
    # injeta um chunk artificial preso no corpus antigo
    db.execute(
        "INSERT INTO chunk (chunk_id, document_id, document_version, chunk_index, "
        "title, text, chunk_hash, corpus_version, source_path, source_type, "
        "indexed_at, is_active, embedded) VALUES "
        "('deadbeefdeadbeef0001','d','v',0,'t','texto antigo','h',?, 'd','x',?,1,1)",
        (cv_old, T0))
    db.commit()
    res = rf.freshness_guard(db, [{"chunk_id": "deadbeefdeadbeef0001", "document_id": "d"}],
                             root=corpus)
    assert any(r["reason"] == "stale_corpus_version" for r in res.rejected)


def test_guard_flags_source_newer_than_index_as_stale(corpus, db):
    # índice construído em T0; a fonte é 'tocada' DEPOIS (mtime futuro) sem reindex
    rf.reindex(db, root=corpus, now_iso=T0)
    cv = rf.current_corpus_version(db)
    chunks = rf.active_chunks(db, cv)
    # torna a fonte mais nova que o índice: reescreve mesmo conteúdo com mtime > indexed_at
    p = corpus / "references/tokens/hot_tower_niche.json"
    import os
    os.utime(p, (1_900_000_000, 1_900_000_000))  # mtime bem no futuro
    res = rf.freshness_guard(db, chunks, root=corpus)
    stale_docs = {s["document_id"] for s in res.stale}
    assert "references/tokens/hot_tower_niche.json" in stale_docs
    assert res.has_stale
    # os chunks stale NÃO entram no fresh (não usados silenciosamente)
    fresh_ids = {c["chunk_id"] for c in res.fresh_chunks}
    stale_ids = {s["chunk_id"] for s in res.stale}
    assert fresh_ids.isdisjoint(stale_ids)


# --------------------------------------------------------------------------- cache invalidation
def _fake_response(corpus_version: str) -> dict:
    return {"program": ["sofa", "rack"], "rag_corpus_version": corpus_version}


def test_cache_hit_same_corpus(corpus, db):
    rf.reindex(db, root=corpus, now_iso=T0)
    cv = rf.current_corpus_version(db)
    qh = rf.query_hash("mobilia da cozinha industrial")
    key = rf.cache_key(query_hash=qh, corpus_version=cv, room_id="r004",
                       style_profile="black_wood_gold")
    assert rf.cache_get(db, key) is None  # MISS inicial
    rf.cache_put(db, key, corpus_version=cv, room_id="r004",
                 style_profile="black_wood_gold", response=_fake_response(cv), now_iso=T0)
    hit = rf.cache_get(db, key)
    assert hit is not None and hit["program"] == ["sofa", "rack"]


def test_document_update_invalidates_cache(corpus, db):
    # 1) indexa, cacheia uma resposta na chave do corpus atual
    rf.reindex(db, root=corpus, now_iso=T0)
    cv0 = rf.current_corpus_version(db)
    qh = rf.query_hash("mobilia da cozinha industrial")
    key0 = rf.cache_key(query_hash=qh, corpus_version=cv0, room_id="r004",
                        style_profile="black_wood_gold")
    rf.cache_put(db, key0, corpus_version=cv0, room_id="r004",
                 style_profile="black_wood_gold", response=_fake_response(cv0), now_iso=T0)
    assert rf.cache_get(db, key0) is not None

    # 2) um documento muda -> reindex -> corpus_version novo
    _write(corpus, "references/tokens/hot_tower_niche.json",
           json.dumps({"name": "hot_tower_niche", "rule": "REGRA NOVA."}),
           mtime=1_700_002_000)
    rf.reindex(db, root=corpus, now_iso=T1)
    cv1 = rf.current_corpus_version(db)
    assert cv1 != cv0

    # 3) a chave NOVA (corpus_version na chave) dá MISS -> recomputa, sem servir stale
    key1 = rf.cache_key(query_hash=qh, corpus_version=cv1, room_id="r004",
                        style_profile="black_wood_gold")
    assert key1 != key0
    assert rf.cache_get(db, key1) is None

    # 4) defesa-em-profundidade: mesmo pedindo a chave ANTIGA, o cache_get vê que o
    #    corpus_version divergiu do atual e devolve MISS (não serve resposta velha)
    assert rf.cache_get(db, key0) is None


def test_purge_stale_cache_removes_old_corpus(corpus, db):
    rf.reindex(db, root=corpus, now_iso=T0)
    cv0 = rf.current_corpus_version(db)
    key = rf.cache_key(query_hash="q", corpus_version=cv0, room_id="r", style_profile="s")
    rf.cache_put(db, key, corpus_version=cv0, room_id="r", style_profile="s",
                 response={"x": 1}, now_iso=T0)
    _write(corpus, "references/tokens/hot_tower_niche.json",
           json.dumps({"name": "hot_tower_niche", "rule": "muda."}), mtime=1_700_003_000)
    rf.reindex(db, root=corpus, now_iso=T1)
    n = rf.purge_stale_cache(db)
    assert n == 1
    remaining = db.execute("SELECT COUNT(*) FROM arch_cache").fetchone()[0]
    assert remaining == 0


def test_cache_key_depends_on_all_inputs():
    base = dict(query_hash="q", corpus_version="c", room_id="r", style_profile="s")
    k0 = rf.cache_key(**base)
    assert k0 != rf.cache_key(**{**base, "query_hash": "q2"})
    assert k0 != rf.cache_key(**{**base, "corpus_version": "c2"})
    assert k0 != rf.cache_key(**{**base, "room_id": "r2"})
    assert k0 != rf.cache_key(**{**base, "style_profile": "s2"})
    assert k0 != rf.cache_key(**{**base, "retrieval_config_version": "v99"})
    assert k0 == rf.cache_key(**base)  # estável
