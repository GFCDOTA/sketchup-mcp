"""FP-033 slice 3 — vision_queue_consumer tests (hermetic: HTTP mocked via
urlopen fake or a guaranteed-closed port; all paths in tmp_path; clock injected
via now=; zero pinned-fixture mutation)."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools import oracle_providers as op
from tools import vision_queue_consumer as vqc
from tools.oracle_providers import get_provider

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "correction_finding.schema.json"
NOW = "2026-07-01T12:00:00"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


class _FakeResp(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _health_body(with_vision: bool = True) -> bytes:
    endpoints = ["/", "/ask", "/health"] + (["/ask-vision"] if with_vision else [])
    return json.dumps({"status": "ok", "model": "claude-opus-4-8",
                       "endpoints": sorted(endpoints)}).encode("utf-8")


def _v1_text(findings: list[dict], verdict: str = "FAIL") -> str:
    return json.dumps({
        "schema_version": "visual_findings.v1",
        "top_level_verdict": verdict,
        "confidence": "high",
        "axes": {k: {"verdict": "PASS", "evidence": "seen"}
                 for k in op._AXIS_KEYS},
        "findings": findings,
    })


def _pending(type_="wall_stub", evidence="stub at top"):
    return {"type": type_, "severity": "WARN", "source": "deterministic",
            "evidence": evidence, "route": "NEEDS_VISION",
            "queued_as": "vision_requests"}


def _seed_queue(out: Path, rows: list[dict]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "vision_requests.jsonl").open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _png(tmp_path: Path, name: str = "render.png") -> Path:
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n fake")
    return p


def _no_http(monkeypatch) -> None:
    def boom(*a, **kw):
        raise AssertionError("HTTP must not be reached on this path")
    monkeypatch.setattr(op.urllib.request, "urlopen", boom)


def _bridge_provider(monkeypatch, response_text: str, calls: dict | None = None):
    """Fake urlopen (test_vision_acl pattern) + dead-port double-guard."""
    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if url.endswith("/health"):
            return _FakeResp(_health_body(True))
        if url.endswith("/ask-vision"):
            if calls is not None:
                calls["ask"] = calls.get("ask", 0) + 1
            return _FakeResp(json.dumps(
                {"response": response_text}).encode("utf-8"))
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(op.urllib.request, "urlopen", fake_urlopen)
    p = get_provider("claude_bridge_vision")
    p.url = "http://localhost:9999"   # escaped un-mocked call fails loudly
    return p


# --- no-op / blocked paths ----------------------------------------------------


def test_empty_queue_is_noop(monkeypatch, tmp_path):
    _no_http(monkeypatch)
    res = vqc.drain(tmp_path, fixture="planta_74", now=NOW, log=lambda m: None)
    assert res["status"] == "EMPTY"
    assert (tmp_path / "consumer_result.json").exists()
    assert not (tmp_path / "vision_confirmed.jsonl").exists()
    assert not (tmp_path / "vision_consumed.jsonl").exists()
    monkeypatch.setattr("sys.argv", ["vision_queue_consumer",
                                     "--out", str(tmp_path),
                                     "--fixture", "planta_74"])
    assert vqc.main() == 0


def test_offline_bridge_blocks_honestly(tmp_path):
    _seed_queue(tmp_path, [_pending()])
    img = _png(tmp_path)
    before = (tmp_path / "vision_requests.jsonl").read_bytes()
    p = get_provider("claude_bridge_vision")
    p.url = "http://127.0.0.1:1"      # guaranteed-closed port: honest offline
    res = vqc.drain(tmp_path, fixture="planta_74", provider=p,
                    image_paths=[img], now=NOW, log=lambda m: None)
    assert res["status"] == "BLOCKED_NEEDS_FP032"
    assert (tmp_path / "vision_requests.jsonl").read_bytes() == before
    assert not (tmp_path / "vision_confirmed.jsonl").exists()
    assert res["pending_left"] == 1


def test_incompatible_bridge_blocks(monkeypatch, tmp_path):
    _seed_queue(tmp_path, [_pending()])
    img = _png(tmp_path)

    def fake_urlopen(req, timeout=None):
        assert req.full_url.endswith("/health")
        return _FakeResp(_health_body(with_vision=False))

    monkeypatch.setattr(op.urllib.request, "urlopen", fake_urlopen)
    p = get_provider("claude_bridge_vision")
    p.url = "http://localhost:9999"
    res = vqc.drain(tmp_path, fixture="planta_74", provider=p,
                    image_paths=[img], now=NOW, log=lambda m: None)
    assert res["status"] == "BLOCKED_NEEDS_FP032"
    assert "/ask-vision" in res["detail"]
    assert not (tmp_path / "vision_confirmed.jsonl").exists()


def test_no_render_blocks_before_http(monkeypatch, tmp_path):
    _seed_queue(tmp_path, [_pending()])
    _no_http(monkeypatch)             # not even probe() may fire
    monkeypatch.setattr(vqc, "ARTIFACTS_REVIEW_ROOT", tmp_path / "no_reviews")
    res = vqc.drain(tmp_path, fixture="planta_74", now=NOW, log=lambda m: None)
    assert res["status"] == "BLOCKED_NEEDS_RENDER"
    assert not (tmp_path / "vision_confirmed.jsonl").exists()


# --- drained path: contract + promotion parity ---------------------------------


def test_drain_converts_v1_to_unified_contract(monkeypatch, tmp_path, validator):
    _seed_queue(tmp_path, [_pending()])
    img = _png(tmp_path)
    findings = [
        {"id": "vf_001", "severity": "FAIL", "axis": "wall_fidelity",
         "type": "missing_wall_continuation", "location": "top",
         "evidence_image": "render.png", "evidence": "gap seen"},
        # axis room_fidelity (não-visão): a rota vem do TYPE -> NEEDS_FELIPE;
        # axis global_visual re-rotearia NEEDS_VISION (precedência do router)
        {"id": "vf_002", "severity": "WARN", "axis": "room_fidelity",
         "type": "global_visual_fail", "location": "center",
         "evidence_image": "render.png", "evidence": "muddy"},
    ]
    p = _bridge_provider(monkeypatch, _v1_text(findings))
    res = vqc.drain(
        tmp_path, fixture="planta_74", provider=p, image_paths=[img],
        discrimination=lambda: {"result": "DISCRIMINATED",
                                "backend": "claude_bridge_vision"},
        now=NOW, log=lambda m: None)
    assert res["status"] == "DRAINED"
    assert res["consumed"] == 1 and res["confirmed"] == 2
    rows = [json.loads(ln) for ln in
            (tmp_path / "vision_confirmed.jsonl")
            .read_text("utf-8").splitlines()]
    assert len(rows) == 2
    for r in rows:
        validator.validate(r)
        assert r["source"] == "claude_bridge"
        assert r["source_check"] == "visual_oracle"
        assert r["consumed_at"] == NOW
        assert r["discriminated"] is True
    routed = {r["type"]: r["route"] for r in rows}
    assert routed["global_visual_fail"] == "NEEDS_FELIPE"   # appearance never auto
    # FAIL preserved: backend proven discriminative
    sev = {r["type"]: r["severity"] for r in rows}
    assert sev["missing_wall_continuation"] == "FAIL"


def test_fail_degraded_to_warn_without_discrimination(monkeypatch, tmp_path):
    out = tmp_path / "run"
    _seed_queue(out, [_pending()])
    img = _png(tmp_path)
    findings = [{"id": "vf_001", "severity": "FAIL", "axis": "wall_fidelity",
                 "type": "missing_wall_continuation", "location": "top",
                 "evidence_image": "render.png", "evidence": "gap"}]
    p = _bridge_provider(monkeypatch, _v1_text(findings))
    res = vqc.drain(out, fixture="planta_74", provider=p, image_paths=[img],
                    discrimination=lambda: None, now=NOW, log=lambda m: None)
    assert res["status"] == "DRAINED"
    assert res["discriminated"] is False
    row = json.loads(
        (out / "vision_confirmed.jsonl").read_text("utf-8").splitlines()[0])
    assert row["severity"] == "WARN"                 # FP-032 promotion parity
    assert "degraded to WARN" in row["evidence"]


def test_duplicate_rows_consumed_once_and_not_redrained(monkeypatch, tmp_path):
    _seed_queue(tmp_path, [_pending(), _pending()])   # same signature twice
    img = _png(tmp_path)
    calls: dict = {}
    findings = [{"id": "vf_001", "severity": "WARN", "axis": "global_visual",
                 "type": "wall_stub", "location": "top",
                 "evidence_image": "render.png", "evidence": "stub confirmed"}]
    p = _bridge_provider(monkeypatch, _v1_text(findings, verdict="WARN"),
                         calls=calls)
    res = vqc.drain(tmp_path, fixture="planta_74", provider=p,
                    image_paths=[img], now=NOW, log=lambda m: None)
    assert res["status"] == "DRAINED"
    assert res["consumed"] == 1                       # dedup by signature
    assert calls["ask"] == 1
    res2 = vqc.drain(tmp_path, fixture="planta_74", provider=p,
                     image_paths=[img], now=NOW, log=lambda m: None)
    assert res2["status"] == "EMPTY"                  # consumed set persisted
    assert calls["ask"] == 1                          # no second HTTP call
