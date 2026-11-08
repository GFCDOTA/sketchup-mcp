"""FP-058: barra de titulo do painel (minimizar/restaurar/fechar), arraste, Esc, limites de tela (multi-monitor, DPI) e rolagem interna.
Geometria pura (sem Qt) + GUI offscreen. Fechar/minimizar o painel NUNCA para listener, Claude ou Codex."""
from __future__ import annotations

import pytest

from tests.test_agent_bar import gui, iso, snap  # noqa: F401  (fixtures/helpers reutilizados)
from tools.orchestration.agent_bar import collectors as col
from tools.orchestration.agent_bar import controls as ctl
from tools.orchestration.agent_bar import geometry as geo

R = geo.Rect


# ------------------------------------------------------------------------------------------------ geometria pura
def test_clamp_keeps_the_window_inside_the_usable_area_with_a_margin():
    area = R(0, 0, 1920, 1040)                                          # 1080p menos barra de tarefas (40 px)
    assert geo.clamp_window(100, 100, 560, 500, area) == (100, 100)
    assert geo.clamp_window(1800, 900, 560, 500, area) == (1920 - 560 - 8, 1040 - 500 - 8)
    assert geo.clamp_window(-300, -50, 560, 500, area) == (8, 8)


def test_clamp_respects_the_taskbar_not_the_full_screen():
    taskbar_bottom = R(0, 0, 2560, 1400)                                # 1440p com barra de 40 px embaixo
    _, y = geo.clamp_window(0, 1390, 560, 300, taskbar_bottom)
    assert y + 300 <= 1400 - 8


def test_clamp_on_a_monitor_with_negative_origin():
    left = R(-1920, 0, 1920, 1040)
    assert geo.clamp_window(-2500, 5, 560, 400, left) == (-1920 + 8, 8)
    assert geo.clamp_window(-10, 5, 560, 400, left)[0] == 0 - 560 - 8


def test_window_larger_than_the_area_anchors_top_left_so_the_titlebar_stays_reachable():
    small = R(0, 0, 500, 400)
    assert geo.clamp_window(300, 300, 560, 700, small) == (8, 8)


def test_pick_screen_by_overlap_nearest_and_empty():
    left, main = R(-1920, 0, 1920, 1040), R(0, 0, 2560, 1400)
    assert geo.pick_screen([left, main], -100, 10, 560, 300) == main          # 460 px no principal x 100 px no da esquerda
    assert geo.pick_screen([left, main], -400, 10, 560, 300) == left
    assert geo.pick_screen([left, main], 5000, 5000, 100, 100) == main           # fora de tudo: o mais proximo
    with pytest.raises(ValueError):
        geo.pick_screen([], 0, 0, 10, 10)


@pytest.mark.parametrize("scale,phys_w,phys_h", [(1.0, 1920, 1080), (1.25, 2560, 1440), (1.5, 3840, 2160), (2.0, 3840, 2160)])
def test_dpi_scales_use_logical_pixels_and_the_panel_always_fits(scale, phys_w, phys_h):
    area = R(0, 0, int(phys_w / scale), int(phys_h / scale) - 40)             # Qt informa o tamanho LOGICO da area util
    h = geo.fit_height(2000, area)                                            # conteudo gigante
    assert h <= area.height - 16
    x, y = geo.clamp_window(area.right, area.bottom, 560, h, area)
    assert x >= area.left and y >= area.top and x + 560 <= area.right and y + h <= area.bottom


def test_fit_height_keeps_small_content_small_and_never_collapses_to_zero():
    assert geo.fit_height(300, R(0, 0, 1920, 1040)) == 300
    assert geo.fit_height(1, R(0, 0, 1920, 1040)) >= 60


def test_place_below_falls_back_above_when_there_is_no_room_and_stays_on_the_bars_monitor():
    left, main = R(-1920, 0, 1920, 1040), R(0, 0, 2560, 1400)
    assert geo.place_below(100, 100, 65, 560, 400, [left, main]) == (100, 171)
    x, y = geo.place_below(100, 1300, 65, 560, 400, [left, main])             # embaixo nao cabe
    assert y + 400 <= 1300 and 0 <= x and y >= 8
    x, y = geo.place_below(-1500, 100, 65, 560, 400, [left, main])             # barra no monitor da esquerda
    assert -1920 <= x and x + 560 <= 0


# ----------------------------------------------------------------------------------------------------- GUI: titulo
def mouse(kind, x, y, buttons=None):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    ev = {"press": QEvent.Type.MouseButtonPress, "move": QEvent.Type.MouseMove, "release": QEvent.Type.MouseButtonRelease}[kind]
    btn = Qt.MouseButton.LeftButton if kind != "move" else Qt.MouseButton.NoButton
    return QMouseEvent(ev, QPointF(5, 5), QPointF(x, y), btn, buttons if buttons is not None else Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)


def test_titlebar_has_title_and_the_three_controls_with_explicit_tooltips(gui):  # noqa: F811
    bar, app, _ = gui
    tb = bar.details.titlebar
    assert tb.title.text() == "Agent Control" and tb.height() == 30
    assert (tb.btn_min.text(), tb.btn_max.text(), tb.btn_close.text()) == ("—", "□", "✕")
    assert "SOMENTE o painel" in tb.btn_close.toolTip() and "nao para o listener" in tb.btn_close.toolTip()


def test_close_x_hides_only_the_panel_and_stops_nothing(gui, monkeypatch):  # noqa: F811
    bar, app, tmp = gui
    for name in ("stop_listener", "restart_listener_dry_run"):
        monkeypatch.setattr(ctl, name, lambda **k: pytest.fail("fechar o painel nao pode controlar o listener"))
    monkeypatch.setattr(bar, "close_app", lambda: pytest.fail("X do painel nao encerra a barra"))
    bar.on_snapshot(snap(tmp))
    bar.toggle_details()
    assert bar.details.isVisible()
    bar.details.titlebar.btn_close.click()
    assert not bar.details.isVisible() and bar.isVisible() is not None
    assert bar.snap is not None                                              # a coleta/estado da barra segue intacto


def test_minimize_collapses_to_the_titlebar_and_restore_brings_the_content_back(gui):  # noqa: F811
    bar, app, tmp = gui
    bar.on_snapshot(snap(tmp))
    bar.toggle_details()
    full = bar.details.height()
    bar.details.titlebar.btn_min.click()
    assert bar.details.collapsed and bar.details.height() == 30 and not bar.details.scroll.isVisibleTo(bar.details)
    assert bar.details.isVisible() and bar.details.titlebar.btn_close.isVisible()      # o X continua acessivel recolhido
    bar.details.titlebar.btn_max.click()
    assert not bar.details.collapsed and bar.details.height() == full
    bar.details.titlebar.btn_min.click()
    bar.details.titlebar.btn_min.click()                                       # recolher de novo e voltar pelo mesmo botao
    assert not bar.details.collapsed


def test_square_button_refits_the_panel_to_its_content(gui):  # noqa: F811
    bar, app, tmp = gui
    bar.on_snapshot(snap(tmp))
    bar.toggle_details()
    bar.details.setFixedHeight(200)
    bar.details.titlebar.btn_max.click()
    assert bar.details.height() > 200


def test_esc_closes_the_panel_but_never_ends_the_bar(gui, monkeypatch):  # noqa: F811
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    bar, app, tmp = gui
    monkeypatch.setattr(bar, "close_app", lambda: pytest.fail("Esc nao encerra a barra"))
    bar.toggle_details()
    QTest.keyClick(bar.details, Qt.Key.Key_Escape)
    assert not bar.details.isVisible()
    bar.toggle_details()
    bar.show()
    QTest.keyClick(bar, Qt.Key.Key_Escape)
    assert not bar.details.isVisible()


def test_close_panel_and_end_bar_are_distinct_actions(gui, monkeypatch):  # noqa: F811
    bar, app, _ = gui
    ended = []
    monkeypatch.setattr(bar, "close_app", lambda: ended.append(1))
    bar.toggle_details()
    bar.close_panel()
    assert not ended and not bar.details.isVisible()
    bar.close_app()
    assert ended == [1]


# ----------------------------------------------------------------------------------------------------- GUI: arraste
def test_dragging_the_titlebar_moves_the_panel_and_makes_it_independent_of_the_bar(gui, monkeypatch):  # noqa: F811
    from PySide6.QtCore import QPoint
    bar, app, tmp = gui
    monkeypatch.setattr("tools.orchestration.agent_bar.window.screen_areas", lambda: [R(0, 0, 3000, 2000)])
    bar.on_snapshot(snap(tmp))
    bar.move(100, 100)
    bar.toggle_details()
    tb = bar.details.titlebar
    start = bar.details.frameGeometry().topLeft()
    tb.mousePressEvent(mouse("press", start.x() + 20, start.y() + 10))
    tb.mouseMoveEvent(mouse("move", start.x() + 520, start.y() + 410))
    tb.mouseReleaseEvent(mouse("release", start.x() + 520, start.y() + 410))
    moved = bar.details.frameGeometry().topLeft()
    assert moved == QPoint(start.x() + 500, start.y() + 400) and bar.details.user_moved
    bar.move(700, 50)                                                          # mover a BARRA nao arrasta mais o painel
    bar._sync_details()
    assert bar.details.frameGeometry().topLeft() == moved
    bar.details.close_panel()
    bar.toggle_details()                                                       # reabrir preserva a posicao escolhida
    assert bar.details.frameGeometry().topLeft() == moved


def test_panel_follows_the_bar_until_the_user_moves_it(gui, monkeypatch):  # noqa: F811
    bar, app, tmp = gui
    monkeypatch.setattr("tools.orchestration.agent_bar.window.screen_areas", lambda: [R(0, 0, 3000, 2000)])
    bar.on_snapshot(snap(tmp))
    bar.move(100, 100)
    bar.toggle_details()
    assert bar.details.frameGeometry().topLeft().y() == 100 + bar.height() + 6
    bar.move(400, 200)
    bar._sync_details()
    assert bar.details.frameGeometry().topLeft().x() == 400 and not bar.details.user_moved


def test_drag_beyond_the_screen_edges_is_clamped_on_every_side_and_multi_monitor(gui, monkeypatch):  # noqa: F811
    bar, app, tmp = gui
    screens = [R(-1920, 0, 1920, 1040), R(0, 0, 2560, 1400)]
    monkeypatch.setattr("tools.orchestration.agent_bar.window.screen_areas", lambda: screens)
    bar.on_snapshot(snap(tmp))
    bar.move(100, 100)
    bar.toggle_details()
    d = bar.details
    tb = d.titlebar
    for gx, gy in [(99999, 99999), (-99999, -99999), (-99999, 99999), (99999, -99999), (-1500, 500)]:
        start = d.frameGeometry().topLeft()
        tb.mousePressEvent(mouse("press", start.x() + 10, start.y() + 10))
        tb.mouseMoveEvent(mouse("move", gx, gy))
        tb.mouseReleaseEvent(mouse("release", gx, gy))
        area = geo.pick_screen(screens, d.x(), d.y(), d.width(), d.height())
        assert area.left <= d.x() and d.x() + d.width() <= area.right and area.top <= d.y() and d.y() + d.height() <= area.bottom, (gx, gy)


def test_opening_near_the_bottom_right_corner_keeps_the_panel_on_screen(gui, monkeypatch):  # noqa: F811
    bar, app, tmp = gui
    area = R(0, 0, 1280, 720)
    monkeypatch.setattr("tools.orchestration.agent_bar.window.screen_areas", lambda: [area])
    bar.on_snapshot(snap(tmp))
    bar.move(1280 - 550, 720 - 65)
    bar.toggle_details()
    d = bar.details
    assert d.x() + d.width() <= area.right and d.y() + d.height() <= area.bottom and d.y() >= area.top and d.x() >= area.left


def test_many_events_scroll_inside_and_the_titlebar_and_buttons_stay_reachable(gui, monkeypatch):  # noqa: F811
    bar, app, tmp = gui
    area = R(0, 0, 1000, 420)                                                  # monitor pequeno: o conteudo nao cabe
    monkeypatch.setattr("tools.orchestration.agent_bar.window.screen_areas", lambda: [area])
    s = snap(tmp)
    s.events = [col.GroupedEvent(iso(i), iso(i), "FAILED", f"review:{i}:{i}:a", "motivo " * 20, 1, True) for i in range(20)]
    s.last_error = "erro " * 80
    bar.on_snapshot(s)
    bar.toggle_details()
    app.processEvents()
    d = bar.details
    assert d.height() <= area.height - 16 and d.y() >= area.top and d.y() + d.height() <= area.bottom
    assert d.scroll.verticalScrollBar().maximum() > 0                          # rola por dentro
    assert d.titlebar.btn_close.isVisible() and d.buttons["stop"].isVisible()
    assert d.titlebar.y() == 0                                                  # titulo ancorado no topo da janela


def test_a_snapshot_arriving_while_closed_or_collapsed_does_not_reopen_or_expand_the_panel(gui):  # noqa: F811
    bar, app, tmp = gui
    s = snap(tmp)
    bar.on_snapshot(s)
    assert not bar.details.isVisible()
    bar.toggle_details()
    bar.details.titlebar.btn_min.click()
    bar.on_snapshot(s)
    assert bar.details.height() == 30
    bar.details.titlebar.btn_close.click()
    bar.on_snapshot(s)
    assert not bar.details.isVisible()


def test_the_worker_keeps_running_conceptually_closing_the_panel_does_not_touch_collection(gui):  # noqa: F811
    bar, app, tmp = gui
    calls = []
    bar.worker.refresh = lambda force=False: calls.append(force)
    bar.toggle_details()
    bar.details.titlebar.btn_close.click()
    assert calls == []                                                          # fechar nao dispara nem cancela coleta
