"""NOC lock — coordenacao de atuador/worktree (base do DIFF-004).

Garante que SO UM atuador (dispatcher) aja por vez, e da pra um worker reivindicar
posse de um recurso (branch/worktree) keyed por owner. TTL + heartbeat: se o dono
morre, o lock expira e outro pode assumir — nada de lock eterno de processo zumbi.

Stdlib pura, single-host multi-processo. Aquisicao do caso-livre e atomica
(O_CREAT|O_EXCL); takeover de lock stale/proprio e last-writer-wins (janela minima).
NAO mata/edita peers — so coordena quem PODE agir (a prevencao real de colisao e a
isolacao por worktree no dispatcher).
"""
import json
import os
import time
from pathlib import Path

DEFAULT_TTL = 900  # 15 min sem heartbeat -> lock considerado morto


class Lock:
    def __init__(self, path, owner: str, ttl: int = DEFAULT_TTL):
        self.path = Path(path)
        self.owner = owner
        self.ttl = ttl

    def _read(self):
        try:
            return json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return None

    def _payload(self) -> str:
        return json.dumps({"owner": self.owner, "pid": os.getpid(), "ts": time.time()})

    def holder(self):
        """Quem segura o lock AGORA (ou None se livre/stale). Nao considera dono==self."""
        d = self._read()
        if not d:
            return None
        if time.time() - float(d.get("ts", 0)) > self.ttl:
            return None  # stale -> livre
        return d

    def held_by_other(self):
        d = self.holder()
        if d and d.get("owner") != self.owner:
            return d
        return None

    def acquire(self) -> bool:
        """True se ESTE owner ficou com o lock. False se outro (vivo) segura."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.held_by_other():
            return False
        existing = self._read()
        if existing is None:
            # caso-livre: criacao atomica, perde a corrida -> False
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return self.acquire() if self.held_by_other() is None else False
            try:
                os.write(fd, self._payload().encode("utf-8"))
            finally:
                os.close(fd)
            d = self._read()
            return bool(d and d.get("owner") == self.owner)
        # existente porem stale ou nosso -> assume (last-writer-wins)
        self.path.write_text(self._payload(), "utf-8")
        d = self._read()
        return bool(d and d.get("owner") == self.owner)

    def heartbeat(self) -> bool:
        """Renova o ts se ainda somos o dono. False se perdemos o lock."""
        d = self._read()
        if d and d.get("owner") == self.owner:
            d["ts"] = time.time()
            self.path.write_text(json.dumps(d), "utf-8")
            return True
        return False

    def release(self) -> None:
        d = self._read()
        if d and d.get("owner") == self.owner:
            try:
                self.path.unlink()
            except OSError:
                pass

    def __enter__(self):
        self._got = self.acquire()
        return self

    def __exit__(self, *exc):
        if getattr(self, "_got", False):
            self.release()
