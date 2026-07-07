"""grafo_server.py — servidor MÍNIMO do Mapa de Conhecimento (:8783).

Independente do dashboard :8782 (studio_dashboard.py), que está sob edição de outra
sessão e revertia a integração da rota /grafo. Aqui o grafo fica estável: serve
tools/grafo.html e tools/kgraph.json e nada mais. stdlib only.

Uso:  python tools/grafo_server.py [--port 8783]
Dados: regenerar com  python tools/build_kgraph.py  (relê na hora, sem reiniciar).
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
GRAFO = HERE / "grafo.html"
FLUXO = HERE / "flow.html"
AGENTS = HERE / "agents.html"
EXPLICA = HERE / "explica.html"
HOME = HERE / "home.html"
KGRAPH = HERE / "kgraph.json"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencia o log de acesso
        pass

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            try:
                self._send(200, HOME.read_text("utf-8"), "text/html; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._send(500, f"home.html: {e}", "text/plain; charset=utf-8")
        elif p == "/grafo":
            try:
                self._send(200, GRAFO.read_text("utf-8"), "text/html; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._send(500, f"grafo.html: {e}", "text/plain; charset=utf-8")
        elif p == "/fluxo":
            try:
                self._send(200, FLUXO.read_text("utf-8"), "text/html; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._send(500, f"flow.html: {e}", "text/plain; charset=utf-8")
        elif p in ("/agents", "/single-agent", "/multi-agent"):
            try:
                self._send(200, AGENTS.read_text("utf-8"), "text/html; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._send(500, f"agents.html: {e}", "text/plain; charset=utf-8")
        elif p in ("/explica", "/como-funciona"):
            try:
                self._send(200, EXPLICA.read_text("utf-8"), "text/html; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._send(500, f"explica.html: {e}", "text/plain; charset=utf-8")
        elif p == "/api/kgraph":
            try:
                self._send(200, KGRAPH.read_text("utf-8"), "application/json; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(e)}), "application/json")
        else:
            self._send(404, b"not found", "text/plain")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8783)
    a = ap.parse_args(argv)
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    print(f"Mapa de Conhecimento -> http://127.0.0.1:{a.port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
