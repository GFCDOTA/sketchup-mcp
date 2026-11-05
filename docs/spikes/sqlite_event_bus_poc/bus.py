"""Standalone durable event-driven proof of concept. Python stdlib only."""
from __future__ import annotations
import json
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
 id INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL,
 kind TEXT NOT NULL, payload TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
 available_at REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
 owner TEXT, result TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS outputs (
 event_key TEXT PRIMARY KEY, result TEXT NOT NULL
);
"""

class Bus:
 def __init__(self, path):
  self.path = str(path)
  with self.db() as db: db.executescript(SCHEMA)
 def db(self):
  # closing(): sqlite3's own context manager commits but never closes, which
  # leaks the file handle and breaks temp-dir cleanup on Windows.
  db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
  db.row_factory = sqlite3.Row
  db.execute('PRAGMA busy_timeout=10000')
  db.execute('PRAGMA journal_mode=WAL')
  return closing(db)
 def publish(self, event_key, kind, payload):
  with self.db() as db:
   db.execute('INSERT OR IGNORE INTO jobs(event_key,kind,payload) VALUES(?,?,?)',
              (event_key,kind,json.dumps(payload)))
   return db.execute('SELECT id FROM jobs WHERE event_key=?',(event_key,)).fetchone()['id']
 def claim(self, kind, owner, lease_seconds=30, now=None):
  now = time.time() if now is None else now
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   try:
    job = db.execute("""SELECT * FROM jobs WHERE kind=? AND
       (state='PENDING' AND available_at<=? OR state='RUNNING' AND lease_until<=?)
       ORDER BY id LIMIT 1""", (kind,now,now)).fetchone()
    if job:
     db.execute("""UPDATE jobs SET state='RUNNING', attempts=attempts+1,
         owner=?, lease_until=? WHERE id=?""",(owner,now+lease_seconds,job['id']))
    db.execute('COMMIT')
   except Exception:
    db.execute('ROLLBACK'); raise
   return dict(job) if job else None
 def finish(self, job, owner, result, now=None):
  now = time.time() if now is None else now
  with self.db() as db:
   db.execute('BEGIN IMMEDIATE')
   try:
    changed = db.execute("""UPDATE jobs SET state='DONE', result=?, lease_until=0
      WHERE id=? AND owner=? AND state='RUNNING' AND lease_until>?""",
      (result,job['id'],owner,now)).rowcount
    if changed:
     db.execute('INSERT OR IGNORE INTO outputs(event_key,result) VALUES(?,?)',
       (job['event_key'],result))
    db.execute('COMMIT')
   except Exception:
    db.execute('ROLLBACK'); raise
   return bool(changed)
 def fail(self, job, owner, reason, max_attempts=3, now=None):
  now = time.time() if now is None else now
  state = 'DLQ' if job['attempts']+1>=max_attempts else 'PENDING'
  with self.db() as db:
   return bool(db.execute("""UPDATE jobs SET state=?,error=?,available_at=?,lease_until=0
    WHERE id=? AND owner=? AND state='RUNNING' AND lease_until>?""",
     (state,reason,now+0.1,job['id'],owner,now)).rowcount)
 def rows(self):
  with self.db() as db: return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY id')]

def process_one(bus,kind,owner,command=None):
 """Run a real short-lived subprocess, never a mock in-process model."""
 job = bus.claim(kind,owner)
 if not job: return False
 payload = json.loads(job['payload'])
 args = command or [sys.executable,str(Path(__file__).with_name('agent.py')),kind]
 try:
  done = subprocess.run(args, input=json.dumps(payload),capture_output=True,text=True,timeout=10)
  if done.returncode: bus.fail(job,owner,done.stderr.strip() or f'exit {done.returncode}')
  else:
   if not bus.finish(job,owner,done.stdout.strip()):
    raise RuntimeError('lease lost; output not committed')
 except (subprocess.TimeoutExpired,OSError) as exc: bus.fail(job,owner,str(exc))
 return True
