"""settings.py — preferencias da barra (posicao, transparencia, intervalos). JSON em %APPDATA%\\agent_bar (fora do repo). Sem Qt."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Settings:
    x: int | None = None
    y: int | None = None
    opacity: float = 0.88
    local_interval_s: int = 3          # coleta local (processos/logs)
    github_interval_s: int = 60        # TTL do cache do GitHub
    notifications: bool = False
    minimized: bool = False


def settings_path() -> Path:
    base = os.environ.get("AGENT_BAR_SETTINGS") or os.path.join(os.environ.get("APPDATA") or str(Path.home()), "agent_bar", "settings.json")
    return Path(base)


def clamp(s: Settings) -> Settings:
    s.opacity = min(1.0, max(0.3, float(s.opacity)))
    s.local_interval_s = min(30, max(2, int(s.local_interval_s)))
    s.github_interval_s = min(600, max(15, int(s.github_interval_s)))
    return s


def load(path: Path | None = None) -> Settings:
    p = path or settings_path()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        known = {k: v for k, v in raw.items() if k in Settings.__dataclass_fields__} if isinstance(raw, dict) else {}
        return clamp(Settings(**known))
    except (OSError, ValueError, TypeError):
        return Settings()


def save(s: Settings, path: Path | None = None) -> None:
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(clamp(s)), indent=1), encoding="utf-8")
    os.replace(tmp, p)
