"""Durable SQLite event store for the real-CLI lab (stdlib only).

Every event row carries: id, event_type, idempotency_key (UNIQUE), payload,
status, attempt/max_attempts, created_at/updated_at/available_at, and lease
info (lease_owner, lease_token, lease_until). Claims are fenced by a random
lease_token, so a worker whose lease expired (or that was killed and later
reclaimed) can never complete, fail or renew a job someone else now owns.

Status lifecycle:
  PENDING -> RUNNING -> DONE | PENDING (retry) | DLQ | SUPERSEDED
  RECORDED  = fact events that nobody consumes (IMPLEMENT_COMPLETED,
              REVIEW_APPROVED, JOB_FAILED).
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

EVENT_TYPES = (
    "IMPLEMENT_REQUESTED",
    "IMPLEMENT_COMPLETED",
    "REVIEW_REQUESTED",
    "REVIEW_APPROVED",
    "REVIEW_CHANGES_REQUESTED",
    "JOB_FAILED",
)
CONSUMABLE = ("IMPLEMENT_REQUESTED", "REVIEW_REQUESTED", "REVIEW_CHANGES_REQUESTED")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id              INTEGER PRIMARY KEY,
  event_type      TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  job_id          TEXT NOT NULL,
  parent_event_id INTEGER REFERENCES events(id),
  payload         TEXT NOT NULL,
  status          TEXT NOT NULL,
  attempt         INTEGER NOT NULL DEFAULT 0,
  max_attempts    INTEGER NOT NULL DEFAULT 3,
  created_at      REAL NOT NULL,
  updated_at      REAL NOT NULL,
  available_at    REAL NOT NULL,
  lease_owner     TEXT,
  lease_token     TEXT,
  lease_until     REAL NOT NULL DEFAULT 0,
  result          TEXT,
  error           TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_claim ON events(event_type, status, available_at);
CREATE TABLE IF NOT EXISTS transitions (
  id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
  at REAL NOT NULL, from_status TEXT, to_status TEXT NOT NULL,
  actor TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS subprocess_runs (
  id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
  agent TEXT NOT NULL, argv TEXT NOT NULL, cwd TEXT NOT NULL,
  pid INTEGER, started_at REAL NOT NULL, ended_at REAL,
  exit_code INTEGER, timed_out INTEGER NOT NULL DEFAULT 0,
  stdout_path TEXT, stderr_path TEXT, outcome TEXT
);
"""


class LeaseLost(RuntimeError):
    """The caller no longer owns the lease; its result must not be committed."""


class EventStore:
    def __init__(self, path: str | Path, clock=time.time):
        self.path = str(path)
        self.clock = clock
        with self._conn() as db:
            db.executescript(SCHEMA)

    # -- plumbing -----------------------------------------------------------
    @contextmanager
    def _conn(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        with closing(db):
            yield db

    @contextmanager
    def _tx(self):
        with self._conn() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    @staticmethod
    def _log(db, event_id, frm, to, actor, detail, now):
        db.execute(
            "INSERT INTO transitions(event_id,at,from_status,to_status,actor,detail) VALUES(?,?,?,?,?,?)",
            (event_id, now, frm, to, actor, detail),
        )

    # -- publishing ---------------------------------------------------------
    def publish(self, event_type, idempotency_key, job_id, payload, *, parent_event_id=None,
                max_attempts=3, actor="publisher"):
        """Idempotent publish. Returns (event_id, created: bool).

        A duplicate idempotency key never creates a second job and never
        overwrites the original payload (first writer wins)."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {event_type!r}")
        status = "PENDING" if event_type in CONSUMABLE else "RECORDED"
        now = self.clock()
        with self._tx() as db:
            cur = db.execute(
                """INSERT OR IGNORE INTO events(event_type,idempotency_key,job_id,parent_event_id,payload,
                   status,max_attempts,created_at,updated_at,available_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (event_type, idempotency_key, job_id, parent_event_id, json.dumps(payload, sort_keys=True),
                 status, max_attempts, now, now, now),
            )
            row = db.execute("SELECT id FROM events WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            created = cur.rowcount == 1
            if created:
                self._log(db, row["id"], None, status, actor, f"published {event_type}", now)
            return row["id"], created

    # -- consuming ----------------------------------------------------------
    def claim(self, event_types, owner, lease_seconds):
        """Atomically claim the oldest eligible event (PENDING & available, or
        RUNNING with an expired lease). Returns a dict or None."""
        if isinstance(event_types, str):
            event_types = (event_types,)
        now = self.clock()
        marks = ",".join("?" * len(event_types))
        with self._tx() as db:
            job = db.execute(
                f"""SELECT * FROM events WHERE event_type IN ({marks}) AND
                    ((status='PENDING' AND available_at<=?) OR (status='RUNNING' AND lease_until<=?))
                    ORDER BY id LIMIT 1""",
                (*event_types, now, now),
            ).fetchone()
            if not job:
                return None
            token = uuid.uuid4().hex
            detail = "claimed" if job["status"] == "PENDING" else f"reclaimed expired lease of {job['lease_owner']}"
            db.execute(
                """UPDATE events SET status='RUNNING', attempt=attempt+1, lease_owner=?, lease_token=?,
                   lease_until=?, updated_at=? WHERE id=?""",
                (owner, token, now + lease_seconds, now, job["id"]),
            )
            self._log(db, job["id"], job["status"], "RUNNING", owner, f"{detail}; attempt {job['attempt'] + 1}", now)
            claimed = dict(db.execute("SELECT * FROM events WHERE id=?", (job["id"],)).fetchone())
            claimed["payload"] = json.loads(claimed["payload"])
            return claimed

    def _owned_update(self, db, ev, sql, params, to_status, detail, now):
        cur = db.execute(
            sql + " WHERE id=? AND lease_token=? AND status='RUNNING' AND lease_until>?",
            (*params, ev["id"], ev["lease_token"], now),
        )
        if cur.rowcount != 1:
            raise LeaseLost(f"event {ev['id']}: lease lost; {to_status} not committed")
        self._log(db, ev["id"], "RUNNING", to_status, ev["lease_owner"], detail, now)

    def renew(self, ev, lease_seconds):
        now = self.clock()
        with self._tx() as db:
            cur = db.execute(
                "UPDATE events SET lease_until=?, updated_at=? WHERE id=? AND lease_token=? AND status='RUNNING' AND lease_until>?",
                (now + lease_seconds, now, ev["id"], ev["lease_token"], now),
            )
            return cur.rowcount == 1

    def complete(self, ev, result, follow_ups=()):
        """Mark DONE and publish follow-up events in the SAME transaction
        (transactional outbox: no completed job without its next event)."""
        now = self.clock()
        with self._tx() as db:
            self._owned_update(db, ev, "UPDATE events SET status='DONE', result=?, lease_until=0, updated_at=?",
                               (json.dumps(result, sort_keys=True), now), "DONE", "completed", now)
            ids = []
            for f in follow_ups:
                status = "PENDING" if f["event_type"] in CONSUMABLE else "RECORDED"
                cur = db.execute(
                    """INSERT OR IGNORE INTO events(event_type,idempotency_key,job_id,parent_event_id,payload,
                       status,max_attempts,created_at,updated_at,available_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (f["event_type"], f["idempotency_key"], ev["job_id"], ev["id"],
                     json.dumps(f["payload"], sort_keys=True), status, f.get("max_attempts", 3), now, now, now),
                )
                row = db.execute("SELECT id FROM events WHERE idempotency_key=?", (f["idempotency_key"],)).fetchone()
                if cur.rowcount == 1:
                    self._log(db, row["id"], None, status, ev["lease_owner"], f"published {f['event_type']} by event {ev['id']}", now)
                ids.append(row["id"])
            return ids

    def fail(self, ev, reason, retry_delay=1.0):
        """Retry (back to PENDING) or dead-letter when attempts are exhausted.
        Dead-lettering also records a JOB_FAILED fact in the same transaction."""
        now = self.clock()
        to = "DLQ" if ev["attempt"] >= ev["max_attempts"] else "PENDING"
        with self._tx() as db:
            self._owned_update(db, ev, "UPDATE events SET status=?, error=?, available_at=?, lease_until=0, updated_at=?",
                               (to, reason[:2000], now + retry_delay, now), to, f"failed: {reason[:300]}", now)
            if to == "DLQ":
                key = f"{ev['job_id']}:job_failed:dlq:{ev['id']}"
                db.execute(
                    """INSERT OR IGNORE INTO events(event_type,idempotency_key,job_id,parent_event_id,payload,
                       status,created_at,updated_at,available_at) VALUES('JOB_FAILED',?,?,?,?, 'RECORDED',?,?,?)""",
                    (key, ev["job_id"], ev["id"],
                     json.dumps({"reason": "dead-lettered", "event_type": ev["event_type"], "error": reason[:500]}),
                     now, now, now),
                )
            return to

    def supersede(self, ev, reason):
        """Discard a claimed event that refers to an outdated artifact version."""
        now = self.clock()
        with self._tx() as db:
            self._owned_update(db, ev, "UPDATE events SET status='SUPERSEDED', error=?, lease_until=0, updated_at=?",
                               (reason, now), "SUPERSEDED", reason, now)

    # -- subprocess audit ---------------------------------------------------
    def run_started(self, event_id, agent, argv, cwd, pid, stdout_path, stderr_path):
        with self._tx() as db:
            return db.execute(
                """INSERT INTO subprocess_runs(event_id,agent,argv,cwd,pid,started_at,stdout_path,stderr_path)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (event_id, agent, json.dumps(argv), str(cwd), pid, self.clock(), str(stdout_path), str(stderr_path)),
            ).lastrowid

    def run_finished(self, run_id, exit_code, timed_out, outcome):
        with self._tx() as db:
            db.execute("UPDATE subprocess_runs SET ended_at=?, exit_code=?, timed_out=?, outcome=? WHERE id=?",
                       (self.clock(), exit_code, int(timed_out), outcome, run_id))

    # -- reads --------------------------------------------------------------
    def events(self, job_id=None):
        with self._conn() as db:
            q, p = ("SELECT * FROM events WHERE job_id=? ORDER BY id", (job_id,)) if job_id else ("SELECT * FROM events ORDER BY id", ())
            return [dict(r) for r in db.execute(q, p)]

    def get(self, event_id):
        with self._conn() as db:
            r = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            return dict(r) if r else None

    def transitions(self):
        with self._conn() as db:
            return [dict(r) for r in db.execute("SELECT * FROM transitions ORDER BY id")]

    def runs(self):
        with self._conn() as db:
            return [dict(r) for r in db.execute("SELECT * FROM subprocess_runs ORDER BY id")]

    def job_terminal(self, job_id):
        """A job ends with REVIEW_APPROVED or JOB_FAILED."""
        with self._conn() as db:
            r = db.execute(
                "SELECT event_type FROM events WHERE job_id=? AND event_type IN ('REVIEW_APPROVED','JOB_FAILED') ORDER BY id LIMIT 1",
                (job_id,),
            ).fetchone()
            return r["event_type"] if r else None
