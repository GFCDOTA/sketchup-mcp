"""FP-034 — variant sweep: contrato do registro julgado + honestidade (nunca
fabrica achado, nunca grava veredito humano) + corpus append-only idempotente.
Hermetico: tudo em tmp_path; provider de visao SEMPRE injetado (fake) ou None;
urlopen com guard anti-HTTP; a planta real so roda em SUBPROCESS (escala
0.0259 garantida pelo setdefault do modulo — em-processo o core.scale pode ja
estar congelado por outro teste). Zero SketchUp, zero mutacao de fixtures."""
from __future__ import annotations

import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from tools import corpus_to_rag as ctr
from tools import oracle_providers as op
from tools import variant_axes as va
from tools import variant_sweep as vs
from tools.variant_axes import Variant

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "judged_variant.schema.json"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _variant(style=None, theme="", seed=0) -> Variant:
    return Variant(plant="planta_74", style=style, theme=theme, layout_seed=seed)


def _png(dir_: Path, name: str = "iso.png") -> Path:
    """PNG real minimo (PIL) — o contact sheet abre com Image.open."""
    from PIL import Image
    dir_.mkdir(parents=True, exist_ok=True)
    p = dir_ / name
    Image.new("RGB", (16, 12), (200, 200, 200)).save(p)
    return p


def _v1_findings(verdict="PASS", findings=None) -> dict:
    return {
        "schema_version": "visual_findings.v1",
        "top_level_verdict": verdict,
        "axes": {k: {"verdict": "PASS", "evidence": "seen"}
                 for k in op._AXIS_KEYS},
        "findings": findings or [],
        "source": "claude_bridge",
    }


class _FakeProvider:
    def __init__(self, status="ok", findings=None, probe_ok=True):
        self._status = status
        self._findings = findings
        self._probe_ok = probe_ok
        self.calls = 0

    def probe(self):
        return (self._probe_ok, "ok" if self._probe_ok else "offline")

    def call(self, req, out_dir=None):
        self.calls += 1
        return SimpleNamespace(status=self._status,
                               normalized_findings=self._findings,
                               detail="fake")


def _no_http(monkeypatch) -> None:
    def boom(*a, **kw):
        raise AssertionError("HTTP must not be reached on this path")
    monkeypatch.setattr(op.urllib.request, "urlopen", boom)


# --- registro julgado: schema + honestidade -------------------------------------


def test_record_validates_against_schema(tmp_path, validator):
    png = _png(tmp_path / "v1")
    recs = [
        vs.build_record(_variant(), run_id="t", gates={"geometry_sanity": "PASS"},
                        png=png, out_root=tmp_path, findings=None),
        vs.build_record(_variant("industrial", "dark_walnut", 2), run_id="t",
                        gates={"geometry_sanity": "FAIL"}, png=png,
                        out_root=tmp_path, findings=_v1_findings()),
        vs.build_record(_variant(), run_id="t",
                        gates={"kitchen_validation": "FAIL"}, png=None,
                        out_root=tmp_path, findings=None),  # abort sem render
    ]
    for r in recs:
        errors = list(validator.iter_errors(r))
        assert not errors, "; ".join(e.message for e in errors)


def test_missing_findings_yields_pending_vision(tmp_path, monkeypatch):
    _no_http(monkeypatch)
    png = _png(tmp_path / "v1")
    # sem sidecar e sem provider -> None (nunca fabrica)
    assert vs._collect_findings(png, plant="planta_74", provider=None) is None
    rec = vs.build_record(_variant(), run_id="t",
                          gates={"geometry_sanity": "PASS"},
                          png=png, out_root=tmp_path, findings=None)
    assert rec["verdict"] == "PENDING_VISION"
    assert rec["visual_findings"] is None
    assert rec["machine_score"]["value"] is None


def test_machine_never_writes_human_verdict(tmp_path):
    pat = re.compile(r"['\"](IMPROVED|SAME|WORSE)['\"]")
    for mod in (vs, va, ctr):
        assert not pat.search(inspect.getsource(mod)), mod.__name__
    png = _png(tmp_path / "v1")
    for findings in (None, _v1_findings("PASS"), _v1_findings("FAIL")):
        rec = vs.build_record(_variant(), run_id="t",
                              gates={"geometry_sanity": "PASS"},
                              png=png, out_root=tmp_path, findings=findings)
        assert rec["human_verdict"] is None
        assert rec["machine_score"]["label"] == "machine_provisional"


def test_deterministic_gate_fail_marks_record_fail(tmp_path):
    png = _png(tmp_path / "v1")
    # gate FAIL manda SEMPRE, mesmo com findings visuais PASS presentes
    rec = vs.build_record(_variant(), run_id="t",
                          gates={"geometry_sanity": "FAIL",
                                 "furniture_overlap": "PASS"},
                          png=png, out_root=tmp_path,
                          findings=_v1_findings("PASS"))
    assert rec["verdict"] == "FAIL"
    # WARN de overlap fica registrado sem derrubar pra FAIL
    rec2 = vs.build_record(_variant(), run_id="t",
                           gates={"geometry_sanity": "PASS",
                                  "furniture_overlap": "WARN"},
                           png=png, out_root=tmp_path,
                           findings=_v1_findings("PASS"))
    assert rec2["verdict"] == "CANDIDATE"
    assert rec2["geometry"]["deterministic_gates"]["furniture_overlap"] == "WARN"
    # findings FAIL (pos-degradacao) tambem derruba
    rec3 = vs.build_record(_variant(), run_id="t",
                           gates={"geometry_sanity": "PASS"},
                           png=png, out_root=tmp_path,
                           findings=_v1_findings("FAIL"))
    assert rec3["verdict"] == "FAIL"


def test_sweep_uses_pt_to_m_0_0259():
    # guard textual: o setdefault precede o PRIMEIRO import de projeto no fonte
    src = Path(vs.__file__).read_text(encoding="utf-8")
    set_at = src.index('os.environ.setdefault("PT_TO_M", "0.0259")')
    first_proj = min(src.index("from core import scale"),
                     src.index("from tools.furnish_apartment"))
    assert set_at < first_proj
    # prova em processo LIMPO (sem env): importar o modulo congela 0.0259
    env = dict(os.environ)
    env.pop("PT_TO_M", None)
    out = subprocess.run(
        [sys.executable, "-c",
         "import tools.variant_sweep; from core import scale; print(scale.PT_TO_M)"],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "0.0259"


# --- adapter de visao: dois modos honestos ---------------------------------------


def test_sidecar_findings_are_loaded_with_fixture_injected(tmp_path, monkeypatch):
    _no_http(monkeypatch)
    png = _png(tmp_path / "v1")
    vf = _v1_findings("WARN")
    png.with_name("visual_findings.json").write_text(
        json.dumps(vf), encoding="utf-8")
    got = vs._collect_findings(png, plant="planta_74", provider=None)
    assert got is not None
    assert got["top_level_verdict"] == "WARN"
    assert got["fixture"] == "planta_74"   # required no schema v1, injetado
    assert got["attempt"] == "variant"


def test_vision_adapter_uses_provider_and_degrades_unproven_fail(tmp_path,
                                                                 monkeypatch):
    _no_http(monkeypatch)  # provider fake: zero HTTP real neste caminho
    png = _png(tmp_path / "v1")
    findings = [{"id": "vf1", "severity": "FAIL", "axis": "global_visual",
                 "type": "other", "location": "sala",
                 "evidence_image": "iso.png", "evidence": "gap"}]
    p = _FakeProvider(findings=_v1_findings("FAIL", findings))
    # sem discrimination_report -> FAIL degrada pra WARN com nota de auditoria
    got = vs._collect_findings(png, plant="planta_74", provider=p,
                               discrimination=lambda: None)
    assert p.calls == 1
    assert got["top_level_verdict"] == "WARN"
    assert "degraded to WARN" in got.get("promotion_note", "")
    assert got["findings"][0]["severity"] == "WARN"
    assert got["discriminated"] is False
    assert got["fixture"] == "planta_74" and got["attempt"] == "variant"
    # com prova DISCRIMINATED o FAIL fica de pe
    p2 = _FakeProvider(findings=_v1_findings("FAIL", [dict(findings[0])]))
    got2 = vs._collect_findings(
        png, plant="planta_74", provider=p2,
        discrimination=lambda: {"result": "DISCRIMINATED",
                                "backend": "claude_bridge_vision"})
    assert got2["top_level_verdict"] == "FAIL"
    assert got2["discriminated"] is True


def test_vision_adapter_unavailable_yields_none_not_fabrication(tmp_path,
                                                                monkeypatch):
    _no_http(monkeypatch)
    png = _png(tmp_path / "v1")
    # probe falhou -> None sem call
    p_off = _FakeProvider(probe_ok=False)
    assert vs._collect_findings(png, plant="planta_74", provider=p_off) is None
    assert p_off.calls == 0
    # call status != ok -> None (negativo honesto)
    p_unavail = _FakeProvider(status="unavailable", findings=None)
    assert vs._collect_findings(png, plant="planta_74", provider=p_unavail,
                                discrimination=lambda: None) is None


def test_bad_sidecar_counts_as_absent_and_does_not_shadow_provider(tmp_path,
                                                                   monkeypatch):
    # sidecar torn (JSON invalido) e sidecar sem schema_version v1: AUSENTE —
    # nunca fabrica achado dele, e o provider vivo E' consultado (nao sombreado)
    _no_http(monkeypatch)
    for bad in ('{"torn": ', json.dumps({"foo": 1}), json.dumps([1, 2])):
        d = tmp_path / f"v{hash(bad) & 0xffff}"
        png = _png(d)
        png.with_name("visual_findings.json").write_text(bad, encoding="utf-8")
        # sem provider -> None (PENDING_VISION honesto, nunca CANDIDATE de lixo)
        assert vs._collect_findings(png, plant="planta_74", provider=None) is None
        p = _FakeProvider(findings=_v1_findings("PASS"))
        got = vs._collect_findings(png, plant="planta_74", provider=p,
                                   discrimination=lambda: None)
        assert p.calls == 1  # provider consultado apesar do sidecar quebrado
        assert got is not None and got["top_level_verdict"] == "PASS"


def test_machine_score_never_fabricated_from_unknown_verdict():
    # findings nao-conformes (sem top_level_verdict valido) -> nota None,
    # nunca o default 0.6 fabricado de um verdict que nao existe
    assert vs._machine_score({}, {"foo": 1}) is None
    assert vs._machine_score({}, {"top_level_verdict": "MAYBE"}) is None
    assert vs._machine_score({}, _v1_findings("WARN")) == 0.6


# --- corpus append-only idempotente + contact sheet -------------------------------


def _fake_run_one(tmp_root, findings=None):
    def run_one(v, out_dir, **kw):
        png = _png(Path(out_dir))
        return vs.build_record(v, run_id=Path(tmp_root).name,
                               gates={"geometry_sanity": "PASS",
                                      "furniture_overlap": "PASS"},
                               png=png, out_root=tmp_root, findings=findings)
    return run_one


def test_corpus_jsonl_is_append_only_idempotent(tmp_path, validator):
    out = tmp_path / "run1"
    recs = vs.sweep(4, out, run_one=_fake_run_one(out), log=lambda m: None)
    corpus = out / "corpus.jsonl"
    lines1 = corpus.read_text("utf-8").splitlines()
    assert len(recs) == 4 and len(lines1) == 4
    for ln in lines1:
        validator.validate(json.loads(ln))
    # segunda passada: celulas ja vistas sao puladas, arquivo NUNCA reescrito
    vs.sweep(4, out, run_one=_fake_run_one(out), log=lambda m: None)
    lines2 = corpus.read_text("utf-8").splitlines()
    assert lines2 == lines1
    ids = [json.loads(ln)["variant_id"] for ln in lines2]
    assert len(ids) == len(set(ids))
    assert (out / "contact_sheet.png").is_file()
    # o corpus so e' tocado via append_jsonl (nunca write_text/rewrite)
    src = inspect.getsource(vs)
    assert "append_jsonl(corpus" in src
    assert "corpus.write_text" not in src


def test_vision_upgrade_appends_superseding_record_never_rewrites(tmp_path):
    out = tmp_path / "run1"
    vs.sweep(1, out, run_one=_fake_run_one(out), log=lambda m: None)  # PENDING
    corpus = out / "corpus.jsonl"
    assert len(corpus.read_text("utf-8").splitlines()) == 1
    # provider presente + registro PENDING_VISION -> re-roda e APPENDA
    upgraded = _fake_run_one(out, findings=_v1_findings("PASS"))
    recs = vs.sweep(1, out, run_one=upgraded, provider=_FakeProvider(),
                    log=lambda m: None)
    lines = corpus.read_text("utf-8").splitlines()
    assert len(lines) == 2  # append-only: superseding, nao rewrite
    assert recs[0]["verdict"] == "CANDIDATE"
    last = json.loads(lines[-1])
    assert last["verdict"] == "CANDIDATE"
    # last-wins na leitura da ponte RAG
    rows = ctr.export_reference_rows(corpus)
    assert len(rows) == 1
    assert rows[0][0]["notes"] == "CANDIDATE"


def test_failed_vision_upgrade_is_idempotent_no_duplicate_append(tmp_path):
    # rerun com --ask-vision e bridge FORA: o upgrade re-roda a celula mas o
    # registro volta PENDING_VISION — appendar duplicaria sem superseder nada.
    # N passadas = corpus continua com 1 linha (idempotente)
    out = tmp_path / "run1"
    vs.sweep(1, out, run_one=_fake_run_one(out), log=lambda m: None)  # PENDING
    corpus = out / "corpus.jsonl"
    assert len(corpus.read_text("utf-8").splitlines()) == 1
    still_pending = _fake_run_one(out)  # findings=None -> PENDING_VISION de novo
    for _ in range(3):
        recs = vs.sweep(1, out, run_one=still_pending,
                        provider=_FakeProvider(probe_ok=False),
                        log=lambda m: None)
        assert recs[0]["verdict"] == "PENDING_VISION"
    lines = corpus.read_text("utf-8").splitlines()
    assert len(lines) == 1  # nada appendado: o corpus nao cresce por rerun offline


# --- integracao: sweep real SU-free em subprocess ---------------------------------


def test_su_free_sweep_smoke_4_variants(tmp_path, validator):
    """--n 4 --dry-run na planta_74 REAL (consensus read-only): 4 registros
    validos, todos PENDING_VISION honestos, contact sheet, escala 0.0259.
    Subprocess = interprete limpo (o setdefault do modulo e' quem congela a
    escala; em-processo a ordem de imports da suite mandaria)."""
    out = tmp_path / "smoke"
    env = dict(os.environ)
    env.pop("PT_TO_M", None)
    r = subprocess.run(
        [sys.executable, "-m", "tools.variant_sweep", "--n", "4",
         "--out", str(out), "--dry-run", "--render", "su-free"],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=420)
    assert r.returncode == 0, r.stderr[-2000:]
    rows = [json.loads(ln) for ln in
            (out / "corpus.jsonl").read_text("utf-8").splitlines()]
    assert len(rows) == 4
    for row in rows:
        validator.validate(row)
        assert row["verdict"] == "PENDING_VISION"
        assert row["visual_findings"] is None
        assert row["human_verdict"] is None
        assert row["params"]["pt_to_m"] == "0.0259"
        assert row["render_refs"]["renderer"] == "su-free"
        assert (out / row["render_refs"]["iso"]).is_file()
    assert (out / "contact_sheet.png").is_file()


def test_force_rerender_supersedes_existing(tmp_path, monkeypatch):
    """Idempotência por presença pula célula já vista; --force-rerender re-roda e
    APPENDA supersede (caso real: o renderer ganhou o shell arquitetônico e o
    corpus precisa do render novo sob os MESMOS variant_ids)."""
    import tools.variant_sweep as vs

    calls = []

    def fake_run(v, out_dir, **kw):
        calls.append(v.variant_id)
        return {"schema": "judged_variant/1.0.0", "variant_id": v.variant_id,
                "verdict": "PENDING_VISION", "run_id": "t", "plant": v.plant,
                "created_at": "2026-07-12T00:00:00Z", "human_verdict": None,
                "render_refs": {"iso": "x/iso.png", "sha256": f"sha-{len(calls)}",
                                "renderer": "su-free"}}

    out = tmp_path / "sweep"
    vs.sweep(1, out, plant="planta_74", run_one=fake_run, log=lambda *a: None)
    assert len(calls) == 1
    vs.sweep(1, out, plant="planta_74", run_one=fake_run, log=lambda *a: None)
    assert len(calls) == 1                                    # idempotente: skip
    vs.sweep(1, out, plant="planta_74", run_one=fake_run,
             force_rerender=True, log=lambda *a: None)
    assert len(calls) == 2                                    # force re-rodou
    from tools.jsonl_io import read_jsonl
    recs = read_jsonl(out / "corpus.jsonl")
    assert len(recs) == 2                                     # supersede appendado
    assert recs[-1]["render_refs"]["sha256"] == "sha-2"       # last-wins = render novo
