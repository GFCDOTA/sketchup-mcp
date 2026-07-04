"""Painel colaborativo de 3 juizes no /ask-vision (server.py). Hermetico: mocka
ask_claude_vision/ask_claude (nunca dispara `claude -p` real); prova paralelismo,
degradacao honesta (juiz falho -> WARN, nunca fabrica) e o contrato HTTP
inalterado ({"response": "<texto>"})."""
from __future__ import annotations

import json
import threading
import time

import tools.claude_bridge.server as srv


def _vf(verdict="PASS", axes=None, findings=None, patterns=None):
    payload = {
        "schema_version": "visual_findings.v1",
        "top_level_verdict": verdict,
        "confidence": "high",
        "axes": axes or {},
        "findings": findings or [],
    }
    if patterns is not None:
        payload["design_patterns_observed"] = patterns
    return json.dumps(payload)


def test_panel_runs_structure_and_material_in_parallel(monkeypatch):
    # 2 chamadas concorrentes: cada uma dorme e registra o momento de entrada;
    # se rodassem em serie, o segundo "start" so viria depois do sleep do 1o
    starts: list = []
    lock = threading.Lock()

    def fake_ask_vision(prompt, images, tier="deep"):
        with lock:
            starts.append(time.monotonic())
        time.sleep(0.05)
        verdict = "PASS" if "ESTRUTURA" in prompt else "PASS"
        return _vf(verdict)

    monkeypatch.setattr(srv, "ask_claude_vision", fake_ask_vision)
    monkeypatch.setattr(srv, "ask_claude", lambda q, tier="deep": _vf("PASS"))

    srv.ask_claude_vision_panel("contexto extra", ["/tmp/a.png"], tier="deep")
    assert len(starts) == 2
    assert abs(starts[0] - starts[1]) < 0.05   # ambos comecaram quase juntos


def test_panel_returns_synthesis_text_as_response_contract(monkeypatch):
    monkeypatch.setattr(srv, "ask_claude_vision",
                        lambda prompt, images, tier="deep": _vf("PASS"))
    captured = {}

    def fake_ask_claude(q, tier="deep"):
        captured["prompt"] = q
        return _vf("PASS", patterns=[{"pattern": "x", "verdict": "works", "why": "y"}])

    monkeypatch.setattr(srv, "ask_claude", fake_ask_claude)
    out = srv.ask_claude_vision_panel("ctx", ["/tmp/a.png"])
    parsed = json.loads(out)
    assert parsed["top_level_verdict"] == "PASS"
    assert parsed["design_patterns_observed"][0]["pattern"] == "x"
    # sintese recebe os 2 relatorios como TEXTO (nao imagem)
    assert "JUDGE 1 REPORT" in captured["prompt"]
    assert "JUDGE 2 REPORT" in captured["prompt"]


def test_panel_degrades_honestly_when_one_judge_fails(monkeypatch):
    def flaky_ask_vision(prompt, images, tier="deep"):
        if "MATERIAL" in prompt:
            raise RuntimeError("timeout")
        return _vf("PASS")

    monkeypatch.setattr(srv, "ask_claude_vision", flaky_ask_vision)
    captured = {}

    def fake_ask_claude(q, tier="deep"):
        captured["prompt"] = q
        return _vf("WARN")

    monkeypatch.setattr(srv, "ask_claude", fake_ask_claude)
    srv.ask_claude_vision_panel("ctx", ["/tmp/a.png"])
    # o juiz que falhou chega a sintese como MISSING + erro honesto, nunca
    # fabricado como se tivesse respondido PASS
    assert "MISSING" in captured["prompt"]
    assert "RuntimeError" in captured["prompt"]


def test_panel_both_judges_fail_synthesis_still_gets_missing_markers(monkeypatch):
    def always_fail(prompt, images, tier="deep"):
        raise RuntimeError("bridge down")

    monkeypatch.setattr(srv, "ask_claude_vision", always_fail)
    captured = {}

    def fake_ask_claude(q, tier="deep"):
        captured["prompt"] = q
        return _vf("WARN")

    monkeypatch.setattr(srv, "ask_claude", fake_ask_claude)
    srv.ask_claude_vision_panel("ctx", ["/tmp/a.png"])
    assert captured["prompt"].count("MISSING") >= 2


def test_ask_vision_route_uses_panel_not_single_call(monkeypatch):
    # trava a regressao: _ask_vision_route deve chamar o PAINEL, nao mais o
    # ask_claude_vision unico direto
    called = {"panel": False, "single": False}

    def fake_panel(prompt, images, tier="deep"):
        called["panel"] = True
        return _vf("PASS")

    def fake_single(*a, **k):
        called["single"] = True
        return _vf("PASS")

    monkeypatch.setattr(srv, "ask_claude_vision_panel", fake_panel)
    monkeypatch.setattr(srv, "ask_claude_vision", fake_single)
    monkeypatch.setattr(srv, "_audit_append", lambda e: None)

    class FakeReq:
        headers = {"Content-Length": "0"}

        def __init__(self, body):
            self._body = body
            self.rfile = self
            self.sent = None

        def read(self, n):
            return self._body

        def _send(self, code, obj):
            self.sent = (code, obj)

    body = json.dumps({"prompt": "julgue", "images": ["/tmp/a.png"]}).encode()

    class FakeReq2(FakeReq):
        headers = {"Content-Length": str(len(body))}

    req = FakeReq2(body)
    srv._ask_vision_route(req, "/ask-vision")
    assert called["panel"] is True
    assert called["single"] is False
    code, obj = req.sent
    assert code == 200
    assert "response" in obj


def test_synthesis_prompt_never_defaults_missing_axis_to_pass(monkeypatch):
    # regressao literal do texto de instrucao: o prompt de sintese TEM que
    # instruir WARN honesto (nunca PASS) pro eixo de um juiz ausente
    assert "Never claim PASS for an axis nobody evaluated" in srv._SYNTHESIS_JUDGE_PROMPT
