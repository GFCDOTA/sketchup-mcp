"""Front local do Estudio (iFood-style) — stdlib only, sem dependencias.

Sobe em http://127.0.0.1:8788 (LAN opcional via ESTUDIO_BIND=0.0.0.0).
- GET  /               -> index.html
- GET  /assets/*       -> fotos/render
- GET  /api/status     -> status.json (o Claude atualiza a cada etapa)
- POST /api/curadoria  -> grava curadoria/<timestamp>.json (o Claude vigia a pasta)

Descartavel por design: sem watchdog, sem task agendada (licao do NOC).
O Claude sobe quando a sessao esta ativa.
"""
from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CURADORIA = ROOT / "curadoria"
CURADORIA.mkdir(exist_ok=True)

CTYPES = {".html": "text/html; charset=utf-8", ".png": "image/png",
          ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".json": "application/json"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        if path == "/api/status":
            f = ROOT / "status.json"
            body = f.read_bytes() if f.exists() else b"{}"
            self._send(200, body)
            return
        target = (ROOT / path.lstrip("/")).resolve()
        if not str(target).startswith(str(ROOT)) or not target.is_file():
            self._send(404, b'{"erro":"nao achei"}')
            return
        self._send(200, target.read_bytes(), CTYPES.get(target.suffix.lower(), "application/octet-stream"))

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?")[0] != "/api/curadoria":
            self._send(404, b'{"erro":"rota desconhecida"}')
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, b'{"erro":"json invalido"}')
            return
        out = CURADORIA / f"curadoria_{time.strftime('%Y%m%d_%H%M%S')}.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), "utf-8")
        self._send(200, b'{"ok":true}')

    def log_message(self, fmt: str, *args) -> None:  # silencioso
        pass


def main() -> None:
    bind = os.environ.get("ESTUDIO_BIND", "127.0.0.1")
    port = int(os.environ.get("ESTUDIO_PORT", "8788"))
    print(f"estudio-front em http://{bind}:{port} (curadoria -> {CURADORIA})", flush=True)
    ThreadingHTTPServer((bind, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
