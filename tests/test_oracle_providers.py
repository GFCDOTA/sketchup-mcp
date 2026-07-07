"""FP-030 — pluggable oracle providers contract tests.

Cover:
- OracleRequest validation (image_paths must exist, prompt non-empty)
- write_oracle_request_package writes the documented structure
- NoneProvider returns deterministic "unavailable"
- ChatGPTBridgeImageProvider probes correctly when bridge is offline
- ChatGPTBridgeImageProvider returns "unavailable" + writes package when
  bridge is offline
- FutureVisionAPIProvider returns "not_implemented" + writes package
- _normalize_to_visual_findings accepts valid payload, rejects malformed
- registry exposes all 3 providers
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.oracle_providers import (
    ChatGPTBridgeImageProvider, FutureVisionAPIProvider,
    NoneProvider, OllamaVisionProvider,
    OracleRequest, OracleResponse,
    VISUAL_FINDINGS_SCHEMA_VERSION,
    _normalize_to_visual_findings,
    available_provider_names, get_provider,
    write_oracle_request_package,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_request(tmp_path: Path) -> OracleRequest:
    img_a = tmp_path / "model_top.png"
    img_b = tmp_path / "model_iso.png"
    img_a.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    img_b.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    return OracleRequest(
        prompt="Review the images.",
        image_paths=[img_a, img_b],
        context={"gates_self_check": {"plan_shell_group_exists": True}},
        expected_schema={"schema_version": VISUAL_FINDINGS_SCHEMA_VERSION},
    )


# ---- registry --------------------------------------------------------


def test_registry_exposes_all_providers():
    names = available_provider_names()
    assert names == [
        "chatgpt_bridge_image",
        "claude_bridge_vision",
        "future_vision_api",
        "none",
        "ollama_vision",
    ]


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("does_not_exist")


def test_get_provider_returns_instance():
    p = get_provider("chatgpt_bridge_image")
    assert isinstance(p, ChatGPTBridgeImageProvider)
    p = get_provider("none")
    assert isinstance(p, NoneProvider)
    p = get_provider("future_vision_api")
    assert isinstance(p, FutureVisionAPIProvider)
    p = get_provider("ollama_vision")
    assert isinstance(p, OllamaVisionProvider)


# ---- OracleRequest validation ----------------------------------------


def test_request_rejects_empty_prompt(tmp_path: Path):
    img = tmp_path / "x.png"
    img.write_bytes(b"x")
    req = OracleRequest(prompt="", image_paths=[img], context={})
    with pytest.raises(ValueError):
        req.validate()


def test_request_rejects_no_images(tmp_path: Path):
    req = OracleRequest(prompt="hi", image_paths=[], context={})
    with pytest.raises(ValueError):
        req.validate()


def test_request_rejects_missing_image(tmp_path: Path):
    req = OracleRequest(
        prompt="hi",
        image_paths=[tmp_path / "missing.png"],
        context={},
    )
    with pytest.raises(FileNotFoundError):
        req.validate()


def test_request_accepts_valid_payload(tmp_path: Path):
    req = _make_request(tmp_path)
    req.validate()  # should not raise


# ---- package writer --------------------------------------------------


def test_package_writer_creates_documented_structure(tmp_path: Path):
    req = _make_request(tmp_path)
    pkg = write_oracle_request_package(
        tmp_path / "out", req, status="incompatible", reason="text-only",
    )
    assert pkg.name == "oracle_request_package"
    assert (pkg / "prompt.md").exists()
    assert (pkg / "context.json").exists()
    assert (pkg / "expected_schema.json").exists()
    assert (pkg / "images" / "model_top.png").exists()
    assert (pkg / "images" / "model_iso.png").exists()
    assert (pkg / "README.md").exists()

    # README mentions status + how-to
    readme = (pkg / "README.md").read_text(encoding="utf-8")
    assert "incompatible" in readme
    assert "text-only" in readme
    assert "ChatGPT" in readme


def test_package_writer_skips_expected_schema_when_none(tmp_path: Path):
    img = tmp_path / "i.png"; img.write_bytes(b"x")
    req = OracleRequest(prompt="p", image_paths=[img], context={})
    pkg = write_oracle_request_package(
        tmp_path / "out", req, status="unavailable", reason="bridge offline",
    )
    assert not (pkg / "expected_schema.json").exists()


# ---- NoneProvider ----------------------------------------------------


def test_none_provider_probe():
    p = NoneProvider()
    ok, detail = p.probe()
    assert ok is False
    assert "none" in detail.lower()


def test_none_provider_call_returns_unavailable(tmp_path: Path):
    p = NoneProvider()
    req = _make_request(tmp_path)
    resp = p.call(req, out_dir=tmp_path / "out")
    assert resp.status == "unavailable"
    assert resp.provider == "none"
    # NoneProvider does NOT write a package — it's an explicit no-op
    assert resp.package_dir is None


# ---- ChatGPTBridgeImageProvider --------------------------------------


def test_chatgpt_bridge_probe_returns_false_when_unreachable():
    # Use a port guaranteed to be closed
    p = ChatGPTBridgeImageProvider(url="http://127.0.0.1:1")
    ok, detail = p.probe()
    assert ok is False
    assert "unreachable" in detail.lower() or "refused" in detail.lower() or "127.0.0.1:1" in detail


def test_chatgpt_bridge_call_writes_package_on_unavailable(tmp_path: Path):
    p = ChatGPTBridgeImageProvider(url="http://127.0.0.1:1")
    req = _make_request(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    resp = p.call(req, out_dir=out_dir)
    assert resp.status == "unavailable"
    assert resp.package_dir is not None
    assert resp.package_dir.exists()
    assert (resp.package_dir / "prompt.md").exists()
    assert (resp.package_dir / "images" / "model_top.png").exists()


# ---- FutureVisionAPIProvider -----------------------------------------


def test_future_vision_api_probe_returns_false():
    p = FutureVisionAPIProvider()
    ok, detail = p.probe()
    assert ok is False
    assert "not implemented" in detail.lower()


def test_future_vision_api_call_returns_not_implemented(tmp_path: Path):
    p = FutureVisionAPIProvider()
    req = _make_request(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    resp = p.call(req, out_dir=out_dir)
    assert resp.status == "not_implemented"
    assert resp.package_dir is not None
    assert resp.package_dir.exists()


# ---- response normalization ------------------------------------------


def _valid_oracle_payload() -> dict:
    return {
        "top_level_verdict": "PASS",
        "confidence": "high",
        "axes": {
            "wall_fidelity":   {"verdict": "PASS", "evidence": "ok"},
            "door_fidelity":   {"verdict": "PASS", "evidence": "ok"},
            "window_fidelity": {"verdict": "PASS", "evidence": "ok"},
            "room_fidelity":   {"verdict": "WARN", "evidence": "open plan"},
            "scale_rotation":  {"verdict": "PASS", "evidence": "ok"},
            "global_visual":   {"verdict": "PASS", "evidence": "ok"},
        },
        "findings": [],
    }


def test_normalize_accepts_valid_payload():
    out = _normalize_to_visual_findings(_valid_oracle_payload())
    assert out is not None
    assert out["schema_version"] == "visual_findings.v1"
    assert out["top_level_verdict"] == "PASS"
    assert set(out["axes"].keys()) == {
        "wall_fidelity", "door_fidelity", "window_fidelity",
        "room_fidelity", "scale_rotation", "global_visual",
    }
    assert out["source"] == "oracle_bridge"


def test_normalize_rejects_missing_top_level_verdict():
    payload = _valid_oracle_payload()
    del payload["top_level_verdict"]
    assert _normalize_to_visual_findings(payload) is None


def test_normalize_rejects_unknown_verdict():
    payload = _valid_oracle_payload()
    payload["top_level_verdict"] = "MAYBE"
    assert _normalize_to_visual_findings(payload) is None


def test_normalize_rejects_missing_axis():
    payload = _valid_oracle_payload()
    del payload["axes"]["wall_fidelity"]
    assert _normalize_to_visual_findings(payload) is None


def test_normalize_rejects_axis_with_unknown_verdict():
    payload = _valid_oracle_payload()
    payload["axes"]["wall_fidelity"]["verdict"] = "BLOCKED"
    assert _normalize_to_visual_findings(payload) is None


def test_normalize_rejects_non_dict_input():
    assert _normalize_to_visual_findings("not a dict") is None  # type: ignore[arg-type]
    assert _normalize_to_visual_findings(None) is None  # type: ignore[arg-type]
    assert _normalize_to_visual_findings([]) is None  # type: ignore[arg-type]


# ---- OllamaVisionProvider --------------------------------------------


def test_ollama_provider_probe_returns_false_when_unreachable():
    p = OllamaVisionProvider(url="http://127.0.0.1:1")
    ok, detail = p.probe()
    assert ok is False
    assert "unreachable" in detail.lower() or "127.0.0.1:1" in detail


def test_ollama_provider_call_writes_package_on_unavailable(tmp_path: Path):
    p = OllamaVisionProvider(url="http://127.0.0.1:1")
    req = _make_request(tmp_path)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    resp = p.call(req, out_dir=out_dir)
    assert resp.status == "unavailable"
    assert resp.package_dir is not None
    assert resp.package_dir.exists()


def test_ollama_extract_first_json_object_balanced():
    p = OllamaVisionProvider()
    text = 'Here is the result: {"a": 1, "b": {"c": [2,3]}} and some prose'
    out = p._extract_first_json_object(text)
    assert out == {"a": 1, "b": {"c": [2, 3]}}


def test_ollama_extract_first_json_object_handles_string_with_braces():
    p = OllamaVisionProvider()
    text = '{"verdict": "PASS", "msg": "an open { brace inside string"}'
    out = p._extract_first_json_object(text)
    assert out == {"verdict": "PASS", "msg": "an open { brace inside string"}


def test_ollama_extract_first_json_object_none_when_absent():
    p = OllamaVisionProvider()
    assert p._extract_first_json_object("just prose, no braces") is None


def test_ollama_extract_first_json_object_none_on_unbalanced():
    p = OllamaVisionProvider()
    assert p._extract_first_json_object('{"a": 1, "b": {') is None


def test_normalize_carries_findings_through():
    payload = _valid_oracle_payload()
    payload["findings"] = [{
        "id": "vf_001", "severity": "FAIL", "axis": "window_fidelity",
        "type": "orphan_glass_panel", "location": "NW corner",
        "evidence_image": "model_iso.png", "evidence": "panel detached"
    }]
    out = _normalize_to_visual_findings(payload)
    assert out is not None
    assert len(out["findings"]) == 1
    assert out["findings"][0]["type"] == "orphan_glass_panel"


# ---- painel de 3 juizes: eixo material_light + design_patterns_observed ----
# (extensoes ADITIVAS do FP-035-prep; retrocompat = os testes acima continuam
# passando sem tocar nenhum deles)


def test_normalize_without_material_light_still_works_backcompat():
    # payload de ANTES do painel (sem material_light nem design_patterns) tem
    # que continuar validando identico — extensao e' aditiva, nunca exigida
    out = _normalize_to_visual_findings(_valid_oracle_payload())
    assert out is not None
    assert "material_light" not in out["axes"]
    assert "design_patterns_observed" not in out


def test_normalize_propagates_material_light_axis_when_present():
    payload = _valid_oracle_payload()
    payload["axes"]["material_light"] = {"verdict": "WARN", "evidence": "flat shading"}
    out = _normalize_to_visual_findings(payload)
    assert out is not None
    assert out["axes"]["material_light"] == {"verdict": "WARN", "evidence": "flat shading"}
    # os 6 eixos base continuam intactos (aditivo, nao substitutivo)
    assert set(out["axes"].keys()) == {
        "wall_fidelity", "door_fidelity", "window_fidelity",
        "room_fidelity", "scale_rotation", "global_visual", "material_light",
    }


def test_normalize_ignores_material_light_with_bad_verdict_silently():
    # eixo opcional malformado NAO derruba o payload inteiro (so ele e' descartado)
    payload = _valid_oracle_payload()
    payload["axes"]["material_light"] = {"verdict": "MAYBE", "evidence": "?"}
    out = _normalize_to_visual_findings(payload)
    assert out is not None
    assert "material_light" not in out["axes"]


def test_normalize_propagates_design_patterns_observed():
    payload = _valid_oracle_payload()
    payload["design_patterns_observed"] = [
        {"pattern": "paleta black_wood_gold em cozinha compacta",
         "verdict": "works", "why": "contraste dourado/preto le bem"},
    ]
    out = _normalize_to_visual_findings(payload)
    assert out is not None
    assert out["design_patterns_observed"] == [
        {"pattern": "paleta black_wood_gold em cozinha compacta",
         "verdict": "works", "why": "contraste dourado/preto le bem"},
    ]


def test_normalize_drops_malformed_pattern_entries_never_fabricates():
    payload = _valid_oracle_payload()
    payload["design_patterns_observed"] = [
        {"pattern": "", "verdict": "works", "why": "sem nome"},         # pattern vazio
        {"pattern": "x", "verdict": "maybe", "why": "verdict invalido"},  # verdict fora do enum
        {"pattern": "y", "verdict": "fails"},                            # sem why
        {"pattern": "z", "verdict": "neutral", "why": "ok"},             # valido
    ]
    out = _normalize_to_visual_findings(payload)
    assert out is not None
    assert out["design_patterns_observed"] == [
        {"pattern": "z", "verdict": "neutral", "why": "ok"},
    ]


def test_normalize_empty_design_patterns_list_is_honest_not_populated():
    # lista vazia (juiz nao teve dado suficiente) fica de fora do dict de saida
    # -- nunca fabrica uma entrada so pra "preencher"
    payload = _valid_oracle_payload()
    payload["design_patterns_observed"] = []
    out = _normalize_to_visual_findings(payload)
    assert out is not None
    assert "design_patterns_observed" not in out
