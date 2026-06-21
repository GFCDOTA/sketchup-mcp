"""Testes do pacote consult_gpt_bridge (contracts/store/prompt_builder/answer_parser/ingest).

Cobre o caminho do MVP manual: build -> render -> store -> parse -> ingest (idempotente), e os
gotchas reais que já queimaram (Título/Descrição com valor na linha de baixo; dedup; COMPARE).
Tudo determinístico (clock injetado via ts/now; paths redirecionados pra tmp_path).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.interior_studio.consult_gpt_bridge import (  # noqa: E402
    answer_parser, contracts, ingest, openai_client, prompt_builder, store)


# ------------------------------------------------------------------ contracts
def test_build_judge_is_valid():
    q = prompt_builder.build_judge(render="https://x/c.png", theme="BLACK_WOOD_GOLD",
                                   question_id="kitchen_skin_001", now="2026-06-20T12:00:00")
    assert contracts.validate_question(q) == []
    assert q["mode"] == "JUDGE" and q["question_id"] == "kitchen_skin_001"


def test_validate_question_catches_missing_and_enum():
    bad = {"question_id": "x", "mode": "NOPE", "room": "garagem"}
    errs = contracts.validate_question(bad)
    assert any("mode" in e for e in errs)
    assert any("room" in e for e in errs)
    assert any("falta" in e for e in errs)


def test_compare_requires_compare_block():
    q = prompt_builder.build_judge(render="r", theme="T", question_id="q1", now="2026-06-20T12:00:00")
    q["mode"] = "COMPARE"
    q["visual_inputs"] = {"main": "r", "aux": [], "compare": {}}   # COMPARE sem compare -> inválido
    assert any("COMPARE" in e for e in contracts.validate_question(q))
    q["visual_inputs"]["compare"] = {"A": "a.png", "B": "b.png"}   # com compare -> válido
    assert contracts.validate_question(q) == []


def test_render_question_md_has_sections():
    q = prompt_builder.build_judge(render="r", theme="T", question_id="q1", now="2026-06-20T12:00:00")
    md = contracts.render_question_md(q)
    for token in ("ARCHITECT_QUESTION_CONTRACT v1", "## Contexto", "cave_check", "ARCHITECT_ANSWER_CONTRACT v1"):
        assert token in md


# ------------------------------------------------------------------ store
def test_store_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CONSULT", tmp_path / "ic")
    q = prompt_builder.build_judge(render="r", theme="T", question_id="kitchen_skin_001",
                                   now="2026-06-20T12:00:00")
    store.save_question(q, ts="20260620T120000")
    assert store.latest_question()["question_id"] == "kitchen_skin_001"
    store.save_answer("kitchen_skin_001", "## Veredito\nPASS\nok", ts="20260620T120500")
    assert "PASS" in store.latest_answer()["raw"]
    assert store.counts() == {"ingested": 0, "failed": 0}


# ------------------------------------------------------------------ parser
ANSWER = """# ARCHITECT_ANSWER_CONTRACT v1
## Metadata
- question_id: `kitchen_skin_001`
- verdict: `WARN`

## Veredito
`WARN`
se segura mas o lado direito apaga.

## Respostas as duvidas
1. cave_check: WARN - lado direito vira buraco escuro.
2. fake_luxury_check: PASS - dourado sutil.
7. ajuste_1: adicionar fill light quente no lado direito.

## Atualizacao para Felipe Style DNA
- cozinha dark precisa de fill light de apoio
- madeira de acento em nicho visivel

## Anti-patterns detectados
- `black_blob_appliance`: eletro some no fundo
- `flat_black_wall`: tudo no mesmo preto

## Proxima microtarefa
Titulo:
`MT-09 - Testar coifa inox dark`
Descricao:
Gerar 3 variacoes de material.
Criterio de aceite:
- coifa percebida em 2s
- nao compete com backsplash
Arquivos provaveis:
- tools/kitchen_vray.py
"""


def test_parse_answer_full():
    p = answer_parser.parse_answer(ANSWER)
    assert p["verdict"] == "WARN"
    assert p["question_id"] == "kitchen_skin_001"
    ids = {qa["id"] for qa in p["question_answers"]}
    assert {"cave_check", "fake_luxury_check", "ajuste_1"} <= ids
    assert "fill light" in p["top_fix"].lower()
    assert len(p["dna_updates"]) == 2
    assert len(p["anti_patterns"]) == 2 and all("`" not in a for a in p["anti_patterns"])  # backtick limpo
    # gotcha: Título/Descrição com valor na linha de baixo
    assert p["next_microtask"]["id"] == "MT-09"
    assert p["next_microtask"]["description"].startswith("Gerar 3 variacoes")
    assert len(p["next_microtask"]["acceptance"]) == 2
    assert p["next_microtask"]["likely_files"] == ["tools/kitchen_vray.py"]


def test_parse_answer_accepts_raw_json():
    p = answer_parser.parse_answer('{"verdict": "PASS", "question_id": "j1"}')
    assert p["verdict"] == "PASS" and p["question_id"] == "j1"


# ------------------------------------------------------------------ ingest (idempotente)
def test_ingest_apply_learning_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "CONSULT", tmp_path / "ic")
    monkeypatch.setattr(ingest, "FELIPE_DNA", tmp_path / "dna.md")
    monkeypatch.setattr(ingest, "JUDGE_RULES", tmp_path / "judge.json")
    monkeypatch.setattr(ingest, "FEEDBACK", tmp_path / "fb")
    monkeypatch.setattr(ingest, "NEXT_MT", tmp_path / "ic" / "next.md")
    ingest.FELIPE_DNA.write_text("# DNA\n", "utf-8")
    ingest.JUDGE_RULES.write_text(json.dumps({"anti_patterns": [], "flagged": []}), "utf-8")

    parsed = answer_parser.parse_answer(ANSWER)
    r1 = ingest.apply_learning(parsed, "kitchen_skin_001", ANSWER)
    assert r1["ok"] and r1["verdict"] == "WARN"
    assert len(r1["rules_added"]) == 2 and len(r1["anti_patterns_added"]) == 2
    assert "corrections" in r1["feedback_path"]   # WARN -> corrections
    assert "MT-09" in ingest.NEXT_MT.read_text("utf-8")

    r2 = ingest.apply_learning(parsed, "kitchen_skin_001", ANSWER)   # 2ª vez não duplica
    assert r2["rules_added"] == [] and r2["anti_patterns_added"] == []
    assert len(json.loads(ingest.JUDGE_RULES.read_text("utf-8"))["anti_patterns"]) == 2


# ------------------------------------------------------------------ openai stub
def test_openai_stub_never_breaks(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = openai_client.ask({"any": "thing"})
    assert r["ok"] is False and r["fallback"] == "manual"
