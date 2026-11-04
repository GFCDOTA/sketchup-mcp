"""window.py — barra flutuante (PySide6) + painel expandido compacto (FP-058). So interface: coleta e controles vem de collectors/controls.
A coleta roda em thread propria; a UI so recebe `Snapshot` por sinal. Acoes demoradas (parar/reiniciar) rodam fora da thread de UI e
o resultado REAL aparece na linha de status do painel (nenhum botao aparenta sucesso quando a acao falhou)."""
from __future__ import annotations

import datetime as dt
import html
import threading
import traceback
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from tools.orchestration.agent_bar import collectors as col
from tools.orchestration.agent_bar import controls as ctl
from tools.orchestration.agent_bar import settings as cfg
from tools.orchestration.agent_bar.models import GroupedEvent, Level, Snapshot

COLORS = {Level.GREEN: "#3ddc84", Level.BLUE: "#4aa8ff", Level.YELLOW: "#ffc233", Level.RED: "#ff4d4f", Level.GRAY: "#8a8f98"}
LEVEL_NAME = {Level.GREEN: "operacional", Level.BLUE: "executando", Level.YELLOW: "aguardando", Level.RED: "erro", Level.GRAY: "desligado/indisponivel"}
BTN_CSS = ("QPushButton{background:#2a2a30;color:#ddd;border:0;border-radius:6px;padding:4px 6px;font-size:11px}"
           "QPushButton:hover{background:#3a3a44}QPushButton:disabled{color:#666}")


class Worker(QObject):
    """Coleta periodica fora da thread de UI. Local a cada `local_interval_s`; GitHub e Project #1 com cache/TTL proprios."""
    snapshot = Signal(object)

    def __init__(self, settings: cfg.Settings, gov: Path | None = None):
        super().__init__()
        self.settings, self.gov = settings, gov
        self._stop, self._now = threading.Event(), threading.Event()
        self._cache = col.GithubCache(ttl_s=settings.github_interval_s)
        self._backlog = col.GithubCache(ttl_s=settings.backlog_interval_s)
        self._thread = threading.Thread(target=self._loop, name="agent-bar-collector", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def refresh(self, force: bool = False) -> None:
        if force:
            self._cache.invalidate()
            self._backlog.invalidate()
        self._now.set()

    def stop(self) -> None:
        self._stop.set()
        self._now.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.snapshot.emit(col.collect_snapshot(self.gov, cache=self._cache, backlog_cache=self._backlog))
            except Exception:                                                  # noqa: BLE001 — coleta nunca derruba a UI
                traceback.print_exc()
            self._now.wait(self.settings.local_interval_s)
            self._now.clear()


def dot(level: Level) -> str:
    return f'<span style="color:{COLORS[level]};font-size:13px">&#9679;</span>'


def hhmm(iso_text: str | None) -> str:
    t = col.parse_iso(iso_text)
    return "-" if t is None else t.astimezone().strftime("%H:%M:%S")


def esc(text: str) -> str:
    return html.escape(text or "")


class Details(QWidget):
    def __init__(self, bar: "Bar"):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.bar = bar
        self._seen_top: str | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(2)
        self.banner, self.agents, self.health, self.backlog = QLabel(), QLabel(), QLabel(), QLabel()
        for w in (self.banner, self.agents, self.health, self.backlog):
            w.setTextFormat(Qt.TextFormat.RichText)
            w.setWordWrap(True)
            w.setMargin(0)
            w.setStyleSheet("color:#e6e6e6;font-size:11px")
            lay.addWidget(w)
        self.events = QListWidget()
        self.events.setStyleSheet("QListWidget{background:#17171a;color:#cfcfd4;border:0;font-size:11px}QListWidget::item{padding:1px 4px}")
        self.events.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.events.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.events.setToolTip("Duplo clique: abre o log original")
        self.events.itemDoubleClicked.connect(lambda _i: bar.action_logs())
        lay.addWidget(self.events)
        self.status = QLabel("pronto")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#9a9aa2;font-size:11px")
        lay.addWidget(self.status)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.buttons: dict[str, QPushButton] = {}
        specs = [("repo", "Repositório", bar.action_repo), ("project", "Project #1", bar.action_project), ("pr", "PR atual", bar.action_pr),
                 ("logs", "Logs", bar.action_logs), ("diag", "Copiar diagnóstico", bar.action_copy_diag),
                 ("refresh", "Atualizar", bar.action_refresh), ("restart", "Reiniciar DRY_RUN", bar.action_restart), ("stop", "Parar", bar.action_stop)]
        for i, (key, text, fn) in enumerate(specs):
            b = QPushButton(text)
            b.setStyleSheet(BTN_CSS)
            b.clicked.connect(lambda _=False, f=fn: f())
            self.buttons[key] = b
            grid.addWidget(b, i // 4, i % 4)
        lay.addLayout(grid)

    def paintEvent(self, _e) -> None:                                           # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(22, 22, 26, 238))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 14, 14)

    def set_status(self, ok: bool, text: str) -> None:
        color = "#3ddc84" if ok else "#ff6b6d"
        self.status.setText(f'<span style="color:{color}">{"&#10003;" if ok else "&#10007;"}</span> {esc(text)}  <span style="color:#6d6d75">{dt.datetime.now():%H:%M:%S}</span>')
        self.status.setTextFormat(Qt.TextFormat.RichText)

    def _event_text(self, e: GroupedEvent) -> str:
        span = f"  ×{e.count} ({hhmm(e.first_at)}–{hhmm(e.last_at)})" if e.count > 1 else ""
        reason = f"  {e.reason}" if e.reason and e.count == 1 else ""
        return f"{hhmm(e.last_at)}  {e.action}  {e.pr_label()}{span}{reason}"[:150]

    def update_snapshot(self, s: Snapshot) -> None:
        self.banner.setText(f'<b style="color:{"#ffc233" if s.mode == "DRY_RUN" else "#ff6b6d" if s.mode == "EXECUTE" else "#8a8f98"}">'
                            f'{esc(s.mode_banner())}</b> &middot; {esc(s.work)}')
        rows = []
        for a in s.agents():
            pid = f" <span style='color:#8a8f98'>pid {a.pid}</span>" if a.pid else ""
            rows.append(f"{dot(a.level)} <b>{a.name}</b> {esc(a.label)}{pid}<br><span style='color:#8f8f98'>&nbsp;&nbsp;&nbsp;{esc(a.detail)}</span>")
        self.agents.setText("<br>".join(rows))
        hb = "indisponível" if s.heartbeat_age_s is None else f"{s.heartbeat_age_s}s"
        ks = "indisponível" if s.kill_switch is None else ("ATIVO" if s.kill_switch else "inativo")
        err = f"<br><span style='color:#ff9a9b'>último erro: {esc(s.last_error)}</span>" if s.last_error else ""
        self.health.setText(f"<b>Saúde</b> heartbeat {hb} &middot; kill switch {ks} &middot; instâncias "
                            f"{'?' if s.concurrent_instances is None else s.concurrent_instances}<br>lock: {esc(s.lock_status)}<br>"
                            f"executor: {esc(s.executor_summary)}{err}")
        known = any(v is not None for v in s.backlog.values())
        cols = " &middot; ".join(f"{k} <b>{'?' if v is None else v}</b>" for k, v in s.backlog.items())
        if s.backlog_error and known:
            self.backlog.setText(f"<b>Backlog</b> {cols} <span style='color:#ffc233'>(desatualizado desde {hhmm(s.backlog_synced)})</span>"
                                 f"<br><span style='color:#ff9a9b'>erro: {esc(s.backlog_error)}</span>")
        elif s.backlog_error:
            self.backlog.setText(f"<b>Backlog</b> <span style='color:#ff9a9b'>erro: {esc(s.backlog_error)}</span>")
        else:
            self.backlog.setText(f"<b>Backlog</b> {cols} <span style='color:#6d6d75'>(sync {hhmm(s.backlog_synced)})</span>")
        top = s.events[0].last_at if s.events else None
        self.events.clear()
        for e in s.events[:20]:
            it = QListWidgetItem(self._event_text(e))
            new = self._seen_top is not None and e.last_at > self._seen_top
            if e.error:
                it.setForeground(QColor("#ff6b6d"))
            elif new:
                it.setForeground(QColor("#4aa8ff"))
            if new or e.error:
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            self.events.addItem(it)
        self._seen_top = top or self._seen_top
        rows_h = self.events.sizeHintForRow(0) if self.events.count() else 0
        self.events.setFixedHeight(min(max(self.events.count(), 1), 6) * max(rows_h, 20) + 6)       # sem espaco vazio; rola acima de 6
        self.adjustSize()


class Bar(QWidget):
    result = Signal(bool, str)

    def __init__(self, settings: cfg.Settings, gov: Path | None = None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.settings, self.gov = settings, gov or col.default_gov_dir()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(settings.opacity)
        self.resize(550, 65)
        self.labels: dict[str, QLabel] = {}
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 12, 6)
        lay.setSpacing(14)
        for name in ("Claude", "Codex", "Listener", "GitHub"):
            lb = QLabel(f"{dot(Level.GRAY)} {name}")
            lb.setTextFormat(Qt.TextFormat.RichText)
            lb.setStyleSheet("color:#f0f0f0;font-size:13px;font-weight:600")
            self.labels[name] = lb
            lay.addWidget(lb)
        self.pr = QLabel("PR -")
        self.pr.setStyleSheet("color:#bdbdc4;font-size:12px")
        lay.addWidget(self.pr)
        lay.addStretch(1)
        self.gear = QLabel("&#9881;")
        self.gear.setTextFormat(Qt.TextFormat.RichText)
        self.gear.setStyleSheet("color:#bdbdc4;font-size:17px")
        lay.addWidget(self.gear)
        self.snap: Snapshot | None = None
        self._drag: QPoint | None = None
        self._moved = False
        self._levels: dict[str, Level] = {}
        self._refresh_pending: float | None = None
        self.tray = QSystemTrayIcon(self) if QSystemTrayIcon.isSystemTrayAvailable() else None
        self.worker = Worker(settings, self.gov)
        self.details = Details(self)
        self.worker.snapshot.connect(self.on_snapshot)
        self.result.connect(self.details.set_status)
        self._place()
        self.worker.start()

    # -------------------------------------------------------------------------------------------------- posicao/pintura
    def _place(self) -> None:
        if self.settings.x is not None and self.settings.y is not None:
            self.move(self.settings.x, self.settings.y)
        else:
            g = QGuiApplication.primaryScreen().availableGeometry()
            self.move(g.right() - self.width() - 24, g.top() + 24)

    def paintEvent(self, _e) -> None:                                           # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(20, 20, 24, 225))
        p.setPen(QColor(70, 70, 80, 200))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 16, 16)

    # ------------------------------------------------------------------------------------------------------- mouse
    def mousePressEvent(self, e) -> None:                                       # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag, self._moved = e.globalPosition().toPoint() - self.frameGeometry().topLeft(), False

    def mouseMoveEvent(self, e) -> None:                                        # noqa: N802
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self._moved = True
            self.move(e.globalPosition().toPoint() - self._drag)
            self._sync_details()

    def mouseReleaseEvent(self, e) -> None:                                     # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            if not self._moved:
                self.toggle_details()
            else:
                self.settings.x, self.settings.y = self.x(), self.y()
                cfg.save(self.settings)
            self._drag = None

    def contextMenuEvent(self, e) -> None:                                      # noqa: N802
        m = QMenu(self)
        m.addAction("Expandir / recolher", self.toggle_details)
        m.addAction("Atualizar agora", self.action_refresh)
        n = QAction("Notificacoes", m, checkable=True, checked=self.settings.notifications)
        n.toggled.connect(self.set_notifications)
        m.addAction(n)
        m.addAction("Minimizar para icone", self.toggle_minimized)
        m.addSeparator()
        m.addAction("Encerrar barra", self.close_app)
        m.exec(e.globalPos())

    # ---------------------------------------------------------------------------------------------------- painel/estado
    def toggle_details(self) -> None:
        if self.details.isVisible():
            self.details.hide()
        else:
            self._sync_details()
            self.details.show()

    def _sync_details(self) -> None:
        g = QGuiApplication.primaryScreen().availableGeometry()
        x = min(max(self.x(), g.left()), g.right() - self.details.width())       # nunca fora da tela (escalas/resolucoes)
        self.details.move(x, min(self.y() + self.height() + 6, g.bottom() - self.details.height()))

    def toggle_minimized(self) -> None:
        self.settings.minimized = not self.settings.minimized
        cfg.save(self.settings)
        mini = self.settings.minimized
        for w in (*self.labels.values(), self.pr, self.gear):
            w.setVisible(not mini)
        self.resize(44 if mini else 550, 44 if mini else 65)
        if mini:
            self.details.hide()

    def set_notifications(self, on: bool) -> None:
        self.settings.notifications = on
        cfg.save(self.settings)

    def report(self, r: ctl.Result) -> None:
        self.result.emit(r.ok, r.message)

    # ------------------------------------------------------------------------------------------------ acoes (botoes)
    def action_repo(self) -> None:
        self.report(ctl.open_url(ctl.REPO_URL))

    def action_project(self) -> None:
        self.report(ctl.open_url(ctl.PROJECT_URL))

    def action_pr(self) -> None:
        self.report(ctl.open_url(self.snap.pr_url if self.snap else None))

    def action_logs(self) -> None:
        p = ctl.latest_log(self.gov)
        self.report(ctl.open_path(p) if p else ctl.Result(False, "nenhum log encontrado"))

    def action_copy_diag(self) -> None:
        if not self.snap:
            self.report(ctl.Result(False, "sem coleta ainda: nada para copiar"))
            return
        text = ctl.diagnostic_text(self.snap)
        QApplication.clipboard().setText(text)
        ok = QApplication.clipboard().text() == text                              # prova: le de volta
        self.report(ctl.Result(ok, f"diagnostico copiado ({len(text)} caracteres)" if ok else "falha ao copiar para a area de transferencia"))

    def action_refresh(self) -> None:
        self._refresh_pending = True
        self.worker.refresh(force=True)
        QTimer.singleShot(15000, self._refresh_timeout)

    def _refresh_timeout(self) -> None:
        if self._refresh_pending:
            self._refresh_pending = None
            self.report(ctl.Result(False, "atualizar: sem resposta da coleta em 15 s"))

    def _run_async(self, fn: Callable[[], ctl.Result]) -> None:
        def go() -> None:
            try:
                r = fn()
            except Exception as exc:                                             # noqa: BLE001 — falha vira mensagem, nunca sucesso falso
                r = ctl.Result(False, f"erro inesperado: {type(exc).__name__}: {exc}")
            self.result.emit(r.ok, r.message)
            self.worker.refresh(force=False)
        threading.Thread(target=go, name="agent-bar-control", daemon=True).start()

    def action_restart(self) -> None:
        if self.confirm("Reiniciar o listener em DRY_RUN? Nao executa nada; recusa com kill switch, execucao ativa ou -Execute."):
            self.details.set_status(True, "reiniciando em DRY_RUN...")
            self._run_async(lambda: ctl.restart_listener_dry_run(confirmed=True, gov=self.gov))

    def action_stop(self) -> None:
        if self.confirm("Parar o listener (Tarefa Agendada)? Recusa se houver execucao ativa."):
            self.details.set_status(True, "parando o listener...")
            self._run_async(lambda: ctl.stop_listener(confirmed=True))

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self, "Confirmar", text) == QMessageBox.StandardButton.Yes

    def close_app(self) -> None:
        self.worker.stop()
        self.details.close()
        QApplication.quit()

    # ------------------------------------------------------------------------------------------------------ snapshot
    def on_snapshot(self, s: Snapshot) -> None:
        self.snap = s
        for a in s.agents():
            self.labels[a.name].setText(f"{dot(a.level)} {a.name}")
            self.labels[a.name].setToolTip(f"{a.line()}\n({LEVEL_NAME[a.level]})")
            if self.settings.notifications and self.tray and a.level is Level.RED and self._levels.get(a.name) not in (None, Level.RED):
                self.tray.showMessage("Agent bar", a.line(), QSystemTrayIcon.MessageIcon.Warning)
            self._levels[a.name] = a.level
        self.pr.setText(f"PR #{s.pr}" if s.pr else "PR -")
        self.pr.setToolTip(f"checks: {s.github_checks}")
        self.gear.setToolTip(f"{s.mode_banner()}\n{s.work}\n" + (s.last_error or "sem erro observado"))
        self.details.update_snapshot(s)
        if self._refresh_pending:
            self._refresh_pending = None
            self.report(ctl.Result(True, f"atualizado (coleta {hhmm(s.at)})"))
