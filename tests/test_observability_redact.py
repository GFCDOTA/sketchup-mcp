"""Redaction acontece NO SINK. Se vazar aqui, vazou pro disco."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.observability.redact import (
    ALLOWED_META_KEYS,
    dropped_keys,
    redact_meta,
    relativize,
    scrub_text,
    sha12,
)

# ---------------------------------------------------------------------------
# allowlist: chave nova nasce bloqueada
# ---------------------------------------------------------------------------


def test_unknown_keys_are_dropped_not_kept():
    meta = redact_meta({"chunkId": "a1", "senhaDoBanco": "hunter2",
                        "campoNovoQueNinguemProibiu": "dado sensível"})
    assert meta == {"chunkId": "a1"}


def test_dropped_keys_are_reportable_for_diagnosis():
    assert dropped_keys({"score": 1, "xyz": 2, "abc": 3}) == ["abc", "xyz"]


def test_prompt_and_chunk_text_are_not_in_the_allowlist():
    """O corpo nunca entra no evento — nem prompt, nem texto de chunk."""
    for key in ("prompt", "text", "systemPrompt", "response", "completion",
                "context", "messages"):
        assert key not in ALLOWED_META_KEYS


def test_empty_meta_is_empty_dict():
    assert redact_meta(None) == {}
    assert redact_meta({}) == {}


# ---------------------------------------------------------------------------
# scrub: segredo colado num campo legítimo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("secret", [
    "sk-abcdefghijklmnopqrstuvwxyz012345",
    "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    "xoxb-1234567890-abcdefghij",
])
def test_known_token_shapes_are_scrubbed(secret):
    assert secret not in scrub_text(f"falhou com credencial {secret} no header")


def test_bearer_header_is_scrubbed():
    assert "eyJhbGciOi" not in scrub_text("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")


def test_key_value_secret_is_scrubbed():
    out = scrub_text("conectando com api_key=abc123xyz789 e token=zzzz9999")
    assert "abc123xyz789" not in out
    assert "zzzz9999" not in out


def test_url_embedded_credentials_are_scrubbed():
    out = scrub_text("POST http://felipe:senhaSuperSecreta@localhost:6333/collections")
    assert "senhaSuperSecreta" not in out
    assert "localhost:6333" in out          # o endpoint em si continua útil


def test_email_is_scrubbed():
    assert "fmodesto30@gmail.com" not in scrub_text("autor: fmodesto30@gmail.com")


def test_scrub_runs_on_allowlisted_values_too():
    """Caso REAL: InfraUnavailable(f'... falhou: {e!r}') serializa a URL inteira,
    e `error` é uma chave legítima da allowlist."""
    meta = redact_meta({"error": "POST http://u:p@localhost:6333 falhou: "
                                 "token=abc123secret"})
    assert "abc123secret" not in meta["error"]
    assert "p@localhost" not in meta["error"]


# ---------------------------------------------------------------------------
# paths: privacidade, não segredo
# ---------------------------------------------------------------------------


def test_repo_absolute_path_becomes_relative():
    repo = Path(__file__).resolve().parents[1]
    out = relativize(f"{repo}\\tools\\reference_db.py")
    assert "reference_db.py" in out
    assert str(repo) not in out


def test_foreign_absolute_path_loses_its_prefix():
    out = relativize(r"C:\Users\felip_local\AppData\Local\segredo\arquivo.json")
    assert "felip_local" not in out
    assert "arquivo.json" in out


def test_posix_absolute_path_loses_its_prefix():
    out = relativize("/home/alguem/projetos/privado/config.yml")
    assert "alguem" not in out
    assert "config.yml" in out


# ---------------------------------------------------------------------------
# limites de tamanho (performance)
# ---------------------------------------------------------------------------


def test_long_string_is_truncated():
    meta = redact_meta({"reason": "x" * 5000})
    assert len(meta["reason"]) <= 520


def test_long_list_is_capped():
    meta = redact_meta({"contextRefs": [f"c{i}" for i in range(500)]})
    assert len(meta["contextRefs"]) <= 64


def test_deep_nesting_is_cut_off():
    deep: dict = {"a": 1}
    for _ in range(10):
        deep = {"a": deep}
    meta = redact_meta({"measurements": deep})
    assert meta["measurements"] is not None      # não explode, só corta


def test_numbers_and_booleans_pass_through_untouched():
    meta = redact_meta({"score": 0.9412, "rank": 3, "selected": False,
                        "measured": None})
    assert meta == {"score": 0.9412, "rank": 3, "selected": False, "measured": None}


# ---------------------------------------------------------------------------
# referência segura ao prompt
# ---------------------------------------------------------------------------


def test_sha12_is_stable_and_short():
    a = sha12("SYSTEM_PROMPT + contexto")
    assert a == sha12("SYSTEM_PROMPT + contexto")
    assert len(a) == 12
    assert a != sha12("SYSTEM_PROMPT + outro contexto")
