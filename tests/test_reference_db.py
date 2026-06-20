"""Contract tests pro reference_db — índice SQLite do reference_lab (M1+M3)."""
import sqlite3

import pytest

from tools import reference_db as rdb


@pytest.fixture()
def con(tmp_path, monkeypatch):
    """DB em tmp, mas ingerindo o reference_lab REAL do repo (contract)."""
    monkeypatch.setattr(rdb, "DB_PATH", tmp_path / "reference.db")
    c = rdb.connect()
    rdb.init(c)
    rdb.ingest(c)
    yield c
    c.close()


def test_ingest_indexa_cards_themes_e_renders(con):
    kinds = dict(con.execute("SELECT kind, COUNT(*) FROM reference GROUP BY kind").fetchall())
    assert kinds.get("card", 0) > 0, "deveria indexar cards/*.json"
    assert kinds.get("theme_preset", 0) > 0, "deveria indexar themes/*.json"
    assert kinds.get("render", 0) > 0, "deveria indexar kitchen_angles/*.png (M3)"


def test_query_por_tema_filtra(con):
    rows = rdb.query(con, kind="render", theme="black_wood_gold")
    assert rows, "deveria achar renders black_wood_gold"
    assert all(r["theme"] == "black_wood_gold" for r in rows)


def test_intermediarios_vray_sao_ignorados(con):
    slugs = [r["slug"] for r in con.execute("SELECT slug FROM reference").fetchall()]
    assert not any(s.endswith(".denoiser") or s.endswith(".effectsResult") for s in slugs)


def test_ingest_idempotente(con):
    before = con.execute("SELECT COUNT(*) FROM reference").fetchone()[0]
    rdb.ingest(con)  # 2ª vez
    after = con.execute("SELECT COUNT(*) FROM reference").fetchone()[0]
    assert before == after, "re-ingest não pode duplicar (UPSERT por slug)"


def test_slug_unico(con):
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO reference (slug, kind, path) VALUES "
                    "((SELECT slug FROM reference LIMIT 1), 'render', 'x.png')")
