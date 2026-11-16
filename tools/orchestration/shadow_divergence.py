"""shadow_divergence.py — detector de divergencia entre a fila JSON do executor e o espelho no EventStore (FP-060 MT-07 / S1, #626).

    python -m tools.orchestration.shadow_divergence [--json] [--strict]     # exit 1 se houver divergencia

SOMENTE LEITURA: le a fila do bridge (JSON) e os eventos do EventStore; nunca escreve em nenhum dos dois. E o criterio de entrada do
cutover do executor para o SQLite: enquanto a fila JSON e o espelho nao concordam, trocar o caminho de execucao e trocar uma verdade por outra.

Como o espelho e produzido hoje (modo sombra, `event_executor._sync_result_to_store`): o bridge grava o evento `CORRECTION_REQUESTED` com a
chave `review:<id>:<pr>:<head_sha>` quando aceita o review; o evento fica PENDING durante TODO o trabalho do item JSON e so e atualizado
quando o item termina (DONE -> DONE; SUPERSEDED/REFUSED/PARKED -> SUPERSEDED; FAILED/BLOCKED -> PENDING com retry, ou DLQ no limite). Os pares
aceitos abaixo sao exatamente esses. Itens que nao sao review (comentarios) nao sao espelhados por desenho e sao ignorados.

Codigos: ORPHAN_EXECUTABLE (evento PENDING/RUNNING sem item JSON: SEMPRE divergencia), MISSING_IN_STORE (item sem evento), STALE_PENDING (item terminou e o evento segue PENDING: o sync se perdeu), STATE_MISMATCH (par fora
da tabela), UNKNOWN_STATE (estado JSON desconhecido; nunca presumido igual) e ORPHAN_IN_STORE (evento do bridge sem item JSON: aviso; so falha
com `--strict`, porque a fila JSON e podada)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

MIRROR_EVENT_TYPE = "CORRECTION_REQUESTED"
MIRROR_PRODUCER = "event_bridge"
MAX_ATTEMPTS = 3                                                    # `event_executor.MAX_ATTEMPTS`: um item JSON FAILED/BLOCKED com menos tentativas ainda pode ser escolhido
RETRYABLE = frozenset({"FAILED", "BLOCKED_CLI", "BLOCKED_CREDENTIALS", "BLOCKED_WORKTREE", "BLOCKED_REVIEW_FETCH"})
# Os estados que `event_executor.pick()` ainda pode escolher (com menos de MAX_ATTEMPTS tentativas). `BLOCKED_REVIEW_FETCH` e retomavel pelo bridge, mas o
# executor JSON NAO o escolhe: um evento PENDING espelhando-o seria trabalho que so o store executaria.
PICKABLE = frozenset({"QUEUED", "FAILED", "BLOCKED_CLI", "BLOCKED_CREDENTIALS", "BLOCKED_WORKTREE"})
EXECUTABLE_EVENT = frozenset({"PENDING", "RUNNING"})                 # um evento assim ainda pode ser reivindicado/executado
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


LATE_TOLERANCE_S = 60                  # atraso do evento em relacao ao JSON que ainda nao e divergencia (relogio/jitter de backoff)


def _epoch(iso: object) -> float | None:
    """`retry_after` do item JSON (ISO UTC, `%Y-%m-%dT%H:%M:%SZ`) em epoch; ausente/ilegivel = None (sem espera conhecida)."""
    import datetime as dt
    try:
        return dt.datetime.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    except ValueError:
        return None


def compare(queue: list[dict], events: list[dict], now: float | None = None) -> list[Divergence]:
    mirror = {e["idempotency_key"]: e for e in events if e.get("producer") == MIRROR_PRODUCER and e.get("event_type") == MIRROR_EVENT_TYPE}
    found, matched = [], set()
    for n, item in enumerate(queue):
        problem = invalid_item(item) if isinstance(item, dict) else "item que nao e objeto"
        if problem:
            raise ValueError(f"fila com item invalido #{n}: {problem}")           # nunca ignorar em silencio: um `ok` falso libera o cutover
        if item.get("kind") != "review":
            continue
        key, state = item["key"], item.get("state")
        event = mirror.get(mirror_key(item))
        if event is None:
            found.append(Divergence("MISSING_IN_STORE", key, f"item {state} sem evento {mirror_key(item)}"))
            continue
        matched.add(event["idempotency_key"])
        if state == "RUNNING":
            # o executor JSON ainda TRABALHA neste item: trocar a fonte agora deixaria o evento PENDING reivindicavel por um segundo executor (mesma correcao em
            # duplicidade). O cutover so e autorizado com a fila JSON DRENADA (nenhum item RUNNING).
            found.append(Divergence("JSON_RUNNING", key, "item RUNNING no executor JSON: o evento PENDING seria reivindicavel em paralelo; drene a fila JSON antes do cutover"))
        allowed = EXPECTED.get(state)
        if allowed is None:
            found.append(Divergence("UNKNOWN_STATE", key, f"estado JSON {state!r} fora da tabela; evento {event['status']}"))
        elif event["status"] not in allowed:
            code = "STALE_PENDING" if event["status"] == "PENDING" and state in FINISHED else "STATE_MISMATCH"
            found.append(Divergence(code, key, f"item {state} mas evento {event['status']} (esperado {'/'.join(sorted(allowed))})"))
        elif state in RETRYABLE or state == "QUEUED":                       # QUEUED tambem: um dry-run devolve o item a QUEUED e consome tentativa so no espelho
            pickable = state in PICKABLE and int(item.get("attempts") or 0) < MAX_ATTEMPTS               # o JSON ainda pode escolher este item?
            if event["status"] == "DLQ" and pickable:
                # o evento esgotou as tentativas (DLQ nao e reivindicavel), mas a fila JSON ainda pode escolher o item: trabalho retomavel seria abandonado no cutover
                found.append(Divergence("STATE_MISMATCH", key, f"item {state} com {item.get('attempts') or 0}/{MAX_ATTEMPTS} tentativas ainda executavel no JSON, mas evento DLQ"))
            elif event["status"] == "PENDING" and pickable:
                # os DOIS lados ainda executam: confere o ORCAMENTO de tentativas e a janela de espera, senao o cutover muda quantas vezes e quando o item roda
                json_left = MAX_ATTEMPTS - int(item.get("attempts") or 0)
                event_left = int(event.get("max_attempts") or MAX_ATTEMPTS) - int(event.get("attempt") or 0)
                if event_left < json_left:
                    found.append(Divergence("STATE_MISMATCH", key, f"orcamento de tentativas divergente: o JSON ainda tem {json_left}, o evento so {event_left}: uma falha apos o "
                                                                  "cutover levaria o item a DLQ antes da hora"))
                retry_at, t_now = _epoch(item.get("retry_after")), (time.time() if now is None else now)
                json_ready = max(retry_at or 0.0, t_now)                      # quando o executor JSON volta a poder escolher o item
                event_ready = max(float(event.get("available_at") or 0), t_now)    # quando o store passa a poder reivindicar o evento
                if event_ready < json_ready - 1:
                    # o JSON espera ate `retry_after`; o store ja poderia executar ANTES (disponivel agora OU num instante futuro anterior ao do JSON)
                    found.append(Divergence("STATE_MISMATCH", key, "o JSON aguarda `retry_after` mas o evento fica disponivel (`available_at`) antes dele: o store executaria antes do JSON"))
                elif event_ready > json_ready + LATE_TOLERANCE_S:
                    # o inverso: o JSON ja pode (ou poderia bem antes) executar o item e o evento so fica disponivel muito depois: o cutover ATRASA o trabalho
                    found.append(Divergence("STATE_MISMATCH", key, f"o evento so fica disponivel (`available_at`) {int(event_ready - json_ready)}s depois de o JSON poder executar o item "
                                                                  f"(tolerancia {LATE_TOLERANCE_S}s): o cutover atrasaria o trabalho"))
            elif event["status"] == "PENDING" and not pickable:
                # o inverso: o JSON NAO volta a escolher o item (tentativas esgotadas ou estado nao escolhido), mas o store ainda pode reivindicar o evento
                found.append(Divergence("STATE_MISMATCH", key, f"item {state} com {item.get('attempts') or 0}/{MAX_ATTEMPTS} tentativas que o executor JSON nao escolhe mais, "
                                                              "mas evento PENDING ainda reivindicavel no store"))
    for idem, event in mirror.items():
        if idem in matched:
            continue
        if event["status"] in EXECUTABLE_EVENT:
            # o bridge publica no SQLite ANTES de salvar a fila JSON: uma parada entre as duas deixa trabalho executavel so no store
            found.append(Divergence("ORPHAN_EXECUTABLE", idem, f"evento {event['status']} sem item na fila JSON: pode ser executado a partir do store sem existir na fila fonte"))
        else:
            found.append(Divergence("ORPHAN_IN_STORE", idem, f"evento {event['status']} sem item na fila JSON (terminal)"))
    return found


def collect(queue: list[dict], store) -> list[Divergence]:
    return compare(queue, store.events())


class ReadOnlyStore:
    """Os eventos do SQLite lidos em modo `ro`: nao cria arquivo, esquema nem linha, nao muda o journal. Escrever aqui falha."""

    def __init__(self, path: Path):
        self.path = path

    def events(self) -> list[dict]:
        db = sqlite3.connect(Path(self.path).resolve().as_uri() + "?mode=ro", uri=True, timeout=15)
        try:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id")]
        finally:
            db.close()


def read_queue(path: Path) -> list[dict]:
    """A fila JSON REAL: o arquivo tem de existir e ter `queue` explicita (lista de objetos). Ausente/ilegivel/sem `queue` e ERRO, nunca "fila vazia"."""
    if not path.is_file():
        raise FileNotFoundError(f"fila JSON ausente: {path.name}")
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"fila JSON ilegivel ({type(exc).__name__}): {path.name}") from exc
    queue = data.get("queue") if isinstance(data, dict) else None
    if not isinstance(queue, list) or any(not isinstance(i, dict) for i in queue):
        raise ValueError(f"fila JSON sem `queue` (lista de objetos): {path.name}")
    for n, it in enumerate(queue):
        problem = invalid_item(it)
        if problem:
            raise ValueError(f"fila JSON com item invalido #{n}: {problem}")
    return queue


def invalid_item(item: dict) -> str:
    """'' se o item da fila tem os campos e tipos que a comparacao usa; senao o problema (so nomes de campo, nunca o conteudo). Um item sem `kind` ou sem chave
    seria ignorado ou quebraria a comparacao e poderia virar um `ok` falso: invalido e erro estruturado, nao divergencia."""
    kind = item.get("kind")
    if not isinstance(kind, str) or not kind:
        return "campo `kind` ausente ou nao-texto"
    if kind != "review":
        return ""                                                    # comentarios nao sao espelhados: so exigem o `kind`
    for field in ("key", "state", "event_id", "head_sha"):
        if not isinstance(item.get(field), str) or not item[field]:
            return f"review sem `{field}` (texto nao vazio)"
    if not isinstance(item.get("pr"), int) or isinstance(item.get("pr"), bool):
        return "review com `pr` que nao e inteiro"
    retry_after = item.get("retry_after")
    if retry_after not in (None, "") and _epoch(retry_after) is None:
        return "review com `retry_after` que nao e um instante ISO UTC (AAAA-MM-DDTHH:MM:SSZ)"       # o JSON compara como texto: um valor ilegivel tem semantica propria, nunca "sem espera"
    attempts = item.get("attempts")
    if attempts is not None and (not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 0):
        return "review com `attempts` que nao e inteiro >= 0"
    return ""


def _load():
    """(fila JSON, eventos somente leitura). Nao cria nada: fonte ausente ou invalida e erro, nao divergencia."""
    from tools.orchestration import event_bridge as eb
    from tools.orchestration import store_factory
    path = store_factory.store_path()
    if not path.is_file():
        raise FileNotFoundError(f"EventStore ausente: {path.name}")
    return read_queue(eb.bridge_path()), ReadOnlyStore(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="relatorio em JSON")
    ap.add_argument("--strict", action="store_true", help="orfao TERMINAL (evento ja concluido sem item JSON) tambem falha; orfao executavel sempre falha")
    ns = ap.parse_args(argv)
    try:
        queue, store = _load()
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:200]}) if ns.json else f"erro: {exc}")
        return 2
    try:
        found = collect(queue, store)
    except (sqlite3.Error, ValueError) as exc:
        kind = "sqlite" if isinstance(exc, sqlite3.Error) else "fila"
        print(json.dumps({"ok": False, "error": f"{kind}: {exc}"[:200]}) if ns.json else f"erro: {kind}: {exc}")
        return 2
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
