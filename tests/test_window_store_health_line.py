"""FP-060 MT-09 (#663): a linha de saude do EventStore no painel Qt (`Details`, window.py) — aparece, sai ESCAPADA, sem credencial, e a cor
muda quando o store nao esta saudavel. GUI offscreen; pulado sem PySide6."""
from __future__ import annotations

from tests.test_agent_bar import gui, snap  # noqa: F401  (fixture e helpers reutilizados)
from tests.test_models_store_line import OK

GREY, RED = "#6d6d75", "#ff9a9b"


def _show(bar, app, s):
    bar.on_snapshot(s)
    app.processEvents()
    return bar.details.health.text()


def test_a_healthy_store_line_is_shown_in_grey(gui):  # noqa: F811
    bar, app, tmp = gui
    s = snap(tmp)
    s.store = OK
    html = _show(bar, app, s)
    assert "EventStore: 2 pendente(s)" in html and f"color:{GREY}" in html


def test_an_unhealthy_store_line_is_shown_in_red(gui):  # noqa: F811
    bar, app, tmp = gui
    s = snap(tmp)
    s.store = {"state": "ausente", "error": "sem event_store.db"}
    html = _show(bar, app, s)
    assert "NAO e saudavel" in html and f"color:{RED}" in html


def test_the_store_line_is_html_escaped_and_carries_no_credential(gui):  # noqa: F811
    bar, app, tmp = gui
    s = snap(tmp)
    s.store = {**OK, "last_error": {"key": "k", "error": "<b>gh</b> falhou: Authorization: OAuth abcdefghijklmnop"}}
    html = _show(bar, app, s)
    assert "abcdefghijklmnop" not in html and "<b>gh</b>" not in html and "&lt;b&gt;gh&lt;/b&gt;" in html
