"""sqlite_source.py — o EventStore (SQLite) como fonte PRIMARIA de claim do executor (FP-060 MT-07 / S2, #626).

    EXECUTOR_SOURCE=json     (padrao) a fila JSON do bridge e o caminho de execucao; o SQLite e espelho (modo sombra).
    EXECUTOR_SOURCE=sqlite   o executor reivindica `CORRECTION_REQUESTED` do EventStore (claim transacional, lease, fencing,
                             DLQ); a fila JSON vira ESPELHO (o sentido do espelho se inverte) e nunca mais escolhe trabalho.

    python -m tools.orchestration.sqlite_source status            # fonte ativa, divergencia JSON x SQLite, leases vivos
    python -m tools.orchestration.sqlite_source rollback-check    # o que a volta para JSON mudaria (nao escreve)
    python -m tools.orchestration.sqlite_source rollback-apply    # reconcilia a fila JSON com o SQLite; so com o executor parado

Contrato (cada linha tem teste):
- Valor desconhecido em EXECUTOR_SOURCE RECUSA (fail-closed); nunca cai silenciosamente no outro caminho.
- Os dois caminhos nunca escolhem trabalho ao mesmo tempo: com `sqlite`, `claim_next`/`update_owned`/heartbeat da fila JSON nao sao chamados.
- Todo item da fila JSON ainda `QUEUED` e publicado no SQLite antes do claim (publish idempotente por chave): o que o bridge aceitou e o
  SQLite perdeu nao fica para sempre sem dono.
- Toda escrita do resultado e CERCADA pelo token do lease (`LeaseLost` => resultado descartado, nada sobrescrito).
- DRY_RUN nao reivindica: um claim consome tentativa (`attempt`), e dry-run em loop esgotaria a fila no DLQ. So olha o proximo candidato.
- O teto diario de execucoes vale tambem aqui (contado nas transicoes do proprio SQLite).
- Rollback: `rollback-apply` marca na fila JSON o que o SQLite ja concluiu, para a volta ao JSON nao repetir trabalho; recusa se algum
  evento tem lease vivo (o executor ainda esta rodando).

O que NAO e: nao liga nada em producao (o padrao segue `json`), nao liga `--execute`, nao prova o E2E da MT-06 (pre-requisito do cutover)."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import threading

from tools.orchestration import event_bridge as eb
from tools.orchestration.event_store import EventStore, LeaseLost
from tools.validation import execution_state as es

SOURCE_ENV = "EXECUTOR_SOURCE"
SOURCES = ("json", "sqlite")
EVENT_TYPE = "CORRECTION_REQUESTED"
IMPLEMENT_TYPE = "IMPLEMENT_REQUESTED"
CLAIMED_TYPES = (EVENT_TYPE, IMPLEMENT_TYPE)                                   # correcao de review e pedido de implementacao (intake)
PRODUCER = "event_bridge"
PARKED_STATES = frozenset({"SUPERSEDED", "REFUSED", "PARKED_UNSUPPORTED"})
DAY_S = 24 * 3600
MAX_MALFORMED_PER_CLAIM = 20                                                   # evento malformado e descartado; nao ha loop infinito

_LOCK = threading.Lock()
_CLAIMED: dict[str, dict] = {}                                                 # key -> {"ev": evento reivindicado, "owner": str, "item": dict}


class SourceError(ValueError):
    """EXECUTOR_SOURCE com valor desconhecido: o executor nao adivinha qual fila e a verdadeira."""


def source() -> str:
    raw = (os.environ.get(SOURCE_ENV) or "json").strip().lower()
    if raw not in SOURCES:
        raise SourceError(f"{SOURCE_ENV}={raw!r} desconhecido (validos: {', '.join(SOURCES)}): recusado")
    return raw


def is_sqlite() -> bool:
    return source() == "sqlite"


def _store() -> EventStore:
    from tools.orchestration.store_factory import get_store
    return get_store()                                                         # sem try/except: aqui o SQLite e a verdade, falhar e parar


def _parse_iso(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------------ evento <-> item
def item_from_event(ev: dict, attempts: int | None = None) -> dict | None:
    """O item no formato que os handlers do executor ja entendem. None = payload que nao descreve um trabalho executavel."""
    p = ev["payload"]                                                          # `claim` devolve o payload ja decodificado; `events()` devolve o texto
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except ValueError:
            return None
    if isinstance(p, dict) and ev.get("event_type") == IMPLEMENT_TYPE:
        return _implement_item(ev, p, attempts)
    if not isinstance(p, dict) or not p.get("review_id") or not isinstance(p.get("pr"), int) or not p.get("head_sha"):
        return None
    key = f"review:{p['review_id']}:{p['pr']}:{p['head_sha']}"
    if key != ev["idempotency_key"]:
        return None                                                            # a chave do evento nao e a do review que o payload descreve
    return {"key": key, "kind": "review", "event_id": f"review:{p['review_id']}", "pr": p["pr"], "issue": p.get("issue"),
            "head_sha": p["head_sha"], "author": p.get("author"), "url": p.get("url"), "state": "RUNNING",
            "attempts": max(0, ev["attempt"] - 1) if attempts is None else attempts, "store_event": ev["id"]}


def _implement_item(ev: dict, p: dict, attempts: int | None) -> dict | None:
    """Item de um `IMPLEMENT_REQUESTED`: so vale se a chave do evento e a do pedido que o payload descreve (Issue + hash da spec)."""
    issue, digest = p.get("issue"), p.get("spec_hash")
    if not isinstance(issue, int) or isinstance(issue, bool) or not isinstance(digest, str) or not digest:
        return None
    if ev["idempotency_key"] != f"implement:issue:{issue}:{digest}":
        return None
    return {"key": ev["idempotency_key"], "kind": "implement", "event_id": f"implement:{issue}", "issue": issue, "spec_hash": digest,
            "title": p.get("title") or "", "pr": None, "head_sha": "", "state": "RUNNING",
            "attempts": max(0, ev["attempt"] - 1) if attempts is None else attempts, "store_event": ev["id"]}


def store_args_from_item(item: dict) -> dict | None:
    """kwargs de `EventStore.publish` para um item JSON ainda nao espelhado (so reviews; comentarios nao sao espelhados por desenho)."""
    if item.get("kind") != "review" or not item.get("pr") or not item.get("head_sha"):
        return None
    rid = str(item.get("event_id", "")).split(":")[-1]
    key = f"review:{rid}:{item['pr']}:{item['head_sha']}"
    return dict(event_type=EVENT_TYPE, idempotency_key=key, job_id=f"pr:{item['pr']}",
                payload={"pr": item["pr"], "issue": item.get("issue"), "head_sha": item["head_sha"], "review_id": rid,
                         "author": item.get("author"), "url": item.get("url")},
                correlation_id=f"bridge:{item.get('event_id')}", producer=PRODUCER)


def backfill_store(store: EventStore, bstate: dict | None = None) -> int:
    """Publica no SQLite todo item JSON ainda QUEUED que ele nao tem. Idempotente (a chave e unica). Devolve quantos criou."""
    if bstate is None:
        with es.locked(eb.bridge_path()):
            bstate = eb.load()
    created = 0
    for it in bstate["queue"]:
        if it.get("state") != "QUEUED":
            continue
        args = store_args_from_item(it)
        if args is None:
            continue
        _id, was_created = store.publish(**args)
        created += int(was_created)
    return created


# --------------------------------------------------------------------------------------------------------- claim / lease
def _recent_claims(store: EventStore, now: float) -> int:
    ids = {e["id"] for e in store.events() if e["event_type"] in CLAIMED_TYPES}
    return sum(1 for t in store.transitions()
               if t["event_id"] in ids and t["to_status"] == "RUNNING" and (t["detail"] or "").startswith(("claimed", "reclaimed"))
               and t["at"] >= now - DAY_S)


def claim_next(owner: str, now: dt.datetime | None = None, *, lease_s: float, daily_cap: int) -> dict | None:
    store = _store()
    backfill_store(store)
    if _recent_claims(store, store.clock()) >= daily_cap:
        return None
    for _ in range(MAX_MALFORMED_PER_CLAIM):
        ev = store.claim(CLAIMED_TYPES, owner, lease_s)
        if ev is None:
            return None
        item = item_from_event(ev)
        if item is None:
            store.supersede(ev, "payload ou chave nao descrevem um trabalho executavel: descartado")
            continue
        with _LOCK:
            _CLAIMED[item["key"]] = {"ev": ev, "owner": owner, "item": item}
        return dict(item)
    return None


def peek_next() -> dict | None:
    """O proximo candidato SEM reivindicar (DRY_RUN): um claim gastaria uma tentativa do evento."""
    store = _store()
    now = store.clock()
    live = {e["job_id"] for e in store.events() if e["event_type"] in CLAIMED_TYPES and e["status"] == "RUNNING" and e["lease_until"] > now}
    for ev in store.events():
        if (ev["event_type"] in CLAIMED_TYPES and ev["status"] == "PENDING" and ev["available_at"] <= now
                and ev["attempt"] < ev["max_attempts"] and ev["job_id"] not in live):
            item = item_from_event(ev, attempts=ev["attempt"])
            if item is not None:
                return item
    return None


def renew(key: str, owner: str, lease_s: float) -> bool:
    """Heartbeat: False = lease perdido (outro dono ou expirado) e o filho precisa ser derrubado."""
    with _LOCK:
        entry = _CLAIMED.get(key)
    if entry is None or entry["owner"] != owner:
        return False
    try:
        return _store().renew(entry["ev"], lease_s)
    except LeaseLost:
        return False


def _retry_delay(it: dict, now: dt.datetime | None, default: float) -> float:
    at = _parse_iso(it.get("retry_after") or "")
    ref = now or dt.datetime.now(dt.timezone.utc)
    return default if at is None else max(0.0, (at - ref).total_seconds())


def update_owned(key: str, owner: str, mutate, release: bool = False, now: dt.datetime | None = None, *,
                 lease_s: float, retry_s: float) -> bool:
    """Mesma interface da fila JSON: `mutate(item, bstate)` roda sobre uma copia local; o efeito durável vai para o SQLite. Sem `release`
    e so uma confirmacao de posse (renova o lease). Com `release`, o estado final do item vira `complete`/`supersede`/`fail` CERCADO pelo
    token. Perdeu o lease => False e nada e gravado."""
    with _LOCK:
        entry = _CLAIMED.get(key)
    if entry is None or entry["owner"] != owner:
        return False
    store, ev, it = _store(), entry["ev"], entry["item"]
    scratch = {**eb.default_bridge_state(), "queue": [it]}
    mutate(it, scratch)
    if not release:
        try:
            if store.renew(ev, lease_s):
                return True
        except LeaseLost:
            pass
        with _LOCK:
            _CLAIMED.pop(key, None)
        return False
    try:
        settled = _settle(store, ev, it, now, retry_s)
    except LeaseLost:
        settled = None
    finally:
        with _LOCK:
            _CLAIMED.pop(key, None)
    if settled is None:
        return False
    _mirror_to_json(it, settled, ev)
    return True


def _settle(store: EventStore, ev: dict, it: dict, now: dt.datetime | None, retry_s: float) -> str:
    """Grava o estado final no SQLite e devolve o status resultante do evento."""
    state = it.get("state")
    why = str(it.get("last_error") or state)
    if state == "DONE_AWAITING_REREVIEW":
        store.complete(ev, {"action": "DONE", "new_head": it.get("new_head", ""), "log": it.get("log", ""),
                            **({"pr": it["pr_number"]} if it.get("pr_number") else {})})
        return "DONE"
    if state in PARKED_STATES:
        store.supersede(ev, why[:2000])
        return "SUPERSEDED"
    delay = _retry_delay(it, now, retry_s) if state != "QUEUED" else 0.0
    return store.fail(ev, why[:2000], retry_delay=delay)


def _mirror_to_json(it: dict, status: str, ev: dict) -> None:
    """Espelho reverso: a fila JSON passa a refletir o que o SQLite decidiu, para um rollback nao repetir trabalho. Melhor esforco."""
    try:
        with es.locked(eb.bridge_path()):
            b = eb.load()
            row = next((t for t in b["queue"] if t["key"] == it["key"]), None)
            if row is None:
                return
            for field in ("last_error", "new_head", "log", "retry_after"):
                if it.get(field) is not None:
                    row[field] = it[field]
            row["state"] = it["state"] if status != "DLQ" else "FAILED"
            row["attempts"] = ev["max_attempts"] if status == "DLQ" else it.get("attempts", row.get("attempts", 0))
            row.pop("owner", None)
            row.pop("lease_expires", None)
            eb.save(b)
    except Exception as exc:                                                   # noqa: BLE001 — o SQLite e a verdade; o espelho nao derruba o executor
        try:
            from tools.orchestration.store_factory import _record_shadow_error
            _record_shadow_error(exc)
        except Exception:                                                      # noqa: BLE001
            pass


def reset_claims() -> None:
    """Auxiliar de teste/reinicio: esquece os claims em memoria (os leases no SQLite seguem valendo ate vencer)."""
    with _LOCK:
        _CLAIMED.clear()


# ------------------------------------------------------------------------------------------------------------- rollback
def rollback_plan(store: EventStore, bstate: dict, now: float | None = None) -> dict:
    """O que a volta para a fila JSON mudaria. `blocked` = eventos com lease vivo: o executor ainda esta no meio do trabalho."""
    now = store.clock() if now is None else now
    by_key = {e["idempotency_key"]: e for e in store.events() if e["event_type"] == EVENT_TYPE}
    changes, blocked = [], []
    for it in bstate["queue"]:
        args = store_args_from_item(it)
        ev = by_key.get(args["idempotency_key"]) if args else None
        if ev is None:
            continue
        if ev["status"] == "RUNNING" and ev["lease_until"] > now:
            blocked.append({"key": it["key"], "owner": ev["lease_owner"]})
            continue
        want = {"DONE": "DONE_AWAITING_REREVIEW", "SUPERSEDED": "SUPERSEDED", "DLQ": "FAILED"}.get(ev["status"])
        if want and it.get("state") != want:
            changes.append({"key": it["key"], "from": it.get("state"), "to": want, "store_status": ev["status"]})
    return {"changes": changes, "blocked": blocked}


def rollback_apply(store: EventStore) -> dict:
    with es.locked(eb.bridge_path()):
        b = eb.load()
        plan = rollback_plan(store, b)
        if plan["blocked"]:
            return {"applied": 0, "refused": "evento(s) com lease vivo: o executor ainda esta rodando; pare-o antes", **plan}
        by_key = {t["key"]: t for t in b["queue"]}
        for c in plan["changes"]:
            row = by_key[c["key"]]
            row["state"] = c["to"]
            row.pop("owner", None)
            row.pop("lease_expires", None)
            if c["to"] == "FAILED":
                row["attempts"] = max(row.get("attempts", 0), 3)
                row["last_error"] = row.get("last_error") or "dead-lettered no SQLite (rollback)"
        if plan["changes"]:
            eb.diagnose(b, f"rollback para a fila JSON: {len(plan['changes'])} item(ns) reconciliados com o SQLite")
            eb.save(b)
        return {"applied": len(plan["changes"]), **plan}


# ----------------------------------------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("status", "rollback-check", "rollback-apply"))
    a = ap.parse_args(argv)
    try:
        active = source()
    except SourceError as exc:
        print(json.dumps({"fatal": str(exc)}))
        return 6
    store = _store()
    if a.cmd == "rollback-apply":
        out = rollback_apply(store)
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return 1 if out.get("refused") else 0
    with es.locked(eb.bridge_path()):
        b = eb.load()
    if a.cmd == "rollback-check":
        plan = rollback_plan(store, b)
        print(json.dumps(plan, indent=1, ensure_ascii=False))
        return 1 if plan["blocked"] else 0
    from tools.orchestration import shadow_divergence as sd
    div = [d.as_dict() for d in sd.collect(b["queue"], store)]
    now = store.clock()
    live = [{"key": e["idempotency_key"], "owner": e["lease_owner"]} for e in store.events()
            if e["event_type"] == EVENT_TYPE and e["status"] == "RUNNING" and e["lease_until"] > now]
    print(json.dumps({"source": active, "divergences": div, "live_leases": live}, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
