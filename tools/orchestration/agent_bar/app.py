"""app.py — entrada da barra: `python -m tools.orchestration.agent_bar.app [--once-json] [--screenshot ARQ.png]`."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent_bar")
    ap.add_argument("--once-json", action="store_true", help="imprime o diagnostico da coleta e sai (sem GUI)")
    ap.add_argument("--screenshot", help="grava um PNG da barra (e do painel expandido) apos a 1a coleta e sai")
    ns = ap.parse_args(argv)
    if ns.once_json:
        from tools.orchestration.agent_bar import collectors as col
        print(col.collect_snapshot().diagnostic())
        return 0
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 nao instalado: uv pip install PySide6-Essentials (extra agent-bar)", file=sys.stderr)
        return 2
    from tools.orchestration.agent_bar import settings as cfg
    from tools.orchestration.agent_bar.window import Bar
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    bar = Bar(cfg.load())
    bar.show()
    if ns.screenshot:
        def shot() -> None:
            bar.details.show()
            bar._sync_details()                                               # noqa: SLF001
            QTimer.singleShot(400, lambda: (bar.grab().save(ns.screenshot), bar.details.grab().save(ns.screenshot.replace(".png", "_panel.png")),
                                            bar.close_app()))
        QTimer.singleShot(7000, shot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
