"""shadow_divergence.py — detector de divergencia entre a fila JSON do executor e o espelho no EventStore (FP-060 MT-07 / S1, #626).

    python -m tools.orchestration.shadow_divergence [--json] [--strict]     # exit 1 se houver divergencia

SOMENTE LEITURA: le a fila do bridge (JSON) e os eventos do EventStore; nunca escreve em nenhum dos dois. E o criterio de entrada do
cutover do executor para o SQLite: enquanto a fila JSON e o espelho nao concordam, trocar o caminho de execucao e trocar uma verdade por outra.

Como o espelho e produzido hoje (modo sombra, `event_executor._sync_result_to_store`): o bridge grava o evento `CORRECTION_REQUESTED` com a
chave `review:<id>:<pr>:<head_sha>` quando aceita o review; o evento fica PENDING durante TODO o trabalho do item JSON e so e atualizado
quando o item termina (DONE -> DONE; SUPERSEDED/REFUSED/PARKED -> SUPERSEDED; FAILED/BLOCKED -> PENDING com retry, ou DLQ no limite). Os pares
aceitos abaixo sao exatamente esses. Itens que nao sao review (comentarios) nao sao espelhados por desenho e sao ignorados.

Codigos: MISSING_IN_STORE (item sem evento), STALE_PENDING (item terminou e o evento segue PENDING: o sync se perdeu), STATE_MISMATCH (par fora
da tabela), UNKNOWN_STATE (estado JSON desconhecido; nunca presumido igual) e ORPHAN_IN_STORE (evento do bridge sem item JSON: aviso; so falha
com `--strict`, porque a fila JSON e podada)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass

MIRROR_EVENT_TYPE = "CORRECTION_REQUESTED"
MIRROR_PRODUCER = "event_bridge"
FINISHED = frozenset({"DONE_AWAITING_REREVIEW", "SUPERSEDED", "REFUSED", "PARKED_UNSUPPORTED"})
EXPECTED: dict[str, frozenset[str]] = {
    "QUEUED": frozenset({"PENDING"}), "RUNNING": frozenset({"PENDING"}),
    "DONE_AWAITING_REREVIEW": frozenset({"DONE"}),
    "SUPERSEDED": frozenset({"SUPERSEDED"}), "REFUSED": frozenset({"SUPERSEDED"}), "PARKED_UNSUPPORTED": frozenset({"SUPERSEDED"}),
    "FAILED": frozenset({"PENDING", "DLQ"}), "BLOCKED_CLI": frozenset({"PENDING", "DLQ"}),
    "BLOCKED_CREDENTIALS": frozenset({"PENDING", "DLQ"}), "BLOCKED_WORKTREE": frozenset({"PENDING", "DLQ"}),
    "BLOCKED_REVIEW_FETCH": frozenset({"PENDING", "DLQ"}),
}


@dataclass(frozen=True)
class Divergence:
    code: str
    key: str
    detail: str

    def as_dict(self) -> dict:
        return {"code": self.code, "key": self.key, "detail": self.detail}


def mirror_key(item: dict) -> str:
    """A MESMA chave que o bridge publica (`store_factory.bridge_to_store_args`) e que o sync procura (`_sync_result_to_store`)."""
    return f"review:{str(item.get('event_id', '')).split(':')[-1]}:{item.get('pr')}:{item.get('head_sha')}"


RETRYABLE = frozenset({"QUEUED", "FAILED", "BLOCKED_CLI", "BLOCKED_CREDENTIALS", "BLOCKED_WORKTREE", "BLOCKED_REVIEW_FETCH"})
JSON_MAX_ATTEMPTS = 3                                                    # o `pick` da fila JSON (`event_executor.MAX_ATTEMPTS`); conferido por teste


def compare(queue: list[dict], events: list[dict], json_max_attempts: int = JSON_MAX_ATTEMPTS) -> list[Divergence]:
    mirror = {e["idempotency_key"]: e for e in events if e.get("producer") == MIRROR_PRODUCER and e.get("event_type") == MIRROR_EVENT_TYPE}
    found, matched = [], set()
    for item in queue:
        if item.get("kind") != "review":
            continue
        key, state = item["key"], item.get("state")
        event = mirror.get(mirror_key(item))
        if event is None:
            found.append(Divergence("MISSING_IN_STORE", key, f"item {state} sem evento {mirror_key(item)}"))
            continue
        matched.add(event["idempotency_key"])
        allowed = EXPECTED.get(state)
        if allowed is None:
            found.append(Divergence("UNKNOWN_STATE", key, f"estado JSON {state!r} fora da tabela; evento {event['status']}"))
        elif event["status"] not in allowed:
            code = "STALE_PENDING" if event["status"] == "PENDING" and state in FINISHED else "STATE_MISMATCH"
            found.append(Divergence(code, key, f"item {state} mas evento {event['status']} (esperado {'/'.join(sorted(allowed))})"))
        elif state in RETRYABLE:
            # o estado bate, mas a ELEGIBILIDADE pode nao bater: o que o JSON ainda executaria e o que o SQLite ainda reivindicaria precisam ser o mesmo, senao o cutover
            # perde trabalho (DLQ no SQLite, ainda elegivel no JSON) ou repete trabalho esgotado (esgotado no JSON, PENDING com tentativas no SQLite)
            json_ok = int(item.get("attempts") or 0) < json_max_attempts
            store_ok = event["status"] == "PENDING" and int(event.get("attempt") or 0) < int(event.get("max_attempts") or 0)
            if json_ok != store_ok:
                found.append(Divergence("ELIGIBILITY_MISMATCH", key, f"item {state} {'elegivel' if json_ok else 'esgotado'} no JSON (tentativas {item.get('attempts', 0)}/"
                                        f"{json_max_attempts}) mas evento {event['status']} {'elegivel' if store_ok else 'nao reivindicavel'} no SQLite "
                                        f"(tentativas {event.get('attempt')}/{event.get('max_attempts')})"))
    for idem, event in mirror.items():
        if idem not in matched:
            found.append(Divergence("ORPHAN_IN_STORE", idem, f"evento {event['status']} sem item na fila JSON"))
    return found


def collect(queue: list[dict], store) -> list[Divergence]:
    return compare(queue, store.events())


def _load():
    """(fila JSON, EventStore). Nao cria o banco: banco ausente e erro, nao divergencia."""
    from tools.orchestration import event_bridge as eb
    from tools.orchestration import store_factory
    path = store_factory.store_path()
    if not path.exists():
        raise FileNotFoundError(f"EventStore ausente: {path.name}")
    return eb.load()["queue"], store_factory.get_store()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="relatorio em JSON")
    ap.add_argument("--strict", action="store_true", help="evento do bridge sem item JSON tambem falha")
    ns = ap.parse_args(argv)
    try:
        queue, store = _load()
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:200]}) if ns.json else f"erro: {exc}")
        return 2
    found = collect(queue, store)
    orphans = [d for d in found if d.code == "ORPHAN_IN_STORE"]
    errors = [d for d in found if d.code != "ORPHAN_IN_STORE"]
    ok = not errors and not (ns.strict and orphans)
    if ns.json:
        print(json.dumps({"ok": ok, "divergences": [d.as_dict() for d in errors], "orphans": [d.as_dict() for d in orphans],
                          "warnings": len(orphans), "checked": {"queue": len(queue), "events": len(store.events())}},
                         ensure_ascii=True, indent=1))
    else:
        for d in [*errors, *orphans]:
            print(f"{d.code:16} {d.key}: {d.detail}")
        print(f"shadow_divergence: {len(errors)} divergencia(s), {len(orphans)} aviso(s) de orfao")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
