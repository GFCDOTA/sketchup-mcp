"""FP-060 MT-06 (#625): o coletor da evidencia E2E nao vaza credencial/e-mail/caminho, nao fixa fluxos no codigo e le o SQLite em modo somente leitura."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/validation/fp060_e2e_evidence.py"
WRAPPER = Path(__file__).resolve().parents[1] / "artifacts/review/fp060/mt06_e2e/2026-11-15/collect_evidence.py"
ce = importlib.import_module("tools.validation.fp060_e2e_evidence")

SECRETS = ["ghp_" + "a" * 36, "github_pat_" + "B" * 40, "Bearer " + "x" * 30, "sk-ant-" + "c" * 30,
           "sk-proj-" + "d" * 40, "sk-" + "e" * 48, "sk-svcacct-" + "f" * 30, "xoxb-" + "1" * 12 + "-" + "g" * 12, "AIza" + "h" * 35,
           "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12, "-----BEGIN RSA PRIVATE KEY-----", "api_key=" + "z" * 20, "password: " + "q" * 12]
WIN_USER_PATH = "C:" + chr(92) + "Users" + chr(92) + "Fulano Silva" + chr(92) + "AppData" + chr(92) + "Local" + chr(92) + "Temp" + chr(92) + "x.json"


@pytest.mark.parametrize("secret", SECRETS)
def test_credentials_are_removed_from_free_text(secret):
    out = ce.scrub(f"falhou com {secret} no meio")
    assert secret not in out and "<token>" in out


def test_emails_and_machine_paths_of_every_style_are_removed():
    text = (f"erro de felip@example.com em {WIN_USER_PATH} e D:/Meus Arquivos/y.db "
            "e /home/fulano/.config/gh e /Users/fulano/Library/z e /e/Claude/data/runs/a.db fim")
    out = ce.scrub(text)
    for leaked in ("felip@example.com", "Fulano", "AppData", "Meus Arquivos", "/home/fulano", "/Users/fulano", "/e/Claude"):
        assert leaked not in out, leaked
    assert "<email>" in out and "<caminho>" in out


def test_clean_applies_to_every_string_in_nested_structures_keys_included():
    data = {"ghp_" + "k" * 30: ["C:/segredo/a.txt", {"deep": "mail a@b.co ghp_" + "z" * 30}], "n": 3, "ok": True}
    cleaned = json.dumps(ce.clean(data))
    ce.assert_clean(cleaned)
    assert "segredo" not in cleaned and "a@b.co" not in cleaned and "ghp_" not in cleaned and '"n": 3' in cleaned


def test_urls_and_timestamps_are_not_mistaken_for_drive_paths():
    text = "https://github.com/o/r/pull/7 as 23:41:25 review:GFCDOTA/x#7:abc"
    assert ce.scrub(text) == text


def test_assert_clean_refuses_anything_the_scrub_missed():
    for bad in ("ghp_" + "q" * 20, "alguem@x.org", WIN_USER_PATH, "/home/u/z"):
        with pytest.raises(SystemExit, match="RECUSADA"):
            ce.assert_clean(f"texto {bad} texto")
    ce.assert_clean("nada sensivel, so numeros 123 e review:GFCDOTA/r#1")


@pytest.mark.parametrize("arg", ["sem-igual", "A=1:2", "A=x:2:db", "A=1:y:db", "=1:2:db", "A=1:2:"])
def test_a_flow_needs_a_name_a_pr_an_issue_and_a_store(arg):
    with pytest.raises(SystemExit, match="fluxo invalido"):
        ce.parse_flow(arg)


def test_the_pr_and_issue_numbers_come_from_the_command_line_not_from_the_code():
    assert ce.parse_flow("D_nova=777:778:/x/gov/store.db") == ("D_nova", 777, 778, Path("/x/gov/store.db"))
    source = SCRIPT.read_text(encoding="utf-8")
    assert "FLOWS" not in source and not any(n in source for n in ("650", "651", "655", "659"))


@pytest.mark.parametrize("dirname", ["a#b", "p%20q", "com espaco", "e&f", "g+h;i"])
def test_the_database_is_opened_read_only_even_when_its_path_has_uri_special_characters(tmp_path, dirname):
    folder = tmp_path / dirname
    folder.mkdir()
    db = folder / "store.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("CREATE TABLE events(id INTEGER PRIMARY KEY, event_type TEXT, idempotency_key TEXT, job_id TEXT, status TEXT, attempt INT,"
                           " max_attempts INT, producer TEXT, created_at REAL, updated_at REAL, error TEXT);"
                           "CREATE TABLE transitions(id INTEGER PRIMARY KEY, event_id INT, at REAL, from_status TEXT, to_status TEXT, actor TEXT, detail TEXT);"
                           "INSERT INTO events(event_type, idempotency_key, status) VALUES('X','k','DONE');")
    names_before = sorted(p.name for p in tmp_path.rglob("*"))
    store = ce.read_store(db)
    assert store["eventos"][0]["idempotency_key"] == "k"
    assert sorted(p.name for p in tmp_path.rglob("*") if not p.name.endswith(("-wal", "-shm"))) == [n for n in names_before if not n.endswith(("-wal", "-shm"))]
    with sqlite3.connect(ce.sqlite_ro_uri(db), uri=True) as conn, pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM events")


def test_a_missing_database_is_an_error_and_is_never_created(tmp_path):
    missing = tmp_path / "x#y" / "store.db"
    with pytest.raises(sqlite3.OperationalError):
        ce.read_store(missing)
    assert not missing.exists() and not (tmp_path / "x").exists()


def test_main_writes_nothing_when_the_final_check_finds_a_leak(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "collect_flow", lambda n, i: {"pr": n, "issue": i, "head_final": "a" * 40, "reviews": [], "nota": "ok"})
    monkeypatch.setattr(ce, "read_store", lambda p: {"eventos": [], "transicoes": []})
    store_arg = "A=1:2:" + (tmp_path / "g" / "s" / "store.db").as_posix()
    out = tmp_path / "out"
    assert ce.main([str(out), store_arg]) == 0 and (out / "evidence.json").is_file()
    monkeypatch.setattr(ce, "clean", lambda v: v)                                                    # se a limpeza falhar, a verificacao final recusa
    monkeypatch.setattr(ce, "collect_flow", lambda n, i: {"pr": n, "issue": i, "head_final": "a" * 40, "reviews": [], "nota": "ghp_" + "w" * 30})
    out2 = tmp_path / "out2"
    with pytest.raises(SystemExit, match="RECUSADA"):
        ce.main([str(out2), store_arg])
    assert not (out2 / "evidence.json").exists()


@pytest.mark.parametrize("path", ["/home/fulano/.config/gh/hosts.yml", "/Users/fulano/Library/z", "/e/Claude/data/runs/a.db", "/tmp/x/y.json", "/mnt/c/Users/f"])
def test_unix_style_machine_paths_are_removed_on_their_own(path):
    out = ce.scrub(f"erro em {path} fim")
    assert path not in out and "<caminho>" in out


@pytest.mark.parametrize("secret", SECRETS)
def test_a_credential_in_a_commit_message_never_reaches_the_written_evidence(secret, tmp_path, monkeypatch):
    flow = {"pr": 1, "issue": 2, "head_final": "a" * 40, "reviews": [], "commits": [{"mensagem": f"corrige {secret} agora"}]}
    monkeypatch.setattr(ce, "collect_flow", lambda n, i: dict(flow))
    monkeypatch.setattr(ce, "read_store", lambda p: {"eventos": [{"error": f"falha com {secret}"}], "transicoes": []})
    out = tmp_path / "out"
    assert ce.main([str(out), "A=1:2:" + (tmp_path / "s.db").as_posix()]) == 0
    written = (out / "evidence.json").read_text(encoding="utf-8")
    assert secret not in written and "<token>" in written
    with pytest.raises(SystemExit, match="RECUSADA"):
        ce.assert_clean(f"texto {secret} texto")                                                   # a verificacao final tambem reconhece o formato


def test_two_different_databases_with_the_same_grandparent_name_are_both_reported(tmp_path, monkeypatch):
    a, b = tmp_path / "runs" / "a" / "store.db", tmp_path / "other" / "b" / "store.db"
    c = tmp_path / "runs" / "c" / "store.db"
    d = tmp_path / "x" / "runs" / "d" / "store.db"
    for db in (a, b, c, d):
        db.parent.mkdir(parents=True)
    assert len({ce.store_id(x) for x in (a, b, c, d)}) == 4
    monkeypatch.setattr(ce, "collect_flow", lambda n, i: {"pr": n, "issue": i, "head_final": "a" * 40, "reviews": []})
    monkeypatch.setattr(ce, "read_store", lambda p: {"eventos": [{"fonte": Path(p).parent.name}], "transicoes": []})
    out = tmp_path / "out"
    ce.main([str(out), f"F1=1:2:{a.as_posix()}", f"F2=3:4:{c.as_posix()}", f"F3=5:6:{a.as_posix()}"])      # F1 e F3 compartilham o banco; F2 e outro com o mesmo avo "runs"
    rep = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
    assert len(rep["stores"]) == 2                                                                   # o compartilhado entra uma vez; o distinto NAO e descartado
    assert rep["fluxos"]["F1"]["store"] == rep["fluxos"]["F3"]["store"] != rep["fluxos"]["F2"]["store"]
    assert {v["eventos"][0]["fonte"] for v in rep["stores"].values()} == {"a", "c"}


def test_the_store_id_does_not_leak_the_machine_path(tmp_path):
    sid = ce.store_id(tmp_path / "x" / "store.db")
    assert sid.startswith("store-") and len(sid) == 14 and str(tmp_path) not in sid


def test_pages_are_merged_structurally_so_a_bracket_pair_inside_a_value_survives():
    assert ce.merge_pages([[{"m": "antes][depois"}]]) == [{"m": "antes][depois"}]                  # pagina unica: intacta
    assert ce.merge_pages([[{"m": "a]["}], [{"m": "[b"}]]) == [{"m": "a]["}, {"m": "[b"}]       # varias paginas: so concatena
    assert ce.merge_pages([]) == []


def test_object_pages_such_as_check_runs_merge_their_lists_and_keep_the_rest():
    merged = ce.merge_pages([{"total_count": 3, "check_runs": [{"n": 1}, {"n": 2}]}, {"total_count": 3, "check_runs": [{"n": 3}]}])
    assert merged["check_runs"] == [{"n": 1}, {"n": 2}, {"n": 3}] and merged["total_count"] == 3
    single = {"state": "open", "labels": [{"name": "x"}]}
    assert ce.merge_pages([single]) == single


@pytest.mark.parametrize("bad", ["texto", {"a": 1}, 3, [[1], {"a": 1}]])
def test_a_malformed_paginated_answer_is_refused(bad):
    with pytest.raises(ValueError):
        ce.merge_pages(bad)


def test_gh_parses_the_slurped_output_without_touching_the_text(monkeypatch):
    payload = json.dumps([[{"mensagem": "antes][depois"}]])
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return type("R", (), {"returncode": 0, "stdout": payload, "stderr": ""})()
    monkeypatch.setattr(ce.subprocess, "run", fake_run)
    assert ce.gh("repos/o/r/pulls/1/commits") == [{"mensagem": "antes][depois"}]
    assert "--slurp" in seen["cmd"] and "--paginate" in seen["cmd"]


# -- 4a revisao do Codex (#660): PEM completo, caminhos Unix quaisquer, check runs de mesmo nome ---------------------------------------------------------
PEM = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA7Zx0aQ1b\nQmFzZTY0Q29ycG8=\n-----END RSA PRIVATE KEY-----"


def test_a_whole_multiline_pem_key_is_removed_not_just_its_header():
    out = ce.scrub(f"antes {PEM} depois")
    assert "MIIEow" not in out and "QmFzZTY0" not in out and "END RSA" not in out and out.startswith("antes <token>") and out.endswith("depois")
    assert "MIIEow" not in ce.scrub("-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASC")                 # sem rodape: ate o fim do texto


def test_a_pem_key_in_a_collected_field_never_reaches_the_written_report(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "collect_flow", lambda n, i: {"pr": n, "issue": i, "head_final": "a" * 40, "reviews": [], "commits": [{"mensagem": f"x {PEM} y"}]})
    monkeypatch.setattr(ce, "read_store", lambda p: {"eventos": [{"error": PEM}], "transicoes": []})
    out = tmp_path / "out"
    assert ce.main([str(out), "A=1:2:" + (tmp_path / "s.db").as_posix()]) == 0
    written = (out / "evidence.json").read_text(encoding="utf-8")
    assert "MIIEow" not in written and "QmFzZTY0" not in written and "PRIVATE KEY" not in written
    with pytest.raises(SystemExit, match="RECUSADA"):
        ce.assert_clean(PEM)


@pytest.mark.parametrize("path", ["/workspace/empresa/projeto/segredo.txt", "/data/runs/a.db", "/srv/app/config.yml", "/Volumes/Disco/x/y.json", "/proc/1/environ"])
def test_any_absolute_unix_path_is_removed_even_outside_the_old_root_list(path):
    out = ce.scrub(f"erro em {path} fim")
    assert path not in out and "<caminho>" in out
    with pytest.raises(SystemExit, match="RECUSADA"):
        ce.assert_clean(f"x {path} y")


def test_urls_relative_paths_and_review_keys_are_not_mistaken_for_machine_paths():
    text = "https://github.com/o/r/pull/7#pullrequestreview-9 review:GFCDOTA/x#7:abc refs/heads/feat/x docs/a/b.md a/b"
    assert ce.scrub(text) == text
    ce.assert_clean(text)


def test_check_runs_with_the_same_name_are_both_preserved_with_id_origin_and_result():
    runs = [{"id": 2, "name": "pytest (py3.12)", "status": "completed", "conclusion": "success", "app": {"slug": "github-actions"}},
            {"id": 1, "name": "pytest (py3.12)", "status": "completed", "conclusion": "failure", "app": {"slug": "github-actions"}},
            {"id": 3, "name": "qg", "status": "in_progress", "conclusion": None, "app": None}]
    out = ce.checks_of(runs)
    assert [(c["id"], c["nome"], c["estado"]) for c in out] == [(1, "pytest (py3.12)", "failure"), (2, "pytest (py3.12)", "success"), (3, "qg", "in_progress")]
    assert out[0]["origem"] == "github-actions" and out[2]["origem"] is None                                       # a falha NAO some atras do sucesso de mesmo nome


# -- 5a revisao do Codex (#660): caminhos UNC; a logica vive em tools/ (o sandbox do revisor nao copia artifacts/) ------------------------------------------
UNC = chr(92) * 2 + "servidor" + chr(92) + "compartilhamento" + chr(92) + "projeto" + chr(92) + "segredo.txt"


@pytest.mark.parametrize("path", [UNC, "//servidor/compartilhamento/projeto/segredo.txt", chr(92) * 2 + "10.0.0.5" + chr(92) + "c$" + chr(92) + "x.db"])
def test_unc_paths_are_removed_and_refused_by_the_final_check(path):
    out = ce.scrub(f"erro em {path} fim")
    assert "servidor" not in out and "compartilhamento" not in out and "10.0.0.5" not in out and "<caminho>" in out
    with pytest.raises(SystemExit, match="RECUSADA"):
        ce.assert_clean(f"x {path} y")


def test_a_unc_path_in_a_collected_field_never_reaches_the_written_report(tmp_path, monkeypatch):
    monkeypatch.setattr(ce, "collect_flow", lambda n, i: {"pr": n, "issue": i, "head_final": "a" * 40, "reviews": [], "commits": [{"mensagem": f"x {UNC} y"}]})
    monkeypatch.setattr(ce, "read_store", lambda p: {"eventos": [{"error": UNC}], "transicoes": []})
    out = tmp_path / "out"
    assert ce.main([str(out), "A=1:2:" + (tmp_path / "s.db").as_posix()]) == 0
    written = (out / "evidence.json").read_text(encoding="utf-8")
    assert "servidor" not in written and "segredo.txt" not in written


def test_urls_with_double_slashes_are_not_mistaken_for_unc_paths():
    text = "https://github.com/o/r/pull/7 http://localhost:8080//x file:///dir ssh://git@host/r"
    assert ce.scrub(text).startswith("https://github.com/o/r/pull/7 http://localhost:8080//x")


def test_the_collector_logic_lives_in_tools_so_the_reviewers_sandbox_can_run_its_tests():
    assert SCRIPT.is_file() and SCRIPT.parts[-3:] == ("tools", "validation", "fp060_e2e_evidence.py")
    assert "artifacts" not in str(ce.__file__.replace(chr(92), "/")).split("/tools/")[-1]
    # o sandbox copia a arvore SEM estas pastas: o modulo testado nao pode depender de nenhuma delas
    for skipped in ("artifacts", "assets", "ops", "runs"):
        assert f"{skipped}/" not in SCRIPT.read_text(encoding="utf-8").replace("artifacts/review/", "")


@pytest.mark.skipif(not WRAPPER.exists(), reason="o sandbox de testes do revisor nao copia artifacts/: o invólucro so existe na arvore completa")
def test_the_versioned_wrapper_is_a_thin_cli_over_the_same_module():
    text = WRAPPER.read_text(encoding="utf-8")
    assert "from tools.validation.fp060_e2e_evidence import main" in text and len(text.splitlines()) < 15
    import subprocess
    import sys
    done = subprocess.run([sys.executable, str(WRAPPER)], capture_output=True, text=True, timeout=60)
    assert done.returncode != 0 and "Uso:" in (done.stderr + done.stdout)                                         # sem argumentos mostra o uso do modulo


# -- 8a revisao do Codex (#660): caminho Unix com espacos ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/home/Joao Silva/projeto/segredo.txt", "/Users/Maria Souza/Documents/x y.db", "/mnt/dados da empresa/a b/c.txt", "/workspace/meu time/projeto/s.txt"])
def test_a_unix_path_with_spaces_is_removed_whole_not_cut_at_the_first_space(path):
    out = ce.scrub(f"erro em {path}")
    for part in ("Silva", "Souza", "empresa", "meu time", "segredo", "projeto"):
        assert part not in out, (part, out)
    assert "<caminho>" in out
    with pytest.raises(SystemExit, match="RECUSADA"):
        ce.assert_clean(f"x {path}")


def test_a_unix_path_with_spaces_never_reaches_the_written_report(tmp_path, monkeypatch):
    path = "/home/Joao Silva/projeto/segredo.txt"
    monkeypatch.setattr(ce, "collect_flow", lambda n, i: {"pr": n, "issue": i, "head_final": "a" * 40, "reviews": [], "commits": [{"mensagem": f"x {path}"}]})
    monkeypatch.setattr(ce, "read_store", lambda p: {"eventos": [{"error": path}], "transicoes": []})
    out = tmp_path / "out"
    assert ce.main([str(out), "A=1:2:" + (tmp_path / "s.db").as_posix()]) == 0
    written = (out / "evidence.json").read_text(encoding="utf-8")
    assert "Silva" not in written and "segredo" not in written


def test_urls_and_plain_prose_after_a_slash_are_not_swallowed_by_the_spaced_pattern():
    text = "veja https://github.com/o/r/pull/7 e refs/heads/feat/x; docs/a/b.md tambem"
    assert ce.scrub(text) == text


@pytest.mark.parametrize("path", ["/custom/Joao Silva/projeto/segredo.txt", "/clientes/Maria de Souza/Meus Documentos/a/b.txt", "/srv2/Equipe Alfa Beta/repo/x.py"])
def test_a_unix_path_with_spaces_under_an_arbitrary_root_is_removed_whole(path):
    out = ce.scrub(f"erro em {path}")
    for part in ("Silva", "Souza", "Alfa", "projeto", "segredo", "Meus"):
        assert part not in out, (part, out)
    with pytest.raises(SystemExit, match="RECUSADA"):
        ce.assert_clean(f"x {path}")


def test_plain_words_and_urls_around_a_path_are_not_swallowed():
    text = "falha em /a/b e depois https://github.com/o/r/pull/7 e texto livre com barra a/b"
    out = ce.scrub(text)
    assert out.startswith("falha em <caminho> e depois https://github.com/o/r/pull/7") and out.endswith("e texto livre com barra a/b")
