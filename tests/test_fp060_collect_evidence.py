"""FP-060 MT-06 (#625): o coletor da evidencia E2E nao vaza credencial/e-mail/caminho, nao fixa fluxos no codigo e le o SQLite em modo somente leitura."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "artifacts/review/fp060/mt06_e2e/2026-11-15/collect_evidence.py"
spec = importlib.util.spec_from_file_location("collect_evidence_under_test", SCRIPT)
ce = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ce)

SECRETS = ["ghp_" + "a" * 36, "github_pat_" + "B" * 40, "Bearer " + "x" * 30, "sk-ant-" + "c" * 30]
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
