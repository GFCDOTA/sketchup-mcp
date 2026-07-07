"""Bloco 2 — APARENCIA NAO-BLOQUEIA. O pipeline gera o .skp canonico + renders,
emite um item de galeria PENDENTE (human_verdict=None, verdict PENDING_VISION|
CANDIDATE) na MESMA galeria do sweep e SEGUE, sem esperar veredito humano.

Cobre os 3 pontos de emissao (furnish, noc_dispatcher, correction_loop) + o
emitter canonico compartilhado, todos reusando variant_sweep.build_record.
Hermetico: tudo em tmp_path, SketchUp/git/subprocess mockados, corpus/paths
injetados. Zero SketchUp real, zero git real, zero rede."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from tools import correction_loop as loop
from tools.claude_bridge import noc_dispatcher as nd
from tools.jsonl_io import read_jsonl
from tools.variant_axes import Variant

# NAO importar furnish_apartment / variant_sweep no NIVEL DO MODULO: os dois setam
# PT_TO_M=0.0259 ANTES de importar core.scale, e este arquivo coleta ALFABETICAMENTE
# CEDO — o import em collection-time congelaria core.scale em 0.0259 pro processo
# inteiro, quebrando os testes de placement (bed/bedroom/room_modes) que esperam o
# default 0.0352. Import LAZY dentro dos testes: quando rodam, core.scale ja esta
# congelado (a cadeia cacheada nao re-congela) — mesma disciplina do subprocess de
# test_variant_sweep. noc_dispatcher/correction_loop NAO forcam esse freeze (import
# lazy de variant_sweep la dentro), entao ficam no topo.

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "judged_variant.schema.json"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _png(dir_: Path, name: str = "iso.png") -> Path:
    from PIL import Image
    dir_.mkdir(parents=True, exist_ok=True)
    p = dir_ / name
    Image.new("RGB", (16, 12), (180, 150, 120)).save(p)
    return p


def _pending(rec: dict) -> None:
    """Contrato compartilhado do item de galeria pendente."""
    assert rec["human_verdict"] is None                  # a maquina NUNCA preenche
    assert rec["verdict"] in ("CANDIDATE", "PENDING_VISION")
    assert rec["machine_score"]["label"] == "machine_provisional"


# --- emitter canonico compartilhado ---------------------------------------------


def test_emit_gallery_item_is_pending_and_idempotent(tmp_path, validator):
    from tools import variant_sweep as vs  # lazy: ver nota de import no topo
    corpus = tmp_path / "run" / "corpus.jsonl"
    corpus.parent.mkdir(parents=True)
    png = _png(tmp_path / "run" / "v1")
    v = Variant(plant="planta_74", style=None, theme="", layout_seed=0)
    rec = vs.emit_gallery_item(corpus, v, png=png, log=lambda *_: None)
    _pending(rec)
    assert rec["verdict"] == "PENDING_VISION"             # sem findings -> pendente
    validator.validate(rec)
    assert len(read_jsonl(corpus)) == 1
    # 2a chamada = mesmo variant_id -> NAO re-appenda (idempotente), retorna o mesmo
    again = vs.emit_gallery_item(corpus, v, png=png, log=lambda *_: None)
    assert again["variant_id"] == rec["variant_id"]
    assert len(read_jsonl(corpus)) == 1                   # corpus nunca reescrito/duplicado


# --- furnish: item emitido DEPOIS do gate, sem travar; .skp NAO regride ----------


def test_furnish_emit_helper_records_flat_white_without_blocking(tmp_path, validator):
    from tools import furnish_apartment as fa  # lazy: ver nota de import no topo
    png = _png(tmp_path / "furn")
    corpus = tmp_path / "gallery" / "planta_74" / "corpus.jsonl"
    fw = {"result": "FAIL", "flags": ["chapado_de_branco"],
          "fails": ["chapado_de_branco: 60% quase-branco"], "warns": []}
    rec = fa._emit_furnished_gallery_item(
        png, skp=tmp_path / "planta_74_furnished.skp", style=None,
        flat_white=fw, corpus=corpus)
    _pending(rec)
    # flat_white FAIL e' APARENCIA: vai pro gate_detail (recuperavel), NUNCA vira
    # gate FAIL que travaria o item -> verdict pendente, nao FAIL
    assert rec["verdict"] == "PENDING_VISION"
    gd = rec["geometry"]["gate_detail"]
    assert gd["flat_white"]["result"] == "FAIL"
    assert gd["source"] == "furnish_apartment"
    assert rec["geometry"]["deterministic_gates"]["kitchen_validation"] == "PASS"
    validator.validate(rec)
    assert len(read_jsonl(corpus)) == 1
    fa._emit_furnished_gallery_item(png, skp=None, style=None, corpus=corpus)
    assert len(read_jsonl(corpus)) == 1                   # idempotente por variant_id


def test_furnish_main_still_builds_skp_and_emits_after_gate(tmp_path, monkeypatch,
                                                            validator):
    """Mocka a parte SketchUp: prova que (a) o .skp canonico AINDA e' gerado (o
    comando SU sai com LAYOUT_OUT apontando pro .skp) e (b) o item de galeria e'
    emitido DEPOIS do flat_white_gate — e main() RETORNA sem esperar veredito."""
    from tools import furnish_apartment as fa  # lazy: ver nota de import no topo
    monkeypatch.delenv("FURNISH_STYLE", raising=False)
    monkeypatch.setattr(sys, "argv", ["furnish_apartment"])           # argparse limpo
    monkeypatch.setattr(fa, "OUT_DIR", tmp_path / "furnished")
    monkeypatch.setattr(fa, "GALLERY_CORPUS_ROOT", tmp_path / "gallery")
    # SU-free: collect_boxes fixo (sem brains reais / freeze de escala)
    box = {"kind": "x", "room": "r", "module": "m", "rgb": [1, 2, 3],
           "z0_in": 0.0, "h_in": 30.0,
           "corners": [[0, 0], [10, 0], [10, 10], [0, 10]]}
    monkeypatch.setattr(fa, "collect_boxes",
                        lambda con: ([dict(box)], [("r1", "sala", "LIVING", "OK", 1)]))
    monkeypatch.setattr(fa.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(fa.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"", stderr=b""))
    monkeypatch.setattr("tools.flat_white_gate.flat_white_check",
                        lambda *a, **k: {"result": "WARN", "flags": ["quase_branco"],
                                         "fails": [], "warns": ["quase_branco"]})
    captured: dict = {}

    def fake_popen(cmd, env=None, creationflags=0):
        captured["cmd"], captured["env"] = cmd, env
        iso = Path(env["LAYOUT_AFTER_ISO"])
        iso.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        Image.new("RGB", (16, 12), (170, 140, 110)).save(iso)
        Path(env["LAYOUT_LOG"]).write_text("furnish ok\n", encoding="utf-8")
        return SimpleNamespace()

    monkeypatch.setattr(fa.subprocess, "Popen", fake_popen)

    assert fa.main() is None                              # RETORNA sem esperar veredito
    # (a) .skp canonico: o comando SU foi montado com o .skp de saida INTACTO
    assert str(fa.BASE_SKP) in captured["cmd"] and str(fa.RB) in captured["cmd"]
    assert captured["env"]["LAYOUT_OUT"].endswith("planta_74_furnished.skp")
    # (b) item de galeria emitido DEPOIS do gate, na galeria compartilhada
    corpus = fa.GALLERY_CORPUS_ROOT / "planta_74" / "corpus.jsonl"
    rows = read_jsonl(corpus)
    assert len(rows) == 1
    _pending(rows[0])
    validator.validate(rows[0])
    assert rows[0]["params"]["style"] is None            # baseline (FURNISH_STYLE vazio)


# --- noc_dispatcher: aparencia -> item de galeria pendente, segue ----------------


def test_dispatcher_appearance_emits_pending_gallery_item(tmp_path, monkeypatch,
                                                          validator):
    monkeypatch.setattr(nd, "VARIANT_OUT_ROOT", tmp_path / "noc_variant_sweep")
    ledger: list = []
    monkeypatch.setattr(nd, "ledger_append", ledger.append)
    wt = tmp_path / "wt-noc-t1"
    _png(wt / "renders", "furnished_iso.png")            # render tocado no diff
    monkeypatch.setattr(
        nd, "_git",
        lambda args, cwd=None, timeout=120: (0, "?? renders/furnished_iso.png\n", ""))
    task = {"id": "T1", "plant": "planta_74", "title": "furnish sala"}
    rec = nd._emit_appearance_gallery_item(task, wt)
    assert rec is not None
    _pending(rec)
    assert rec["variant_id"] == "planta_74__noc-t1__warm_compact__L0"
    validator.validate(rec)
    corpus = nd.VARIANT_OUT_ROOT / "planta_74" / "corpus.jsonl"
    assert len(read_jsonl(corpus)) == 1
    # render efemero do wt copiado pro dir persistente da variante (path estavel)
    assert (corpus.parent / rec["variant_id"] / "iso.png").is_file()
    assert rec["render_refs"]["iso"] == f"{rec['variant_id']}/iso.png"
    assert not ledger                                    # sucesso: nada de GALLERY_EMIT_SKIPPED


# --- correction_loop: achado de aparencia -> item recuperavel, nao morre em fila -


def _finding(type_, sev="FAIL", evidence="e"):
    return {"type": type_, "severity": sev, "source": "deterministic",
            "evidence": evidence}


def test_correction_loop_needs_felipe_emits_recoverable_gallery_item(tmp_path,
                                                                     validator):
    corpus = tmp_path / "gallery" / "corpus.jsonl"
    res = loop.run_loop(
        fixture="planta_74",
        detect=lambda ctx: [_finding("floating_door", evidence="door")],
        out_dir=tmp_path / "out", gallery_corpus=corpus,
        heartbeat=None, log=lambda m: None)
    assert res.state == loop.NEEDS_FELIPE                 # so aparencia -> Felipe
    # fila-arquivo ANTIGA continua (comportamento intacto)…
    q = (tmp_path / "out" / "visual_review_queue.jsonl").read_text("utf-8").splitlines()
    assert len(q) == 1 and json.loads(q[0])["type"] == "floating_door"
    # …E o item de galeria PENDENTE torna o achado recuperavel
    rows = read_jsonl(corpus)
    assert len(rows) == 1
    _pending(rows[0])
    assert rows[0]["variant_id"] == "planta_74__correction__warm_compact__L0"
    assert rows[0]["geometry"]["gate_detail"]["source"] == "correction_loop"
    validator.validate(rows[0])


def test_correction_loop_without_gallery_corpus_stays_backward_compatible(tmp_path):
    # gallery_corpus=None (default): NENHUM item emitido — comportamento legado
    res = loop.run_loop(
        fixture="planta_74",
        detect=lambda ctx: [_finding("floating_door", evidence="door")],
        out_dir=tmp_path / "out", heartbeat=None, log=lambda m: None)
    assert res.state == loop.NEEDS_FELIPE
    assert not (tmp_path / "gallery").exists()


def test_correction_loop_gallery_emit_is_idempotent(tmp_path):
    corpus = tmp_path / "gallery" / "corpus.jsonl"
    for _ in range(3):
        loop.run_loop(
            fixture="planta_74",
            detect=lambda ctx: [_finding("floating_door", evidence="door")],
            out_dir=tmp_path / "out", gallery_corpus=corpus,
            heartbeat=None, log=lambda m: None)
    assert len(read_jsonl(corpus)) == 1                  # mesmo variant_id -> 1 linha
