#!/usr/bin/env python3
"""Gate framework §6.3 — read-only file-fetch for the oracle.

The oracle is blind to artifacts (it sees only the prompt), so it used to guess
facts. Now, when it needs a file, it answers `Verdict: MORE-INFO` +
`Need-files: <paths>`; the asker reads them (READ-ONLY, allowlisted) and re-sends.

Safety (the whole point): paths must live INSIDE the repo (no traversal), have an
allowed text suffix, and never be a secret (.oauth_token / .env / *.key / *.pem /
*.token / id_rsa / *secret*). Never written, only read; capped size.
"""
from __future__ import annotations

import re
from pathlib import Path

ALLOW_SUFFIX = (".json", ".jsonl", ".py", ".rb", ".md", ".txt", ".cfg", ".toml", ".ini")
_DENY_NAMES = (".oauth_token", ".env")
_DENY_SUFFIX = (".pem", ".key", ".token")
MAX_BYTES = 200_000


def parse_need_files(raw: str) -> list[str]:
    """Extract the file paths the oracle asked for (`Need-files: a, b`)."""
    m = re.search(
        r"(?im)^[ \t>*\-\d.\)]*\**\s*need[_\- ]?files?\**\s*[:\-]\s*(.+)$", raw or "")
    if not m:
        return []
    parts = re.split(r"[,\s`'\"]+", m.group(1).strip())
    seen, out = set(), []
    for p in parts:
        p = p.strip().rstrip(".")
        if p and ("/" in p or "." in p) and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def is_allowed(path: str, repo_root: Path) -> bool:
    """True iff `path` is a repo-internal, non-secret, allowed-suffix text file."""
    repo_root = Path(repo_root).resolve()
    try:
        p = (repo_root / path).resolve()
        p.relative_to(repo_root)            # inside the repo (blocks ../ traversal)
    except (ValueError, OSError):
        return False
    name = p.name.lower()
    if name in _DENY_NAMES or name.endswith(_DENY_SUFFIX):
        return False
    if "secret" in name or "id_rsa" in name:
        return False
    return p.suffix.lower() in ALLOW_SUFFIX


def safe_read_files(paths, repo_root) -> dict:
    """Read each allowed path (read-only, capped). Returns
    {path: {ok, content|reason}}."""
    repo_root = Path(repo_root)
    out: dict[str, dict] = {}
    for path in paths:
        if not is_allowed(path, repo_root):
            out[path] = {"ok": False, "reason": "denied (allowlist / secret / traversal)"}
            continue
        p = (repo_root / path).resolve()
        if not p.is_file():
            out[path] = {"ok": False, "reason": "not found"}
            continue
        try:
            out[path] = {"ok": True,
                         "content": p.read_text("utf-8", errors="replace")[:MAX_BYTES]}
        except OSError as e:
            out[path] = {"ok": False, "reason": f"read error: {e}"}
    return out


def build_followup(prompt: str, files: dict) -> str:
    """Compose the re-send: original prompt + the requested files (read-only)."""
    parts = [prompt, "", "=== REQUESTED FILES (read-only) ==="]
    for path, r in files.items():
        if r.get("ok"):
            parts += [f"--- {path} ---", r["content"]]
        else:
            parts += [f"--- {path}: {r.get('reason', 'unavailable')} ---"]
    return "\n".join(parts)
