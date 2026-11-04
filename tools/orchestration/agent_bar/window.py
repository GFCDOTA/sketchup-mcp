"""window.py — barra flutuante (PySide6) + painel expandido (FP-058). So interface: coleta e controles vem de collectors/controls.
A coleta roda em thread propria; a UI so recebe `Snapshot` por sinal (nunca bloqueia em subprocesso)."""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidget,
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
from tools.orchestration.agent_bar.models import Level, Snapshot

COLORS = {Level.GREEN: "#3ddc84", Level.BLUE: "#4aa8ff", Level.YELLOW: "#ffc233", Level.RED: "#ff4d4f", Level.GRAY: "#8a8f98"}
LEVEL_NAME = {Level.GREEN: "operacional", Level.BLUE: "executando", Level.YELLOW: "aguardando", Level.RED: "erro", Level.GRAY: "desligado/indisponivel"}


class Worker(QObject):
    """Coleta periodica fora da thread de UI. GitHub com cache (TTL configuravel); local a cada `local_interval_s`."""
    snapshot = Signal(object)

    def __init__(self, settings: cfg.Settings, gov: Path | None = None):
        super().__init__()
        self.settings, self.gov = settings, gov
        self._stop, self._now = threading.Event(), threading.Event()
        self._cache = col.GithubCache(ttl_s=settings.github_interval_s)
        self._thread = threading.Thread(target=self._loop, name="agent-bar-collector", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def refresh(self) -> None:
        self._now.set()

    def stop(self) -> None:
        self._stop.set()
        self._now.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.snapshot.emit(col.collect_snapshot(self.gov, cache=self._cache))
            except Exception:                                                  # noqa: BLE001 — coleta nunca derruba a UI
                traceback.print_exc()
            self._now.wait(self.settings.local_interval_s)
            self._now.clear()


def dot(level: Level) -> str:
    return f'<span style="color:{COLORS[level]};font-size:15px">&#9679;</span>'


class Details(QWidget):
    def __init__(self, bar: "Bar"):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.bar = bar
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(550)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        self.agents, self.health, self.backlog = QLabel(), QLabel(), QLabel()
        for w in (self.agents, self.health, self.backlog):
            w.setTextFormat(Qt.TextFormat.RichText)
            w.setStyleSheet("color:#e6e6e6;font-size:12px")
            w.setWordWrap(True)
            lay.addWidget(w)
        self.events = QListWidget()
        self.events.setMaximumHeight(170)
        self.events.setStyleSheet("background:#17171a;color:#cfcfd4;border:0;font-size:11px")
        lay.addWidget(self.events)
        row = QHBoxLayout()
        for text, fn in (("Repositorio", lambda: ctl.open_url(ctl.REPO_URL)), ("Project #1", lambda: ctl.open_url(ctl.PROJECT_URL)),
                         ("PR atual", bar.open_pr), ("Logs", bar.open_logs), ("Copiar diagnostico", bar.copy_diag),
                         ("Atualizar", bar.worker.refresh), ("Reiniciar DRY_RUN", bar.restart), ("Parar", bar.stop)):
            b = QPushButton(text)
            b.setStyleSheet("QPushButton{background:#2a2a30;color:#ddd;border:0;border-radius:6px;padding:5px 8px;font-size:11px}"
                            "QPushButton:hover{background:#3a3a44}")
            b.clicked.connect(lambda _=False, f=fn: f())
            row.addWidget(b)
        lay.addLayout(row)

    def paintEvent(self, _e) -> None:                                           # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(22, 22, 26, 235))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 14, 14)

    def update_snapshot(self, s: Snapshot) -> None:
        rows = [f"{dot(a.level)} <b>{a.name}</b> &mdash; {a.label}{f' (pid {a.pid})' if a.pid else ''}"
                f"<br><span style='color:#9a9aa2'>&nbsp;&nbsp;&nbsp;{a.detail}</span>" for a in s.agents()]
        self.agents.setText("<b>Agentes</b><br>" + "<br>".join(rows))
        hb = "indisponivel" if s.heartbeat_age_s is None else f"{s.heartbeat_age_s}s"
        ks = "indisponivel" if s.kill_switch is None else ("ATIVO" if s.kill_switch else "inativo")
        inst = "indisponivel" if s.concurrent_instances is None else str(s.concurrent_instances)
        self.health.setText(f"<b>Saude</b><br>modo {s.mode} &middot; heartbeat {hb} &middot; kill switch {ks} &middot; instancias {inst}"
                            f" &middot; lock {s.lock_holder or 'indisponivel'}<br>ultimo erro: {s.last_error or 'nenhum observado'}")
        b = s.backlog
        self.backlog.setText("<b>Backlog</b> &mdash; " + " &middot; ".join(f"{k}: {'Indisponivel' if v is None else v}" for k, v in b.items()))
        self.events.clear()
        for e in s.events[:20]:
            self.events.addItem(f"{e.at[11:19]}  {e.action}  {e.item.split(':')[2] if e.item.count(':') > 1 else e.item}  {e.reason}"[:140])


class Bar(QWidget):
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
        self.tray = QSystemTrayIcon(self) if QSystemTrayIcon.isSystemTrayAvailable() else None
        self.worker = Worker(settings, self.gov)
        self.details = Details(self)
        self.worker.snapshot.connect(self.on_snapshot)
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
        m.addAction("Atualizar agora", self.worker.refresh)
        n = QAction("Notificacoes", m, checkable=True, checked=self.settings.notifications)
        n.toggled.connect(self.set_notifications)
        m.addAction(n)
        m.addAction("Minimizar para icone", self.toggle_minimized)
        m.addSeparator()
        m.addAction("Encerrar barra", self.close_app)
        m.exec(e.globalPos())

    # ---------------------------------------------------------------------------------------------------------- acoes
    def toggle_details(self) -> None:
        if self.details.isVisible():
            self.details.hide()
        else:
            self._sync_details()
            self.details.show()

    def _sync_details(self) -> None:
        self.details.move(self.x(), self.y() + self.height() + 6)

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

    def open_pr(self) -> None:
        r = ctl.open_url(self.snap.pr_url if self.snap else None)
        if not r.ok:
            self.info(r.message)

    def open_logs(self) -> None:
        p = ctl.latest_log(self.gov)
        r = ctl.open_path(p) if p else ctl.Result(False, "nenhum log encontrado")
        if not r.ok:
            self.info(r.message)

    def copy_diag(self) -> None:
        if self.snap:
            QApplication.clipboard().setText(ctl.diagnostic_text(self.snap))

    def restart(self) -> None:
        if self.confirm("Reiniciar o listener em DRY_RUN? (nao executa nada; recusa se houver execucao ativa)"):
            self.info(ctl.restart_listener_dry_run(confirmed=True).message)
            self.worker.refresh()

    def stop(self) -> None:
        if self.confirm("Parar o listener (Tarefa Agendada)? Recusa se houver execucao ativa."):
            self.info(ctl.stop_listener(confirmed=True).message)
            self.worker.refresh()

    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self, "Confirmar", text) == QMessageBox.StandardButton.Yes

    def info(self, text: str) -> None:
        QMessageBox.information(self, "Agent bar", text)

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
        self.gear.setToolTip(f"modo {s.mode}\n" + (s.last_error or "sem erro observado"))
        self.details.update_snapshot(s)
