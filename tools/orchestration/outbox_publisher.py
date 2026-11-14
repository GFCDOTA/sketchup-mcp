"""outbox_publisher.py — publicador do outbox do `EventStore` (FP-060 M2, Issue #606).

O `EventStore` grava a intencao de efeito externo na MESMA transacao que conclui o evento (`complete(..., outbox_entries=)`).
Este modulo e o lado que faltava: quem tira a entrada da fila e aplica o efeito. Uma entrada por chamada:

    claim (lease + fencing) -> alvo.find(entrada) -> [renova o lease -> alvo.send(entrada)] -> ACK

Regras:
  - **Reconciliar SEMPRE antes de enviar**, inclusive na primeira tentativa. Um publicador que morre depois do efeito e antes
    do ACK deixa um resultado desconhecido; o proximo pergunta ao alvo pela chave de idempotencia e so envia se nao achar.
  - **Sem reconciliacao nao ha envio.** Se o alvo nao consegue responder ao `find`, a entrada volta para a fila.
  - **ACK so do dono do lease.** Lease perdido antes do envio = nada enviado; perdido durante o envio = sem ACK, e o proximo
    publicador reconcilia.
  - Falha do alvo volta para a fila com atraso e vai para DLQ no limite de tentativas da entrada.

O que isto NAO garante: exactly-once no sistema externo. A entrega e "pelo menos uma tentativa + reconciliacao": depende de
o alvo conseguir achar o efeito pela chave. Dois envios simultaneos da mesma chave por processos que nao compartilham este
`EventStore` nao sao evitados aqui.

Nenhum alvo deste modulo fala com o GitHub: `LedgerTarget` e um arquivo local que faz o papel de sistema externo no
laboratorio e nos testes."""
from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from tools.orchestration.event_store import EventStore, LeaseLost


class TargetError(RuntimeError):
    """O alvo nao conseguiu reconciliar ou aplicar o efeito. A entrada volta para a fila (ou DLQ no limite)."""


class Target(Protocol):
    def find(self, entry: dict) -> str | None:
        """Referencia do efeito ja aplicado para `entry["idempotency_key"]`, ou None. Nunca aplica efeito."""

    def send(self, entry: dict) -> str:
        """Aplica o efeito e devolve a referencia dele. So e chamado depois de um `find` que devolveu None."""


class LedgerTarget:
    """Arquivo JSONL, uma linha por efeito: o "sistema externo" do laboratorio. O estado e o arquivo, nao a instancia."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def lines(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, ValueError) as exc:
            raise TargetError(f"ledger ilegivel: {type(exc).__name__}") from exc
        if any(not isinstance(row, dict) or "key" not in row for row in rows):
            raise TargetError("ledger ilegivel: linha sem chave")
        return rows

    def find(self, entry: dict) -> str | None:
        for number, row in enumerate(self.lines(), 1):
            if row["key"] == entry["idempotency_key"]:
                return f"ledger:{number}"
        return None

    def send(self, entry: dict) -> str:
        count = len(self.lines())
        line = json.dumps({"key": entry["idempotency_key"], "operation": entry["operation"], "payload": entry["payload"]},
                          sort_keys=True, ensure_ascii=True)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise TargetError(f"ledger nao gravavel: {type(exc).__name__}") from exc
        return f"ledger:{count + 1}"


def publish_one(store: EventStore, targets: Mapping[str, Target], owner: str, *, lease_seconds: float = 60.0,
                target: str | None = None, retry_delay: float = 1.0,
                after_send: Callable[[dict, str], None] | None = None) -> dict:
    """Publica NO MAXIMO uma entrada do outbox. `after_send` roda entre o efeito e o ACK (ponto de caos dos testes)."""
    claimed = store.claim_outbox(owner, lease_seconds, target)
    if claimed is None:
        return {"action": "IDLE"}
    entry = {**claimed, "payload": json.loads(claimed["payload"])}
    out = {"outbox": claimed["id"], "key": claimed["idempotency_key"], "target": claimed["target"]}
    try:
        handler = targets.get(claimed["target"])
        if handler is None:
            raise TargetError(f"alvo desconhecido: {claimed['target']}")
        reference, action = handler.find(entry), "RECONCILED"
        if reference is None:
            if not store.renew_outbox(claimed, lease_seconds):               # fencing: quem perdeu o lease nao envia
                raise LeaseLost(f"outbox {claimed['id']}: lease perdido antes do envio; nada enviado")
            reference, action = handler.send(entry), "SENT"
            if after_send:
                after_send(entry, reference)
        store.complete_outbox(claimed)
        return {"action": action, **out, "reference": reference, "attempt": claimed["attempts"]}
    except TargetError as exc:
        try:
            to = store.fail_outbox(claimed, str(exc), retry_delay)
        except LeaseLost as lost:
            return {"action": "LEASE_LOST", **out, "reason": str(lost)}
        return {"action": "FAILED", **out, "to": to, "reason": str(exc), "attempt": claimed["attempts"]}
    except LeaseLost as exc:
        return {"action": "LEASE_LOST", **out, "reason": str(exc)}


def drain(store: EventStore, targets: Mapping[str, Target], owner: str, *, limit: int = 20, **options) -> list[dict]:
    """Publica as entradas disponiveis agora, em ordem, ate a fila ficar ociosa ou `limit`. Entrada que falha volta com
    atraso (`retry_delay`), entao nao e reclamada de novo nesta drenagem."""
    results = []
    for _ in range(limit):
        result = publish_one(store, targets, owner, **options)
        if result["action"] == "IDLE":
            break
        results.append(result)
    return results
