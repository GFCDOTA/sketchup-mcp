"""FP-035 — testes de contrato do retrieve(): room/style/budget -> DesignSpecBundle.v1.

Determinísticos, herméticos: DB em tmp_path, zero rede, zero clock/random. Provam
o contrato (valida contra schema), o ranking estável, a degradação honesta
(confidence LOW sem corpus julgado FP-034), o colapso de sinônimo e o budget_fit.
Fonte dos tokens = references/tokens/*.json (real, read-only)."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from tools import reference_db as rdb

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/design_spec_bundle.schema.json").read_text("utf-8"))


def _validate(bundle: dict) -> None:
    jsonschema.validate(bundle, SCHEMA)


def _fresh_db(tmp_path, monkeypatch):
    """DB temporário ingerido do reference_lab + references/tokens (real)."""
    monkeypatch.setattr(rdb, "DB_PATH", tmp_path / "reference.db")
    con = rdb.connect()
    rdb.init(con)
    rdb.ingest(con)
    return con


# --- contrato do bundle -----------------------------------------------------

def test_bundle_validates_against_schema():
    bundle = rdb.retrieve("kitchen", "black_wood_gold")
    _validate(bundle)
    assert bundle["schema_version"] == "design_spec_bundle.v1"
    assert bundle["query"] == {"room": "kitchen", "style": "black_wood_gold",
                               "budget": None}


def test_retrieve_kitchen_black_wood_gold_returns_tokens():
    bundle = rdb.retrieve("kitchen", "black_wood_gold")
    names = {t["name"] for t in bundle["tokens"]}
    # os tokens-âncora de cozinha da spec (Acceptance): torre quente + base madeira.
    assert "hot_tower_niche" in names
    assert "coordinated_medium_dark_wood_base" in names
    assert len(bundle["tokens"]) >= 3
    # todo token traz builder_kinds e source_path rastreável.
    for t in bundle["tokens"]:
        assert t["builder_kinds"]
        assert t["source_path"].startswith("references/tokens/")


def test_retrieve_excludes_wrong_room_tokens():
    # os tokens curados são de cozinha; bedroom não deve vazar token de cozinha.
    bundle = rdb.retrieve("bedroom", "black_wood_gold")
    assert bundle["tokens"] == []
    _validate(bundle)


# --- ranking determinístico -------------------------------------------------

def test_ranking_is_deterministic():
    a = rdb.retrieve("kitchen", "black_wood_gold", "medio")
    b = rdb.retrieve("kitchen", "black_wood_gold", "medio")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    # ordem dos nomes estável entre chamadas
    assert [t["name"] for t in a["tokens"]] == [t["name"] for t in b["tokens"]]


def test_no_clock_or_random_in_retrieve():
    import inspect
    src = inspect.getsource(rdb.retrieve)
    assert "random" not in src
    assert "datetime.now" not in src and "time.time" not in src


# --- colapso de sinônimo / dedup -------------------------------------------

def test_synonym_collapse_dedup(monkeypatch):
    # injeta um token de disco cujo nome é sinônimo de outro já presente:
    # 'integrated_fridge_tower' -> canônico 'fridge_tower' (via reference_grammar).
    real = rdb._load_disk_tokens

    def _patched(room):
        toks = real(room)
        # duplica um token sob dois nomes-sinônimo do mesmo canônico
        base = dict(toks[0])
        toks.append({**base, "raw_name": "integrated_fridge_tower"})
        toks.append({**base, "raw_name": "fridge_tower"})
        return toks

    monkeypatch.setattr(rdb, "_load_disk_tokens", _patched)
    bundle = rdb.retrieve("kitchen", "black_wood_gold", top_n=20)
    names = [t["name"] for t in bundle["tokens"]]
    # sinônimo colapsado -> aparece 'fridge_tower' UMA vez, 'integrated_fridge_tower' some
    assert names.count("fridge_tower") == 1
    assert "integrated_fridge_tower" not in names


# --- anti-patterns ----------------------------------------------------------

def test_anti_pattern_carried():
    bundle = rdb.retrieve("kitchen", "black_wood_gold")
    assert bundle["anti_patterns"]                     # não vazio (tokens têm anti)
    # o anti_pattern do hot_tower_niche fala de forno/torre — deve estar presente
    blob = " ".join(bundle["anti_patterns"]).lower()
    assert "forno" in blob or "torre" in blob or "puxador" in blob


# --- honestidade FP-034 -----------------------------------------------------

def test_confidence_low_when_fp034_corpus_absent():
    # sem DB / sem judged_variant -> confidence LOW, nunca HIGH fabricado.
    bundle = rdb.retrieve("kitchen", "black_wood_gold")
    assert bundle["confidence"] == "LOW"
    assert any("FP-034" in n for n in bundle["notes"])


def test_confidence_high_when_fp034_present_with_pass(tmp_path, monkeypatch):
    con = _fresh_db(tmp_path, monkeypatch)
    rdb._upsert(con, {
        "slug": "variant/v1", "kind": "judged_variant", "path": "x/iso.png",
        "room": "kitchen", "theme": "black_wood_gold",
        "curation_status": "candidate",
        "gate_verdicts": json.dumps({"geometry_sanity": "PASS"}),
    })
    con.commit()
    bundle = rdb.retrieve("kitchen", "black_wood_gold", con=con)
    assert bundle["confidence"] == "HIGH"
    _validate(bundle)
    # provenance registra o judged_variant como origem do sinal (honestidade)
    kinds = {p["kind"] for p in bundle["provenance"]}
    assert "judged_variant" in kinds
    con.close()


# --- budget_fit -------------------------------------------------------------

def _rank_of(bundle: dict, name: str) -> int:
    names = [t["name"] for t in bundle["tokens"]]
    return names.index(name) if name in names else len(names)


def test_budget_fit_penalizes_overshoot():
    # hot_tower_niche é custo 'alto'; com budget=baixo ele é rebaixado no ranking
    # (budget_fit=-1) vs sem budget (0). Prova o sinal de budget_fit no score.
    low = rdb.retrieve("kitchen", "black_wood_gold", "baixo", top_n=12)
    none = rdb.retrieve("kitchen", "black_wood_gold", top_n=12)
    # sob budget baixo o token 'alto' cai (índice maior = pior posição)
    assert _rank_of(low, "hot_tower_niche") > _rank_of(none, "hot_tower_niche")


def test_cost_level_parses_prose():
    assert rdb._cost_level("alto (coluna dedicada...)") == 5
    assert rdb._cost_level("médio (laminado...)") == 3
    assert rdb._cost_level("baixo (fita LED é barata)") == 1
    assert rdb._cost_level(None) is None


# --- tokens dir indexado (ingest estendido) ---------------------------------

def test_tokens_dir_indexed(tmp_path, monkeypatch):
    con = _fresh_db(tmp_path, monkeypatch)
    rows = rdb.query(con, kind="token", room="kitchen")
    slugs = {r["slug"] for r in rows}
    assert "hot_tower_niche" in slugs
    assert "coordinated_medium_dark_wood_base" in slugs
    assert len(rows) >= 12
    con.close()
