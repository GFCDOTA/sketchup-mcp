"""FP-032 — ACL de Visão contract/unit/guard tests.

Covers the three slices that make the visual ACL trustworthy:

- schema hardening (`visual_findings.v1` + optional source/confidence/
  discriminated) with back-compat proven,
- the `ClaudeBridgeVisionProvider` normalization + honest-failure contract
  (mocked HTTP — no network, no `claude -p`),
- the runner promotion gate (`promote_oracle_verdict` / `load_latest_
  discrimination`): only a PROVEN-discriminative backend can cast a hard FAIL,
- a guard that no machine path emits an appearance verdict (IMPROVED/SAME/WORSE).

Companion: `tools/oracle_providers.py`, `tools/run_skp_visual_review.py`,
`tools/negative_dogfood.py`, `schemas/visual_findings.schema.json`.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from tools import oracle_providers as op
from tools import run_skp_visual_review as rr
from tools.oracle_providers import OracleRequest, get_provider

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "visual_findings.schema.json"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _canonical_v1() -> dict:
    """A v1 findings blob as written BEFORE FP-032 (no honesty fields)."""
    return {
        "schema_version": "visual_findings.v1",
        "fixture": "planta_74",
        "attempt": "final",
        "top_level_verdict": "WARN",
        "axes": {
            "wall_fidelity": {"verdict": "PASS", "evidence": "ok"},
            "global_visual": {"verdict": "WARN", "evidence": "needs eye"},
        },
        "findings": [
            {
                "id": "vf_001",
                "severity": "WARN",
                "axis": "global_visual",
                "type": "global_visual_fail",
                "location": "top/center",
                "evidence_image": "model_top.png",
                "evidence": "possible gap",
            }
        ],
    }


# --- schema hardening -------------------------------------------------


def test_schema_v1_backcompat(validator):
    """A v1 blob written before FP-032 (no source/confidence/discriminated)
    still validates against the hardened schema."""
    blob = _canonical_v1()
    assert "source" not in blob["findings"][0]
    assert validator.iter_errors(blob) == [] or list(validator.iter_errors(blob)) == []
    validator.validate(blob)  # raises on failure


def test_schema_accepts_new_fields(validator):
    """`source`, `confidence`, `discriminated` accepted + typed at both the
    top level and inside a finding."""
    blob = _canonical_v1()
    blob["source"] = "claude_bridge"
    blob["confidence"] = "high"
    blob["discriminated"] = True
    blob["findings"][0]["source"] = "claude_bridge"
    blob["findings"][0]["confidence"] = "medium"
    blob["findings"][0]["discriminated"] = None  # null = not measured
    validator.validate(blob)


def test_schema_legacy_source_value_still_valid(validator):
    """The normalizer's legacy default `oracle_bridge` stays in the enum so
    findings written before the source split keep validating."""
    blob = _canonical_v1()
    blob["source"] = "oracle_bridge"
    validator.validate(blob)


def test_schema_rejects_unknown_source(validator):
    """The `source` enum is enforced when present (typed, not free-form)."""
    blob = _canonical_v1()
    blob["findings"][0]["source"] = "totally_made_up_backend"
    errs = list(validator.iter_errors(blob))
    assert errs, "unknown source value should fail validation"


def test_schema_rejects_unknown_confidence(validator):
    blob = _canonical_v1()
    blob["confidence"] = "very-sure"
    assert list(validator.iter_errors(blob)), "confidence enum must be enforced"


def test_normalizer_output_validates_findings_shape(validator):
    """`_normalize_to_visual_findings` output, once given fixture/attempt, is a
    valid v1 (guards the provider's own contract)."""
    raw = {
        "top_level_verdict": "FAIL",
        "confidence": "high",
        "axes": {k: {"verdict": "PASS", "evidence": ""} for k in op._AXIS_KEYS},
        "findings": [{
            "id": "vf_x", "severity": "FAIL", "axis": "wall_fidelity",
            "type": "missing_wall_continuation", "location": "top",
            "evidence_image": "model_top.png", "evidence": "gap",
        }],
    }
    norm = op._normalize_to_visual_findings(raw)
    assert norm is not None
    norm = {**norm, "fixture": "planta_74", "attempt": "final"}
    validator.validate(norm)


# --- ClaudeBridgeVisionProvider (mocked HTTP) -------------------------


class _FakeResp(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _health_body(with_vision: bool) -> bytes:
    endpoints = ["/", "/ask", "/health"]
    if with_vision:
        endpoints.append("/ask-vision")
    return json.dumps({
        "status": "ok", "oracle": "claude", "model": "claude-opus-4-8",
        "endpoints": sorted(endpoints),
    }).encode("utf-8")


def _valid_v1_response_text() -> str:
    obj = {
        "schema_version": "visual_findings.v1",
        "top_level_verdict": "FAIL",
        "confidence": "high",
        "axes": {k: {"verdict": ("FAIL" if k == "wall_fidelity" else "PASS"),
                     "evidence": "seen"} for k in op._AXIS_KEYS},
        "findings": [{
            "id": "vf_001", "severity": "FAIL", "axis": "wall_fidelity",
            "type": "missing_wall_continuation", "location": "top/center",
            "evidence_image": "corrupted_top.png", "evidence": "wall gap",
        }],
    }
    # wrap in prose to prove the extractor peels it out
    return "Here is my review:\n```json\n" + json.dumps(obj) + "\n```\n"


def _make_provider_and_req(tmp_path: Path):
    img = tmp_path / "top.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n fake")
    p = get_provider("claude_bridge_vision")
    p.url = "http://localhost:9999"
    req = OracleRequest(
        prompt="review", image_paths=[img],
        context={"gates_self_check": {"a": True},
                 "shell_stats_from_python": {"input_walls": 10}},
        expected_schema={"schema_version": "visual_findings.v1"},
    )
    return p, req


def test_claude_bridge_vision_normalizes(monkeypatch, tmp_path):
    """Bridge advertises /ask-vision and returns a v1 (prose-wrapped) response
    -> status ok, normalized, source stamped claude_bridge."""
    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if url.endswith("/health"):
            return _FakeResp(_health_body(with_vision=True))
        if url.endswith("/ask-vision"):
            return _FakeResp(json.dumps(
                {"response": _valid_v1_response_text()}).encode("utf-8"))
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(op.urllib.request, "urlopen", fake_urlopen)
    p, req = _make_provider_and_req(tmp_path)
    resp = p.call(req, out_dir=tmp_path / "out")
    assert resp.status == "ok", resp.detail
    assert resp.normalized_findings is not None
    assert resp.normalized_findings["source"] == "claude_bridge"
    assert resp.normalized_findings["top_level_verdict"] == "FAIL"
    assert resp.package_dir is None


def test_claude_bridge_vision_incompatible_when_no_route(monkeypatch, tmp_path):
    """Bridge up but text-only (no /ask-vision) -> incompatible + package,
    never fabricates a verdict. This is the live :8765 state pre-deploy."""
    def fake_urlopen(req, timeout=None):
        assert req.full_url.endswith("/health")
        return _FakeResp(_health_body(with_vision=False))

    monkeypatch.setattr(op.urllib.request, "urlopen", fake_urlopen)
    p, req = _make_provider_and_req(tmp_path)
    resp = p.call(req, out_dir=tmp_path / "out")
    assert resp.status == "incompatible"
    assert resp.normalized_findings is None
    assert resp.package_dir is not None and resp.package_dir.exists()


def test_claude_bridge_vision_unavailable_when_unreachable(monkeypatch, tmp_path):
    def fake_urlopen(req, timeout=None):
        raise op.urllib.error.URLError("connection refused")

    monkeypatch.setattr(op.urllib.request, "urlopen", fake_urlopen)
    p, req = _make_provider_and_req(tmp_path)
    resp = p.call(req, out_dir=tmp_path / "out")
    assert resp.status == "unavailable"
    assert resp.package_dir is not None and resp.package_dir.exists()


def test_claude_bridge_vision_rejects_non_v1_no_json(monkeypatch, tmp_path):
    """claude answered prose with no JSON -> invalid_response, NOT fabricated."""
    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/health"):
            return _FakeResp(_health_body(with_vision=True))
        return _FakeResp(json.dumps(
            {"response": "Looks fine to me, no defects."}).encode("utf-8"))

    monkeypatch.setattr(op.urllib.request, "urlopen", fake_urlopen)
    p, req = _make_provider_and_req(tmp_path)
    resp = p.call(req, out_dir=tmp_path / "out")
    assert resp.status == "invalid_response"
    assert resp.normalized_findings is None
    assert resp.package_dir is not None and resp.package_dir.exists()


def test_claude_bridge_vision_rejects_json_that_isnt_v1(monkeypatch, tmp_path):
    """claude answered JSON but not visual_findings.v1 -> invalid_response."""
    def fake_urlopen(req, timeout=None):
        if req.full_url.endswith("/health"):
            return _FakeResp(_health_body(with_vision=True))
        return _FakeResp(json.dumps(
            {"response": '{"verdict": "great", "notes": "no schema here"}'}
        ).encode("utf-8"))

    monkeypatch.setattr(op.urllib.request, "urlopen", fake_urlopen)
    p, req = _make_provider_and_req(tmp_path)
    resp = p.call(req, out_dir=tmp_path / "out")
    assert resp.status == "invalid_response"
    assert resp.normalized_findings is None


# --- runner promotion gate -------------------------------------------


def test_promotion_degrades_fail_when_not_discriminated():
    v, note = rr.promote_oracle_verdict("FAIL", discriminated=False)
    assert v == "WARN"
    assert "FP-032" in note


def test_promotion_keeps_fail_when_discriminated():
    v, note = rr.promote_oracle_verdict("FAIL", discriminated=True)
    assert v == "FAIL"
    assert note == ""


@pytest.mark.parametrize("verdict", ["PASS", "WARN"])
def test_promotion_never_escalates(verdict):
    """PASS/WARN pass through unchanged regardless of discrimination proof."""
    for disc in (True, False):
        v, note = rr.promote_oracle_verdict(verdict, discriminated=disc)
        assert v == verdict
        assert note == ""


def _write_report(path: Path, backend: str | None, result: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "negative_dogfood.v2", "fixture": "planta_74",
           "result": result}
    if backend is not None:
        doc["backend"] = backend
    path.write_text(json.dumps(doc), encoding="utf-8")


def test_load_latest_discrimination_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(rr, "REPO_ROOT", tmp_path)
    assert rr.load_latest_discrimination("planta_74", "claude_bridge_vision") is None


def test_load_latest_discrimination_matches_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(rr, "REPO_ROOT", tmp_path)
    base = tmp_path / "artifacts" / "review" / "planta_74"
    _write_report(base / "run_a" / "discrimination_report.json",
                  "claude_bridge_vision", "DISCRIMINATED")
    _write_report(base / "run_b" / "discrimination_report.json",
                  "ollama_vision", "NOT_DISCRIMINATED")
    got = rr.load_latest_discrimination("planta_74", "claude_bridge_vision")
    assert got is not None and got["result"] == "DISCRIMINATED"
    # backend filter really filters
    other = rr.load_latest_discrimination("planta_74", "ollama_vision")
    assert other is not None and other["result"] == "NOT_DISCRIMINATED"


def test_load_latest_discrimination_legacy_report_is_ollama(monkeypatch, tmp_path):
    """A pre-multi-backend report (no `backend` key) counts as ollama_vision."""
    monkeypatch.setattr(rr, "REPO_ROOT", tmp_path)
    base = tmp_path / "artifacts" / "review" / "planta_74"
    _write_report(base / "legacy" / "discrimination_report.json",
                  None, "NOT_DISCRIMINATED")
    got = rr.load_latest_discrimination("planta_74", "ollama_vision")
    assert got is not None and got["result"] == "NOT_DISCRIMINATED"


def test_end_to_end_gate_math_non_proven_backend():
    """A non-proven backend that returns FAIL cannot harden the gate: the
    effective verdict feeding worst_verdict is WARN, not FAIL."""
    oracle_verdict = "FAIL"
    effective, _ = rr.promote_oracle_verdict(oracle_verdict, discriminated=False)
    final = rr.worst_verdict(effective, "PASS", "PASS")
    assert final == "WARN"
    # ...but a PROVEN backend's FAIL does harden it
    effective2, _ = rr.promote_oracle_verdict(oracle_verdict, discriminated=True)
    assert rr.worst_verdict(effective2, "PASS", "PASS") == "FAIL"


# --- guard: no machine appearance verdict ----------------------------


def test_no_machine_appearance_verdict():
    """No FP-032 tool module emits an appearance verdict (IMPROVED/SAME/WORSE)
    as a string literal. That verdict is exclusively Felipe's (chrome-only)."""
    modules = [
        REPO_ROOT / "tools" / "oracle_providers.py",
        REPO_ROOT / "tools" / "negative_dogfood.py",
        REPO_ROOT / "tools" / "run_skp_visual_review.py",
    ]
    pattern = re.compile(r"""['"](IMPROVED|SAME|WORSE)['"]""")
    offenders = []
    for m in modules:
        for i, line in enumerate(m.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{m.name}:{i}: {line.strip()}")
    assert not offenders, "machine must not emit appearance verdicts:\n" + "\n".join(offenders)
