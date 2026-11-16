"""rate_limit.py — limite de uso da conta do revisor como ESTADO persistente, nao como falha (FP-060, requisito de resiliencia).

Problema real (2026-11-16): o Codex respondeu `You've hit your usage limit ... try again at 3:05 PM`. O despachador tratou isso como falha tecnica, consumiu as 5 tentativas do
evento em poucos minutos e mandou o #669 para a DLQ — por um esgotamento TEMPORARIO de cota. Aqui ele vira um estado da CONTA, gravado no SQLite do EventStore.

  classificar   `classify()` separa LIMITE DE USO, FALHA DE AUTENTICACAO, FALHA TRANSITORIA e ERRO DEFINITIVO a partir da saida do processo. So o limite de uso
                e a autenticacao suspendem a conta; transitorio e definitivo seguem o caminho normal (retry com atraso, DLQ ao esgotar as tentativas).
  persistir     tabela `rate_limits` (uma linha por conta): estado, instante de reset, quantos episodios seguidos, quem esta sondando. Sobrevive a reinicio do supervisor e
                do Windows (o horario e absoluto, comparado ao relogio do EventStore). Nada fica so em memoria.
  suspender     `peek()` e `admit()` barram a revisao ANTES de qualquer chamada ao GitHub ou ao Codex: durante o bloqueio os workers devolvem IDLE e nao seguram lease.
  nao gastar    o evento volta a PENDING com `EventStore.defer()` (a tentativa NAO e consumida) e `available_at` = reset. Nunca vai para a DLQ so por cota.
  retomar       passado o reset, UM worker por vez sonda (`admit` concede a sonda; os outros esperam). Sucesso limpa o estado; novo limite abre novo episodio. O HEAD e os
                checks sao revalidados pelo `pr_lifecycle.work` antes de a sonda ser concedida.
  conservador   horario ambiguo (sem AM/PM, ja passado, fuso incerto, mais de 7 dias, texto sem previsao) => espera escalonada 30 min, 1 h, 2 h, 4 h, 6 h e sonda.
                Reset declarado ganha 2 min de folga. Um bloqueio vigente nunca e ENCURTADO por outro worker.
  nao infinito  mais de `MAX_EPISODES` limites seguidos sem nenhuma revisao bem-sucedida => `ESCALATED`: a conta fica suspensa, NENHUMA chamada e feita, nenhum evento vai
                para a DLQ, e o log do ciclo mostra o estado. Retomar e decisao do proprietario (`python -m tools.orchestration.rate_limit clear --account ...`).

Horarios de texto livre ("try again at 3:05 PM") sao do relogio LOCAL da maquina que roda o Codex. O horario e sempre resolvido em relacao ao instante em que o erro foi
OBSERVADO (nao ao de agora), e a sonda confirma na pratica: um fuso errado custa uma sonda, nunca uma tentativa do evento."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from dataclasses import dataclass

USAGE_LIMIT, AUTH, TRANSIENT, FATAL = "USAGE_LIMIT", "AUTH", "TRANSIENT", "FATAL"
OK, LIMITED, AUTH_FAILED, ESCALATED = "OK", "LIMITED", "AUTH_FAILED", "ESCALATED"

MARGIN_S = 120.0                                           # folga depois do reset declarado
MAX_RESET_S = 7 * 86400.0                                  # reset declarado alem disto e tratado como ambiguo
BACKOFF_S = (1800.0, 3600.0, 7200.0, 14400.0, 21600.0)     # sem previsao confiavel: espera escalonada, teto de 6 h
AUTH_BACKOFF_S = 600.0                                     # autenticacao nao se cura sozinha: nao martela o CLI, mas tambem nao espera um dia
PROBE_LEASE_S = 2400.0                                     # uma sonda que morreu libera a vaga depois disto
MAX_EPISODES = 12                                          # limites SEGUIDOS sem sucesso antes de escalar ao proprietario

_USAGE = re.compile(r"usage limit|hit your .{0,20}limit|rate[ _-]?limit|quota|too many requests|\b429\b|insufficient_quota|exceeded your current", re.I)
_AUTH = re.compile(r"not logged in|please log ?in|log ?in required|login required|unauthori[sz]ed|\b401\b|\b403\b|authentication|invalid api key|token (?:has )?(?:expired|been revoked|revoked)", re.I)
_TRANSIENT = re.compile(r"timed? ?out|timeout|temporar|overloaded|service unavailable|bad gateway|gateway time|\b50[234]\b|connection (?:reset|refused|aborted|closed)|"
                        r"network|dns|econn|etimedout|try again later|internal server error", re.I)
_AT_CLOCK = re.compile(r"try again (?:at|after)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)
_AT_DATE = re.compile(r"try again (?:at|after)\s+([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4}),?\s+(\d{1,2}):(\d{2})\s*(am|pm)\b", re.I)
_IN = re.compile(r"try again in\s+([^.\n]{1,60})", re.I)
_UNIT = re.compile(r"(\d+(?:\.\d+)?)\s*(days?|d|hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", re.I)
_RETRY_AFTER = re.compile(r"retry-after\s*[:=]\s*(\d+)", re.I)
_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2}))", re.I)
_MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_SECONDS = {"d": 86400.0, "h": 3600.0, "m": 60.0, "s": 1.0}


@dataclass(frozen=True)
class Failure:
    kind: str
    reason: str
    reset_at: float | None = None                          # epoch; None = sem previsao confiavel (ambiguo / ausente)
    ambiguous: bool = False


@dataclass(frozen=True)
class Block:
    account: str
    state: str
    kind: str
    until: float
    reset_known: bool
    episodes: int
    reason: str
    escalated: bool = False
    probing: bool = False

    def as_dict(self) -> dict:
        return {"account": self.account, "state": self.state, "kind": self.kind, "until": self.until,
                "until_iso": dt.datetime.fromtimestamp(self.until, dt.timezone.utc).isoformat() if self.until else None,
                "reset_known": self.reset_known, "episodes": self.episodes, "reason": self.reason[:200], "probing": self.probing}


@dataclass(frozen=True)
class Admission:
    allowed: bool
    probe: bool = False
    block: Block | None = None


# ----------------------------------------------------------------------------------------------------------------------------- classificar
def parse_reset(text: str, observed: float) -> float | None:
    """Instante (epoch) em que a cota volta, resolvido em relacao a `observed`; None quando ausente OU ambiguo. Nunca adivinha: o chamador espera o escalonamento."""
    if not text:
        return None
    candidates: list[float] = []
    obs_dt = dt.datetime.fromtimestamp(observed)
    m = _AT_DATE.search(text)
    if m and m.group(1)[:3].lower() in _MONTHS:
        try:
            hour = int(m.group(4)) % 12 + (12 if m.group(6).lower() == "pm" else 0)
            candidates.append(dt.datetime(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)), hour, int(m.group(5))).timestamp())
        except (ValueError, OverflowError, OSError):
            return None
    else:
        m = _AT_CLOCK.search(text)
        if m:
            hh, mm, mer = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
            if mer:
                if not 1 <= hh <= 12:
                    return None
                hh = hh % 12 + (12 if mer == "pm" else 0)
            elif not 13 <= hh <= 23 and hh != 0:
                return None                                # "3:05" sem AM/PM e sem formato de 24 h: pode ser 03:05 ou 15:05
            if mm > 59:
                return None
            try:
                candidates.append(obs_dt.replace(hour=hh, minute=mm, second=0, microsecond=0).timestamp())
            except ValueError:
                return None
    m = _IN.search(text)
    if m:
        total = sum(float(n) * _SECONDS[u[0].lower()] for n, u in _UNIT.findall(m.group(1)))
        if total > 0:
            candidates.append(observed + total)
    m = _RETRY_AFTER.search(text)
    if m:
        candidates.append(observed + float(m.group(1)))
    m = _ISO.search(text)
    if m:
        try:
            candidates.append(dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    if len(candidates) != 1:
        return None                                        # nenhuma previsao, ou previsoes divergentes: ambiguo
    reset = candidates[0]
    if reset <= observed or reset - observed > MAX_RESET_S:
        return None                                        # ja passou (fuso/relogio incerto) ou longe demais para confiar
    return reset


def classify(rc: int | None, text: str, timed_out: bool = False, observed: float | None = None) -> Failure:
    """Classifica a falha de uma execucao do Codex. A ordem importa: a cota esgotada diz tambem 'try again', e a autenticacao nao pode ser confundida com ela."""
    observed = time.time() if observed is None else observed
    text = text or ""
    if _USAGE.search(text):
        reset = parse_reset(text, observed)
        return Failure(USAGE_LIMIT, "limite de uso da conta do revisor" + ("" if reset else " (sem previsao confiavel de reset)"), reset, reset is None)
    if _AUTH.search(text):
        return Failure(AUTH, "falha de autenticacao do revisor")
    if timed_out or _TRANSIENT.search(text):
        return Failure(TRANSIENT, "falha transitoria do revisor" + (" (timeout)" if timed_out else ""))
    return Failure(FATAL, f"codex saiu com codigo {rc}")


def account_key(policy: dict) -> str:
    reviewers = [str(r) for r in (policy.get("reviewers") or []) if r]
    return f"codex:{reviewers[0] if reviewers else 'default'}"


# ------------------------------------------------------------------------------------------------------------------------------ persistir
_SCHEMA = """
CREATE TABLE IF NOT EXISTS rate_limits (
  account          TEXT PRIMARY KEY,
  state            TEXT NOT NULL,
  kind             TEXT NOT NULL DEFAULT '',
  blocked_until    REAL NOT NULL DEFAULT 0,
  reset_known      INTEGER NOT NULL DEFAULT 0,
  episodes         INTEGER NOT NULL DEFAULT 0,
  first_blocked_at REAL NOT NULL DEFAULT 0,
  last_reason      TEXT NOT NULL DEFAULT '',
  probe_owner      TEXT,
  probe_until      REAL NOT NULL DEFAULT 0,
  last_ok_at       REAL NOT NULL DEFAULT 0,
  updated_at       REAL NOT NULL DEFAULT 0
);
"""


class RateLimitGate:
    """Estado de limite por conta, no SQLite do proprio EventStore (mesma transacao `BEGIN IMMEDIATE`: seguro entre threads e processos)."""

    def __init__(self, store):
        self.store = store
        with store.connection() as db:
            db.executescript(_SCHEMA)

    def _now(self, now: float | None) -> float:
        return self.store.clock() if now is None else now

    @staticmethod
    def _block(r, probing: bool = False) -> Block:
        return Block(r["account"], r["state"], r["kind"], r["blocked_until"], bool(r["reset_known"]), r["episodes"], r["last_reason"],
                     r["state"] == ESCALATED, probing)

    def _row(self, db, account: str):
        return db.execute("SELECT * FROM rate_limits WHERE account=?", (account,)).fetchone()

    # -- leitura --------------------------------------------------------------------------------------------------------------------------
    def peek(self, account: str, owner: str | None = None, now: float | None = None) -> Block | None:
        """Bloqueio vigente (None = pode seguir). Sem efeito colateral. Uma sonda viva de OUTRO worker tambem barra."""
        now = self._now(now)
        with self.store.transaction() as db:
            r = self._row(db, account)
        return self._blocking(r, owner, now)

    def _blocking(self, r, owner: str | None, now: float) -> Block | None:
        if r is None or r["state"] == OK:
            return None
        if r["state"] == ESCALATED or r["blocked_until"] > now:
            return self._block(r)
        if r["probe_owner"] and r["probe_until"] > now and r["probe_owner"] != owner:
            return self._block(r, probing=True)
        return None

    def status(self, now: float | None = None) -> list[dict]:
        now = self._now(now)
        with self.store.transaction() as db:
            rows = db.execute("SELECT * FROM rate_limits WHERE state<>?", (OK,)).fetchall()
        return [{**self._block(r).as_dict(), "remaining_s": max(0.0, r["blocked_until"] - now)} for r in rows]

    # -- escrita --------------------------------------------------------------------------------------------------------------------------
    def admit(self, account: str, owner: str, now: float | None = None) -> Admission:
        """Autoriza UMA revisao. Conta saudavel: qualquer worker. Bloqueio vencido: so a SONDA de um worker por vez (os outros esperam o resultado dela)."""
        now = self._now(now)
        with self.store.transaction() as db:
            r = self._row(db, account)
            blk = self._blocking(r, owner, now)
            if blk is not None:
                return Admission(False, False, blk)
            if r is None or r["state"] == OK:
                return Admission(True, False, None)
            db.execute("UPDATE rate_limits SET probe_owner=?, probe_until=?, updated_at=? WHERE account=?", (owner, now + PROBE_LEASE_S, now, account))
            return Admission(True, True, None)

    def record_block(self, account: str, failure: Failure, now: float | None = None) -> Block:
        """Registra um limite (ou falha de autenticacao). Idempotente e concorrente: varios workers falhando no MESMO episodio contam 1; um bloqueio vigente nunca encurta."""
        now = self._now(now)
        auth = failure.kind == AUTH
        with self.store.transaction() as db:
            r = self._row(db, account)
            live = r is not None and r["state"] in (LIMITED, AUTH_FAILED) and r["blocked_until"] > now
            if live:
                episodes = r["episodes"]
            else:
                episodes = (r["episodes"] if r is not None else 0) + 1
            if auth:
                until, known = now + AUTH_BACKOFF_S, False
            elif failure.reset_at is not None:
                until, known = failure.reset_at + MARGIN_S, True
            else:
                until, known = now + BACKOFF_S[min(max(episodes, 1) - 1, len(BACKOFF_S) - 1)], False
            if live:
                until = max(until, r["blocked_until"])
                known = known or bool(r["reset_known"])
            state = ESCALATED if (episodes > MAX_EPISODES or (r is not None and r["state"] == ESCALATED)) else (AUTH_FAILED if auth else LIMITED)
            first = r["first_blocked_at"] if (r is not None and r["state"] != OK and r["first_blocked_at"]) else now
            reason = failure.reason[:300]
            db.execute(
                """INSERT INTO rate_limits(account,state,kind,blocked_until,reset_known,episodes,first_blocked_at,last_reason,probe_owner,probe_until,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,NULL,0,?)
                   ON CONFLICT(account) DO UPDATE SET state=excluded.state, kind=excluded.kind, blocked_until=excluded.blocked_until, reset_known=excluded.reset_known,
                   episodes=excluded.episodes, first_blocked_at=excluded.first_blocked_at, last_reason=excluded.last_reason, probe_owner=NULL, probe_until=0,
                   updated_at=excluded.updated_at""",
                (account, state, failure.kind, until, int(known), episodes, first, reason, now))
            return self._block(self._row(db, account))

    def seed_block(self, account: str, until: float, reason: str, now: float | None = None) -> None:
        """Recuperacao de um limite ja gravado so no texto de um erro antigo (DLQ legada): so cria bloqueio se NAO houver um vigente (nunca encurta, nunca conta episodio)."""
        now = self._now(now)
        with self.store.transaction() as db:
            r = self._row(db, account)
            if r is not None and (r["state"] == ESCALATED or r["blocked_until"] >= until):
                return
            db.execute(
                """INSERT INTO rate_limits(account,state,kind,blocked_until,reset_known,episodes,first_blocked_at,last_reason,updated_at) VALUES(?,?,?,?,1,1,?,?,?)
                   ON CONFLICT(account) DO UPDATE SET state=?, kind=?, blocked_until=?, reset_known=1, episodes=MAX(episodes, 1), probe_owner=NULL, probe_until=0, last_reason=?, updated_at=?""",
                (account, LIMITED, USAGE_LIMIT, until, now, reason[:300], now, LIMITED, USAGE_LIMIT, until, reason[:300], now))

    def record_success(self, account: str, now: float | None = None) -> None:
        """Uma execucao do Codex terminou (rc 0): a cota voltou. Limpa o estado e zera os episodios."""
        now = self._now(now)
        with self.store.transaction() as db:
            db.execute(
                """INSERT INTO rate_limits(account,state,last_ok_at,updated_at) VALUES(?,?,?,?)
                   ON CONFLICT(account) DO UPDATE SET state=?, kind='', blocked_until=0, reset_known=0, episodes=0, first_blocked_at=0, probe_owner=NULL, probe_until=0,
                   last_reason='', last_ok_at=?, updated_at=?""",
                (account, OK, now, now, OK, now, now))

    def release_probe(self, account: str, owner: str) -> None:
        """A sonda terminou sem provar nada (PR obsoleto, timeout, erro de GitHub...): devolve a vaga sem alterar o bloqueio."""
        with self.store.transaction() as db:
            db.execute("UPDATE rate_limits SET probe_owner=NULL, probe_until=0 WHERE account=? AND probe_owner=?", (account, owner))

    def clear(self, account: str, now: float | None = None) -> None:
        """Decisao do proprietario (tambem sai de ESCALATED)."""
        self.record_success(account, now)


# ------------------------------------------------------------------------------------------------------------ recuperar a DLQ legada por cota
_LEGACY = re.compile(r"limite de uso|usage limit|hit your .{0,20}limit|insufficient_quota", re.I)


def requeue_quota_dlq(store, gate: RateLimitGate, account: str, producer: str, now: float | None = None) -> list[dict]:
    """Eventos que foram para a DLQ SO por cota (erro com a assinatura do limite de uso, de antes deste mecanismo) voltam a PENDING com 0 tentativas e o historico
    preservado; o reset lido do texto do erro (relativo a quando ele ocorreu) vira bloqueio da conta. Idempotente: o que nao e DLQ-por-cota nunca e tocado."""
    now = gate._now(now)
    out = []
    for ev in store.events():
        if ev["producer"] != producer or ev["status"] != "DLQ" or not _LEGACY.search(ev.get("error") or ""):
            continue
        reset = parse_reset(ev.get("error") or "", ev["updated_at"])
        if reset is not None and reset + MARGIN_S > now:
            gate.seed_block(account, reset + MARGIN_S, "DLQ legada por limite de uso", now)
        if store.requeue_dlq(ev["id"], "limite de uso: reenfileirado (tentativas tecnicas nao foram consumidas por cota)",
                             available_at=max(now, (reset + MARGIN_S) if reset else now)):
            out.append({"event": ev["id"], "action": "REQUEUED_QUOTA_DLQ"})
    return out


def main(argv: list[str] | None = None) -> int:
    from tools.orchestration.store_factory import get_store
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    cl = sub.add_parser("clear")
    cl.add_argument("--account", required=True)
    a = ap.parse_args(argv)
    gate = RateLimitGate(get_store())
    if a.cmd == "status":
        print(json.dumps(gate.status(), indent=1, ensure_ascii=False))
    else:
        gate.clear(a.account)
        print(json.dumps({"cleared": a.account}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
