"""FP-060 MT-09 (#663): o VALOR inteiro do cabecalho Authorization/Proxy-Authorization sai de todo texto do EventStore, qualquer que seja o esquema,
da falha persistida ate o painel e o diagnostico copiado. Revisao independente de 1917b495 (esquema OAuth escapava)."""
from __future__ import annotations

import pytest

from tests.test_agent_bar_store import (  # noqa: F401  (fixture e helpers reutilizados)
    NOW,
    snap,
    store,
)
from tools.orchestration.agent_bar import collectors as col

CRED = "abcdefghijklmnop"
SCHEMES = ["OAuth", "Digest", "AWS4-HMAC-SHA256", "Negotiate", "Bearer", "Basic", "token", "Custom-Scheme_1"]


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("header", ["Authorization", "authorization", "Proxy-Authorization", "AUTHORIZATION"])
def test_the_whole_authorization_value_is_redacted_under_any_scheme(header, scheme):
    out = col.redact_secrets(f"gh falhou: {header}: {scheme} {CRED}")
    assert CRED not in out and scheme not in out.split("gh falhou:")[1].replace("<segredo>", "")


@pytest.mark.parametrize("raw", [f'"Authorization": "OAuth {CRED}"', f"Authorization={CRED}", f"'authorization': 'Digest username=\"u\", response=\"{CRED}\"'",
                                 f"Authorization: OAuth oauth_token=\"{CRED}\", oauth_signature=\"x\""])
def test_quoted_json_and_multi_parameter_authorization_values_are_redacted_entirely(raw):
    assert CRED not in col.redact_secrets(raw)


@pytest.mark.parametrize("raw", [f"Authorization: Custom id=a;opaque={CRED}", f"Authorization: Digest realm=x; nonce=y; response={CRED}",
                                 f"Proxy-Authorization: OAuth a=1;b={CRED}"])
def test_parameters_after_a_semicolon_are_part_of_the_header_value_and_are_redacted(raw):
    assert CRED not in col.redact_secrets(raw)


def test_the_next_line_of_the_error_survives_so_it_stays_readable():
    out = col.redact_secrets(f"Authorization: OAuth {CRED}\nHTTP 401 do servidor")
    assert CRED not in out and "HTTP 401 do servidor" in out


@pytest.mark.parametrize("prose", ["authorization denied by the server", "falta authorization no pedido", "unauthorized: HTTP 401"])
def test_the_word_authorization_in_prose_is_untouched(prose):
    assert col.redact_secrets(prose) == prose


@pytest.mark.parametrize("scheme", ["OAuth", "Digest", "AWS4-HMAC-SHA256"])
def test_an_oauth_style_credential_never_reaches_the_panel_or_the_copied_diagnostic(store, tmp_path, scheme):  # noqa: F811
    store.publish("CORRECTION_REQUESTED", "k", "pr:1", {"x": 1})
    ev = store.claim(("CORRECTION_REQUESTED",), "w", 60, job_id="pr:1")
    store.fail(ev, f"gh falhou: Authorization: {scheme} {CRED}", retry_delay=900)
    out = col.collect_store(tmp_path, NOW)
    s = snap(out)
    assert CRED not in s.store_line() and CRED not in str(out.get("last_error")) and CRED not in s.diagnostic()
