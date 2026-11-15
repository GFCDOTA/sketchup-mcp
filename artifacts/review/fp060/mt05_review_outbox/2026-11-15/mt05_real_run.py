"""FP-060 MT-05: a funcao de PRODUCAO `codex_reviewer.publish_via_outbox` contra o GitHub real, num PR descartavel, com o processo
"morto" logo depois do POST. Uso: mt05_real_run.py <pr> <diretorio novo de saida>. O token vem de CODEX_REVIEWER_GH_TOKEN e nunca e impresso.
Nao ha Codex aqui: o veredito e fixo; o que se prova e a camada de publicacao."""
import json
import sys
import time
from pathlib import Path

from tools.orchestration import codex_reviewer as cr
from tools.orchestration import event_bridge as eb
from tools.orchestration import github_review_target as gt
from tools.orchestration.event_store import EventStore

PR, OUT = int(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True)                                         # falha se ja existir: nunca reaproveita uma execucao
REPO = eb.REPO


class Crash(BaseException):
    """O processo morre depois do POST e antes do ACK."""


token, why = cr.publisher_identity(eb.load_policy(), cr.gh_user_with)   # exige login em `reviewers` e fora de `executor_logins`
assert token, f"sem identidade independente: {why}"
pr = gt.gh_api("GET", f"repos/{REPO}/pulls/{PR}")                       # credencial do executor (keyring), so leitura
assert pr["state"] == "open" and pr["draft"] is True, "o PR descartavel precisa estar aberto e em draft"
head = pr["head"]["sha"]
verdict = {"pr": PR, "head_sha": head, "verdict": "REQUEST_CHANGES", "confidence": "HIGH", "tests_reviewed": [], "files_reviewed": [],
           "findings": [{"severity": "LOW", "file": "PR-descartavel", "line": 1,
                         "reason": "prova descartavel da publicacao via outbox (FP-060 MT-05): nenhum codigo foi revisado",
                         "required_change": "nenhuma; este PR sera fechado sem merge"}]}
key = cr.review_key(REPO, verdict)
store = EventStore(OUT / "events.db")
armed = {"on": True}


def chaos_api(method, path, *, token=None, fields=None):
    result = gt.gh_api(method, path, token=token, fields=fields)
    if method == "POST" and armed["on"]:
        armed["on"] = False
        raise Crash                                                     # o POST aconteceu; o processo "morre" antes de gravar o ACK
    return result


def reviews_with_key():
    rows = gt.gh_api("GET", f"repos/{REPO}/pulls/{PR}/reviews?per_page=100", token=token)
    return [r for r in rows if gt.marker(key) in (r.get("body") or "")]


def outbox():
    return [{"status": o["status"], "attempts": o["attempts"]} for o in store.outbox_entries()]


steps = []
try:
    cr.publish_via_outbox(verdict, token, REPO, api=chaos_api, store=store)
except Crash:
    steps.append({"step": "processo morto depois do POST e antes do ACK", "outbox": outbox(), "reviews_com_a_chave": len(reviews_with_key())})
url_during_lease = cr.publish_via_outbox(verdict, token, REPO, store=store)
steps.append({"step": "nova chamada com o lease do morto ainda valido", "outbox": outbox(), "reviews_com_a_chave": len(reviews_with_key()),
              "devolveu_url": bool(url_during_lease)})
time.sleep(cr.PUBLISH_LEASE_S + 2)
url_after_lease = cr.publish_via_outbox(verdict, token, REPO, store=store)
steps.append({"step": "nova chamada depois do lease expirar", "outbox": outbox(), "reviews_com_a_chave": len(reviews_with_key())})

found = reviews_with_key()
review = found[0] if found else {}
event = [e for e in store.events() if e["event_type"] == "REVIEW_REQUESTED"]
evidence = {
    "pr": PR, "head_sha": head, "autor_do_pr": pr["user"]["login"], "revisor": (review.get("user") or {}).get("login"), "chave": key, "steps": steps,
    "reviews_com_a_chave": len(found), "url": url_after_lease,
    "review": {"id": review.get("id"), "state": review.get("state"), "commit_id": review.get("commit_id")},
    "evento_de_publicacao": [{"status": e["status"], "producer": e["producer"]} for e in event], "outbox_final": outbox(),
    "verdict": "PASS" if (len(found) == 1 and url_during_lease == url_after_lease and outbox() == [{"status": "DONE", "attempts": 2}]
                          and review.get("commit_id") == head and review.get("state") == "CHANGES_REQUESTED"
                          and len(event) == 1 and event[0]["status"] == "DONE" and pr["user"]["login"] != (review.get("user") or {}).get("login")) else "FAIL",
}
(OUT / "evidence.json").write_text(json.dumps(evidence, indent=1, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(evidence, indent=1, ensure_ascii=True))
