"""Gate framework §6.3 — read-only file-fetch (allowlist + safety)."""
from __future__ import annotations

from pathlib import Path

from tools.gate_filefetch import (
    build_followup,
    is_allowed,
    parse_need_files,
    safe_read_files,
)

REPO = Path(__file__).resolve().parents[1]
_REAL = "fixtures/quadrado/consensus_with_window.json"


def test_parse_need_files_variants():
    assert parse_need_files("Need-files: a/b.json, c.md") == ["a/b.json", "c.md"]
    assert parse_need_files("- **Need files**: `x.py`") == ["x.py"]
    assert parse_need_files(
        "Verdict: MORE-INFO\nNeed_files: fixtures/q/c.json") == ["fixtures/q/c.json"]
    assert parse_need_files("no file request here") == []


def test_is_allowed_repo_text_file():
    assert is_allowed(_REAL, REPO)
    assert is_allowed("tools/overlay_diff.py", REPO)


def test_is_allowed_blocks_secrets_and_traversal():
    assert not is_allowed(".oauth_token", REPO)
    assert not is_allowed("tools/claude_bridge/.oauth_token", REPO)
    assert not is_allowed("../../etc/passwd", REPO)       # traversal
    assert not is_allowed("deploy.key", REPO)
    assert not is_allowed("cert.pem", REPO)
    assert not is_allowed("runs/planta_74/model.skp", REPO)   # not a text suffix
    assert not is_allowed("my_secret.json", REPO)             # 'secret' in name


def test_safe_read_reads_allowed_denies_secret_and_missing():
    res = safe_read_files([_REAL, ".oauth_token", "does/not/exist.json"], REPO)
    assert res[_REAL]["ok"] and "{" in res[_REAL]["content"]
    assert not res[".oauth_token"]["ok"]
    assert not res["does/not/exist.json"]["ok"]


def test_build_followup_includes_content_and_denial():
    files = {"a.json": {"ok": True, "content": "DATA123"},
             "b.key": {"ok": False, "reason": "denied"}}
    out = build_followup("decide A vs B", files)
    assert "decide A vs B" in out
    assert "DATA123" in out
    assert "denied" in out
