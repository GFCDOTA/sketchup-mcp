"""corpus_to_rag + human_verdicts.jsonl — o veredito do Felipe entra nos RAGs.

O arquivo e' escrito SO pelo clique na tela de curadoria do :8782
(KICKOFF_CURADORIA, Fatia 2); aqui pina-se o CONSUMO: overlay last-wins em
memoria (corpus nunca reescrito), vocabulario humano IMPROVED|SAME|WORSE
estrito, e propagacao pros dois exports (reference_db notes/tags e memory json).
Hermetico: tudo em tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.corpus_to_rag import _last_wins, export_memory_json, export_reference_rows


def _rec(vid: str, verdict: str = "CANDIDATE") -> dict:
    return {
        "schema": "judged_variant/1.0.0", "run_id": "planta_x", "variant_id": vid,
        "created_at": "2026-07-04T05:00:00Z", "plant": "planta_x",
        "params": {"style": None, "theme": "", "layout_seed": 0},
        "geometry": {"n_boxes": 1, "deterministic_gates": {"geometry_sanity": "PASS"}},
        "render_refs": {"iso": f"{vid}/iso.png", "sha256": "abc", "renderer": "su-free"},
        "visual_findings": None,
        "machine_score": {"value": 0.6, "label": "machine_provisional"},
        "verdict": verdict, "human_verdict": None,
    }


def _write(tmp_path: Path, corpus: list[dict], human: list[dict] | None = None) -> Path:
    p = tmp_path / "corpus.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in corpus), "utf-8")
    if human is not None:
        (tmp_path / "human_verdicts.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in human), "utf-8")
    return p


def test_overlay_last_wins_and_strict_vocabulary(tmp_path):
    corpus = _write(tmp_path, [_rec("v1"), _rec("v2")], human=[
        {"variant_id": "v1", "human_verdict": "SAME", "note": "1a impressao",
         "t": "2026-07-04T10:00:00Z"},
        {"variant_id": "v1", "human_verdict": "IMPROVED", "note": "melhor pra X",
         "t": "2026-07-04T10:05:00Z"},          # correcao: o ULTIMO clique vence
        {"variant_id": "v2", "human_verdict": "CANDIDATE"},   # vocabulario da MAQUINA -> ignorado
        {"variant_id": "fantasma", "human_verdict": "WORSE"},  # variante inexistente -> ignorado
    ])
    by = {r["variant_id"]: r for r in _last_wins(corpus)}
    assert by["v1"]["human_verdict"] == {"verdict": "IMPROVED", "note": "melhor pra X",
                                         "t": "2026-07-04T10:05:00Z"}
    assert by["v2"]["human_verdict"] is None
    # rail: overlay e' SO em memoria — o corpus no disco continua com null
    assert all(json.loads(ln)["human_verdict"] is None
               for ln in corpus.read_text("utf-8").splitlines())


def test_missing_human_file_keeps_export_identical(tmp_path):
    corpus = _write(tmp_path, [_rec("v1")])
    (row, tags), = export_reference_rows(corpus)
    assert row["notes"] == "CANDIDATE"
    assert not any(t.startswith("human_") for t in tags)


def test_reference_rows_carry_human_verdict_in_notes_and_tags(tmp_path):
    corpus = _write(tmp_path, [_rec("v1")], human=[
        {"variant_id": "v1", "human_verdict": "IMPROVED", "note": "melhor pra X",
         "t": "2026-07-04T10:05:00Z"}])
    (row, tags), = export_reference_rows(corpus)
    assert row["notes"] == "CANDIDATE | human:IMPROVED (melhor pra X)"
    assert "human_improved" in tags
    # promocao a golden continua decisao humana FORA daqui (kickoff: fora de escopo)
    assert row["curation_status"] == "candidate"


def test_memory_json_carries_human_verdict(tmp_path):
    corpus = _write(tmp_path, [_rec("v1"), _rec("v2")], human=[
        {"variant_id": "v2", "human_verdict": "WORSE", "note": "", "t": None}])
    out = tmp_path / "judged_variants.json"
    assert export_memory_json(corpus, out) == 2
    items = {i["id"]: i for i in json.loads(out.read_text("utf-8"))}
    assert items["v2"]["human_verdict"] == {"verdict": "WORSE", "note": "", "t": None}
    assert items["v1"]["human_verdict"] is None
