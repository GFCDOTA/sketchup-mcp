"""event_store.py — Durable SQLite event store (FP-060 P1, Issue #606).

Promoted from the PoC in docs/spikes/sqlite_event_bus_poc/event_store.py.

Every event row carries the canonical envelope (SPEC §5.1): event_id (UUID),
event_type, aggregate_type, idempotency_key (UNIQUE), job_id, correlation_id,
causation (parent_event_id), producer, payload, and lease info for fenced
claims.

Status lifecycle:
  PENDING -> RUNNING -> DONE | PENDING (retry) | DLQ | SUPERSEDED
  RECORDED = fact events that nobody consumes.

Transactional outbox: external side effects (GitHub API calls) are queued in
the same transaction as event completion, ensuring no completed job without
its side effects queued.

Properties (SPEC §6.2): WAL, configurable busy_timeout, explicit close
(D-060-01), atomic claim/update, transactional outbox, fenced lease tokens.

The aggregate identity is (aggregate_type, job_id); producers must use a
stable job_id across all events for the same PR. Outbox delivery is at least
once: publishers must reconcile unknown outcomes and use idempotency keys.
Lease fencing protects database writes, not an already-issued remote call.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

EVENT_TYPES = frozenset({
    "ISSUE_READY", "PR_OPENED", "PR_HEAD_UPDATED", "CI_PASSED", "CI_FAILED",
    "GITHUB_REVIEW_SUBMITTED", "PR_MERGED", "ISSUE_UNBLOCKED",
    "IMPLEMENT_REQUESTED", "IMPLEMENT_STARTED", "IMPLEMENT_COMPLETED",
    "IMPLEMENT_FAILED", "CORRECTION_REQUESTED",
    "REVIEW_REQUESTED", "REVIEW_STARTED", "REVIEW_APPROVED",
    "REVIEW_CHANGES_REQUESTED", "REVIEW_BLOCKED",
    "JOB_RETRY_SCHEDULED", "JOB_SUPERSEDED", "JOB_FAILED", "JOB_DEAD_LETTERED",
    "PUBLISH_REQUESTED", "PUBLISH_COMPLETED", "PUBLISH_FAILED",
    "WORKFLOW_COMPLETED",
})

CONSUMABLE = frozenset({
    "IMPLEMENT_REQUESTED", "CORRECTION_REQUESTED",
    "REVIEW_REQUESTED", "REVIEW_CHANGES_REQUESTED",
    "PUBLISH_REQUESTED",
})

PENDING = ("queued", "in_progress", "pending", "waiting", "requested", None)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id              INTEGER PRIMARY KEY,
  event_id        TEXT    NOT NULL,
  event_type      TEXT    NOT NULL,
  aggregate_type  TEXT    NOT NULL DEFAULT 'pull_request',
  idempotency_key TEXT    NOT NULL UNIQUE,
  job_id          TEXT    NOT NULL,
  correlation_id  TEXT    NOT NULL DEFAULT '',
  parent_event_id INTEGER REFERENCES events(id),
  producer        TEXT    NOT NULL DEFAULT 'coordinator',
  payload         TEXT    NOT NULL,
  status          TEXT    NOT NULL,
  attempt         INTEGER NOT NULL DEFAULT 0,
  max_attempts    INTEGER NOT NULL DEFAULT 3,
  created_at      REAL    NOT NULL,
  updated_at      REAL    NOT NULL,
  available_at    REAL    NOT NULL,
  lease_owner     TEXT,
  lease_token     TEXT,
  lease_until     REAL    NOT NULL DEFAULT 0,
  result          TEXT,
  error           TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_claim
  ON events(event_type, status, available_at);
CREATE INDEX IF NOT EXISTS ix_events_aggregate
  ON events(aggregate_type, job_id, status, lease_until);

CREATE TABLE IF NOT EXISTS transitions (
  id          INTEGER PRIMARY KEY,
  event_id    INTEGER NOT NULL REFERENCES events(id),
  at          REAL    NOT NULL,
  from_status TEXT,
  to_status   TEXT    NOT NULL,
  actor       TEXT,
  detail      TEXT
);

CREATE TABLE IF NOT EXISTS subprocess_runs (
  id          INTEGER PRIMARY KEY,
  event_id    INTEGER NOT NULL REFERENCES events(id),
  agent       TEXT    NOT NULL,
  argv        TEXT    NOT NULL,
  cwd         TEXT    NOT NULL,
  pid         INTEGER,
  started_at  REAL    NOT NULL,
  ended_at    REAL,
  exit_code   INTEGER,
  timed_out   INTEGER NOT NULL DEFAULT 0,
  stdout_path TEXT,
  stderr_path TEXT,
  outcome     TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
  id              INTEGER PRIMARY KEY,
  event_id        INTEGER NOT NULL REFERENCES events(id),
  target          TEXT    NOT NULL,
  operation       TEXT    NOT NULL,
  payload         TEXT    NOT NULL,
  idempotency_key TEXT    NOT NULL UNIQUE,
  status          TEXT    NOT NULL DEFAULT 'PENDING',
  attempts        INTEGER NOT NULL DEFAULT 0,
  max_attempts    INTEGER NOT NULL DEFAULT 5,
  available_at    REAL    NOT NULL,
  lease_owner     TEXT,
  lease_token     TEXT,
  lease_until     REAL    NOT NULL DEFAULT 0,
  created_at      REAL    NOT NULL,
  updated_at      REAL    NOT NULL,
  error           TEXT
);
CREATE INDEX IF NOT EXISTS ix_outbox_pending ON outbox(status, target);
"""


class LeaseLost(RuntimeError):
    """The caller no longer owns the lease; its result must not be committed."""


class EventStore:
    def __init__(self, path: str | Path, *, clock=time.time, busy_timeout_ms: int = 15000):
        self.path = str(path)
        self.clock = clock
        self._busy_timeout_ms = busy_timeout_ms
        with self._conn() as db:
            db.executescript(_SCHEMA)
            db.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @contextmanager
    def _conn(self):
        db = sqlite3.connect(self.path, timeout=self._busy_timeout_ms / 1000, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
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
    def publish(self, event_type: str, idempotency_key: str, job_id: str, payload: dict, *,
                parent_event_id: int | None = None, correlation_id: str = "",
                aggregate_type: str = "pull_request", producer: str = "coordinator",
                max_attempts: int = 3, actor: str = "publisher") -> tuple[int, bool]:
        """Idempotent publish. Returns (event_id, created: bool).

        A duplicate idempotency key never creates a second job and never
        overwrites the original payload (first writer wins)."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {event_type!r}")
        status = "PENDING" if event_type in CONSUMABLE else "RECORDED"
        now = self.clock()
        eid = uuid.uuid4().hex
        with self._tx() as db:
            cur = db.execute(
                """INSERT OR IGNORE INTO events(event_id,event_type,aggregate_type,idempotency_key,
                   job_id,correlation_id,parent_event_id,producer,payload,status,max_attempts,
                   created_at,updated_at,available_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (eid, event_type, aggregate_type, idempotency_key, job_id,
                 correlation_id, parent_event_id, producer,
                 json.dumps(payload, sort_keys=True), status, max_attempts, now, now, now),
            )
            row = db.execute("SELECT id FROM events WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            created = cur.rowcount == 1
            if created:
                self._log(db, row["id"], None, status, actor, f"published {event_type}", now)
            return row["id"], created

    @staticmethod
    def _record_dlq_fact(db, ev, reason, now):
        key = f"{ev['job_id']}:job_failed:dlq:{ev['id']}"
        db.execute(
            """INSERT OR IGNORE INTO events(event_id,event_type,aggregate_type,idempotency_key,job_id,
               correlation_id,parent_event_id,payload,status,created_at,updated_at,available_at)
               VALUES(?,?,?,?,?,?,?,?,'RECORDED',?,?,?)""",
            (uuid.uuid4().hex, "JOB_FAILED", ev["aggregate_type"], key, ev["job_id"],
             ev["correlation_id"], ev["id"],
             json.dumps({"reason": "dead-lettered", "event_type": ev["event_type"], "error": reason[:500]}),
             now, now, now),
        )

    # -- consuming ----------------------------------------------------------
    def claim(self, event_types, owner: str, lease_seconds: float) -> dict | None:
        """Atomically claim the oldest eligible event (PENDING & available, or
        RUNNING with an expired lease), excluding any live aggregate owner."""
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if isinstance(event_types, str):
            event_types = (event_types,)
        marks = ",".join("?" * len(event_types))
        with self._tx() as db:
            now = self.clock()
            # Reap exhausted leases across event types before selecting work, so a
            # different consumer also records the terminal state and frees the aggregate.
            expired = db.execute(
                """SELECT * FROM events WHERE status='RUNNING' AND lease_until<=?
                   AND attempt>=max_attempts""", (now,),
            ).fetchall()
            for ev in expired:
                reason = "lease expired after final attempt"
                db.execute(
                    """UPDATE events SET status='DLQ', error=?, lease_owner=NULL,
                       lease_token=NULL, lease_until=0, updated_at=? WHERE id=?""",
                    (reason, now, ev["id"]),
                )
                self._log(db, ev["id"], "RUNNING", "DLQ", owner, reason, now)
                self._record_dlq_fact(db, ev, reason, now)
            job = db.execute(
                f"""SELECT e.* FROM events e WHERE e.event_type IN ({marks}) AND e.attempt<e.max_attempts AND
                    ((e.status='PENDING' AND e.available_at<=?) OR (e.status='RUNNING' AND e.lease_until<=?))
                    AND NOT EXISTS (SELECT 1 FROM events active
                        WHERE active.aggregate_type=e.aggregate_type AND active.job_id=e.job_id
                        AND active.id<>e.id AND active.status='RUNNING' AND active.lease_until>?)
                    ORDER BY e.id LIMIT 1""",
                (*event_types, now, now, now),
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

    def renew(self, ev: dict, lease_seconds: float) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._tx() as db:
            now = self.clock()
            cur = db.execute(
                "UPDATE events SET lease_until=?, updated_at=? WHERE id=? AND lease_token=? AND status='RUNNING' AND lease_until>?",
                (now + lease_seconds, now, ev["id"], ev["lease_token"], now),
            )
            return cur.rowcount == 1

    def complete(self, ev: dict, result: dict, follow_ups=(), outbox_entries=()) -> tuple[list[int], list[int]]:
        """Mark DONE and publish follow-up events + outbox entries in the SAME
        transaction (transactional outbox: no completed job without its
        side effects queued). Returns (follow_up_ids, outbox_ids)."""
        with self._tx() as db:
            now = self.clock()
            self._owned_update(db, ev, "UPDATE events SET status='DONE', result=?, lease_until=0, updated_at=?",
                               (json.dumps(result, sort_keys=True), now), "DONE", "completed", now)
            fids: list[int] = []
            for f in follow_ups:
                status = "PENDING" if f["event_type"] in CONSUMABLE else "RECORDED"
                cor = f.get("correlation_id", ev.get("correlation_id", ""))
                cur = db.execute(
                    """INSERT OR IGNORE INTO events(event_id,event_type,aggregate_type,idempotency_key,
                       job_id,correlation_id,parent_event_id,producer,payload,status,max_attempts,
                       created_at,updated_at,available_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (uuid.uuid4().hex, f["event_type"], f.get("aggregate_type", ev.get("aggregate_type", "pull_request")),
                     f["idempotency_key"], ev["job_id"], cor, ev["id"],
                     f.get("producer", ev.get("producer", "coordinator")),
                     json.dumps(f["payload"], sort_keys=True), status,
                     f.get("max_attempts", 3), now, now, now),
                )
                row = db.execute("SELECT id FROM events WHERE idempotency_key=?", (f["idempotency_key"],)).fetchone()
                if cur.rowcount == 1:
                    self._log(db, row["id"], None, status, ev["lease_owner"],
                              f"published {f['event_type']} by event {ev['id']}", now)
                fids.append(row["id"])
            oids: list[int] = []
            for o in outbox_entries:
                cur = db.execute(
                    """INSERT OR IGNORE INTO outbox(event_id,target,operation,payload,idempotency_key,
                       max_attempts,created_at,updated_at,available_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (ev["id"], o["target"], o["operation"],
                     json.dumps(o["payload"], sort_keys=True), o["idempotency_key"],
                     o.get("max_attempts", 5), now, now, now),
                )
                row = db.execute("SELECT id FROM outbox WHERE idempotency_key=?", (o["idempotency_key"],)).fetchone()
                oids.append(row["id"])
            return fids, oids

    def fail(self, ev: dict, reason: str, retry_delay: float = 1.0) -> str:
        """Retry (back to PENDING) or dead-letter when attempts are exhausted.
        Dead-lettering also records a JOB_FAILED fact in the same transaction."""
        to = "DLQ" if ev["attempt"] >= ev["max_attempts"] else "PENDING"
        with self._tx() as db:
            now = self.clock()
            self._owned_update(db, ev, "UPDATE events SET status=?, error=?, available_at=?, lease_until=0, updated_at=?",
                               (to, reason[:2000], now + retry_delay, now), to, f"failed: {reason[:300]}", now)
            if to == "DLQ":
                self._record_dlq_fact(db, ev, reason, now)
            return to

    def supersede(self, ev: dict, reason: str) -> None:
        """Discard a claimed event that refers to an outdated artifact version."""
        with self._tx() as db:
            now = self.clock()
            self._owned_update(db, ev, "UPDATE events SET status='SUPERSEDED', error=?, lease_until=0, updated_at=?",
                               (reason, now), "SUPERSEDED", reason, now)

    # -- subprocess audit ---------------------------------------------------
    def run_started(self, event_id: int, agent: str, argv: list, cwd: str | Path,
                    pid: int, stdout_path: str | Path, stderr_path: str | Path) -> int:
        with self._tx() as db:
            return db.execute(
                """INSERT INTO subprocess_runs(event_id,agent,argv,cwd,pid,started_at,stdout_path,stderr_path)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (event_id, agent, json.dumps(argv), str(cwd), pid, self.clock(),
                 str(stdout_path), str(stderr_path)),
            ).lastrowid

    def run_finished(self, run_id: int, exit_code: int, timed_out: bool, outcome: str) -> None:
        with self._tx() as db:
            db.execute("UPDATE subprocess_runs SET ended_at=?, exit_code=?, timed_out=?, outcome=? WHERE id=?",
                       (self.clock(), exit_code, int(timed_out), outcome, run_id))

    # -- outbox reads -------------------------------------------------------
    def pending_outbox(self, target: str | None = None) -> list[dict]:
        """Inspection only. Publishers must obtain ownership via claim_outbox."""
        with self._conn() as db:
            if target:
                rows = db.execute("SELECT * FROM outbox WHERE status='PENDING' AND target=? ORDER BY id", (target,))
            else:
                rows = db.execute("SELECT * FROM outbox WHERE status='PENDING' ORDER BY id")
            return [dict(r) for r in rows]

    def claim_outbox(self, owner: str, lease_seconds: float, target: str | None = None) -> dict | None:
        """Claim before any external effect. A reclaimed entry gets a new token.

        A crash after the remote call is an unknown outcome: the next publisher
        must reconcile the idempotency key before sending again.
        """
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._tx() as db:
            now = self.clock()
            db.execute("""UPDATE outbox SET status='DLQ', lease_until=0, updated_at=?,
                       error='lease expired after final attempt; remote outcome requires reconciliation'
                       WHERE status='RUNNING' AND lease_until<=? AND attempts>=max_attempts""", (now, now))
            row = db.execute(
                """SELECT * FROM outbox WHERE attempts<max_attempts AND
                   ((status='PENDING' AND available_at<=?) OR (status='RUNNING' AND lease_until<=?))
                   AND (? IS NULL OR target=?) ORDER BY id LIMIT 1""", (now, now, target, target),
            ).fetchone()
            if row is None:
                return None
            db.execute("""UPDATE outbox SET status='RUNNING', attempts=attempts+1,
                       lease_owner=?, lease_token=?, lease_until=?, updated_at=? WHERE id=?""",
                       (owner, uuid.uuid4().hex, now + lease_seconds, now, row['id']))
            return dict(db.execute("SELECT * FROM outbox WHERE id=?", (row['id'],)).fetchone())

    def _owned_outbox_update(self, db, entry: dict, sql: str, params: tuple, now: float) -> None:
        cur = db.execute(sql + " WHERE id=? AND lease_token=? AND status='RUNNING' AND lease_until>?",
                         (*params, entry['id'], entry['lease_token'], now))
        if cur.rowcount != 1:
            raise LeaseLost(f"outbox {entry['id']}: lease lost; update refused")

    def renew_outbox(self, entry: dict, lease_seconds: float) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._tx() as db:
            now = self.clock()
            cur = db.execute("""UPDATE outbox SET lease_until=?, updated_at=? WHERE id=?
                             AND lease_token=? AND status='RUNNING' AND lease_until>?""",
                             (now + lease_seconds, now, entry['id'], entry['lease_token'], now))
            return cur.rowcount == 1

    def complete_outbox(self, entry: dict) -> None:
        """Only the current unexpired owner can acknowledge delivery."""
        with self._tx() as db:
            now = self.clock()
            self._owned_outbox_update(db, entry,
                                     "UPDATE outbox SET status='DONE', lease_until=0, updated_at=?", (now,), now)

    def fail_outbox(self, entry: dict, reason: str, retry_delay: float = 1.0) -> str:
        """Terminal states are immutable; delayed/duplicate outcomes are fenced."""
        with self._tx() as db:
            now = self.clock()
            row = db.execute("SELECT attempts, max_attempts FROM outbox WHERE id=?", (entry['id'],)).fetchone()
            if row is None:
                raise LeaseLost(f"outbox {entry['id']}: missing entry")
            to = "DLQ" if row['attempts'] >= row['max_attempts'] else "PENDING"
            self._owned_outbox_update(db, entry,
                                     "UPDATE outbox SET status=?, error=?, available_at=?, lease_until=0, updated_at=?",
                                     (to, reason[:2000], now + retry_delay, now), now)
            return to

    # -- event reads --------------------------------------------------------
    def events(self, job_id: str | None = None) -> list[dict]:
        with self._conn() as db:
            if job_id:
                rows = db.execute("SELECT * FROM events WHERE job_id=? ORDER BY id", (job_id,))
            else:
                rows = db.execute("SELECT * FROM events ORDER BY id")
            return [dict(r) for r in rows]

    def get(self, event_id: int) -> dict | None:
        with self._conn() as db:
            r = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            return dict(r) if r else None

    def transitions(self) -> list[dict]:
        with self._conn() as db:
            return [dict(r) for r in db.execute("SELECT * FROM transitions ORDER BY id")]

    def runs(self) -> list[dict]:
        with self._conn() as db:
            return [dict(r) for r in db.execute("SELECT * FROM subprocess_runs ORDER BY id")]

    def job_terminal(self, job_id: str) -> str | None:
        with self._conn() as db:
            r = db.execute(
                "SELECT event_type FROM events WHERE job_id=? AND event_type IN ('REVIEW_APPROVED','JOB_FAILED') ORDER BY id LIMIT 1",
                (job_id,),
            ).fetchone()
            return r["event_type"] if r else None

    def stats(self) -> dict:
        """Snapshot for observability (SPEC §10)."""
        with self._conn() as db:
            counts = {}
            for s in ("PENDING", "RUNNING", "DONE", "DLQ", "SUPERSEDED", "RECORDED"):
                counts[s] = db.execute("SELECT COUNT(*) FROM events WHERE status=?", (s,)).fetchone()[0]
            outbox_pending = db.execute("SELECT COUNT(*) FROM outbox WHERE status='PENDING'").fetchone()[0]
            return {"events": counts, "outbox_pending": outbox_pending, "schema_version": SCHEMA_VERSION}
