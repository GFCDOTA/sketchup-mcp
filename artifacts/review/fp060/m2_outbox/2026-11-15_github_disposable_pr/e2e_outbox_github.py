"""FP-060 M2: publicacao de um review pela conta independente via outbox, com morte entre o POST e o ACK, num PR descartavel.

Uso: e2e_outbox_github.py <pr> <diretorio novo de saida>. O token vem de CODEX_REVIEWER_GH_TOKEN e nunca e impresso."""
import json
import os
import sys
import time
from pathlib import Path

from tools.orchestration import event_bridge as eb
from tools.orchestration import github_review_target as gt
from tools.orchestration import outbox_publisher as op
from tools.orchestration.event_store import EventStore

PR, OUT = int(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True)                                   # falha se ja existir: nunca reaproveita uma execucao
LEASE_S = 5.0


class Crash(BaseException):
    """O publicador morre depois do efeito externo e antes do ACK."""


target = gt.from_policy(eb.load_policy(), eb.REPO)        # recusa executor, login fora de `reviewers` ou token ausente
token = os.environ["CODEX_REVIEWER_GH_TOKEN"].strip().lstrip("﻿")
pr = gt.gh_api("GET", f"repos/{eb.REPO}/pulls/{PR}")      # credencial do executor (keyring), so leitura
# guarda EXPLICITA (vale com `python -O`): aberto, draft, marcador de descartavel no corpo, 0 arquivos alterados, autor != revisor; senao nada entra no outbox
head, author = gt.require_disposable_pr(pr, target.reviewer)

key = f"fp060-m2-e2e:pr{PR}:{head}:REQUEST_CHANGES"
body = ("Codex CLI (revisor independente) — prova DESCARTAVEL de publicacao via outbox (FP-060 M2, #606).\n"
        "Nenhum codigo foi revisado: o PR nao altera arquivo. O review existe so para provar que, com o publicador morto "
        "entre o POST e o ACK, a reconciliacao acha o review e nao posta outro.")
store = EventStore(OUT / "events.db")
store.publish("REVIEW_REQUESTED", f"ev:{key}", "job:fp060-m2-e2e", {})
ev = store.claim("REVIEW_REQUESTED", "worker", 60)
store.complete(ev, {"verdict": "REQUEST_CHANGES"}, outbox_entries=[{
    "target": "github", "operation": "publish_review", "idempotency_key": key,
    "payload": {"pr": PR, "head_sha": head, "verdict": "REQUEST_CHANGES", "body": body}}])
targets = {"github": target}


def reviews_with_key() -> list[dict]:
    rows = gt.gh_api("GET", f"repos/{eb.REPO}/pulls/{PR}/reviews?per_page=100", token=token)
    return [r for r in rows if gt.marker(key) in (r.get("body") or "")]


def outbox() -> list[dict]:
    return [{"id": o["id"], "status": o["status"], "attempts": o["attempts"]} for o in store.outbox_entries()]


steps = []


def die(entry, reference):
    raise Crash


try:
    op.publish_one(store, targets, "pub-1", lease_seconds=LEASE_S, after_send=die)
except Crash:
    steps.append({"step": "publicador 1 morreu depois do POST e antes do ACK", "outbox": outbox(), "reviews_com_a_chave": len(reviews_with_key())})
steps.append({"step": "publicador 2 logo depois (lease do morto ainda vale)", "resultado": op.publish_one(store, targets, "pub-2", lease_seconds=LEASE_S),
              "reviews_com_a_chave": len(reviews_with_key())})
time.sleep(max(LEASE_S, target.send_timeout_s + op.SEND_MARGIN_S) + 1)   # o lease do morto cobre o teto do envio (GET + POST), nao so LEASE_S
second = op.publish_one(store, targets, "pub-2", lease_seconds=LEASE_S)
steps.append({"step": "publicador 2 depois do lease expirar", "resultado": second, "outbox": outbox(), "reviews_com_a_chave": len(reviews_with_key())})
steps.append({"step": "publicador 2 de novo", "resultado": op.publish_one(store, targets, "pub-2", lease_seconds=LEASE_S)})

found = reviews_with_key()
review = found[0] if found else {}
evidence = {
    "pr": PR, "head_sha": head, "autor_do_pr": author, "revisor": target.reviewer, "chave": key, "steps": steps,
    "reviews_com_a_chave": len(found),
    "review": {"id": review.get("id"), "login": (review.get("user") or {}).get("login"), "state": review.get("state"),
               "commit_id": review.get("commit_id"), "url": review.get("html_url")},
    "outbox_final": outbox(),
    "verdict": "PASS" if (len(found) == 1 and second.get("action") == "RECONCILED" and second.get("attempt") == 2
                          and outbox() == [{"id": 1, "status": "DONE", "attempts": 2}]
                          and review.get("commit_id") == head and (review.get("user") or {}).get("login") == target.reviewer) else "FAIL",
}
(OUT / "evidence.json").write_text(json.dumps(evidence, indent=1, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(evidence, indent=1, ensure_ascii=True))
