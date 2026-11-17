"""github_review_target.py — destino GitHub do publicador do outbox: parecer de revisao independente (FP-060 M2, Issue #606).

Implementa o contrato `outbox_publisher.Target` para um review de PR. Nada neste modulo roda sozinho: ele so existe para ser
entregue ao publicador, e o publicador so o aciona com uma entrada de outbox. Os testes usam um GitHub em memoria; a prova
contra o GitHub real e o E2E num PR descartavel, que exige a identidade independente (`CODEX_REVIEWER_GH_TOKEN`).

Reconciliacao: cada review postado leva no corpo um marcador com a chave de idempotencia da entrada. `find` lista os reviews do
PR e so conta o marcador escrito pelo LOGIN do revisor independente — marcador no review do executor ou de terceiros e ignorado,
porque quem publica em nome da revisao e so o revisor. Se a listagem nao termina dentro do limite de paginas, `find` falha em vez
de afirmar que o efeito nao existe: sem reconciliacao nao ha envio.

Antes de postar, `send` revalida no GitHub: PR aberto, do proprio repositorio e HEAD igual ao SHA revisado (um parecer vale para
um commit so). O token do revisor so viaja no ambiente do processo `gh`, nunca na linha de comando, e e removido de qualquer mensagem
de erro.

O que isto NAO garante: que o GitHub nunca duplique (dois publicadores sem o mesmo `EventStore` podem postar a mesma chave ao
mesmo tempo) nem que a listagem de reviews seja imediatamente consistente apos o POST. Nao faz merge, nao altera labels, nao
resolve conversas e nao fala com ninguem alem do PR da entrada."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from tools.orchestration.outbox_publisher import TargetError

Api = Callable[..., Any]       # api(method, path, *, token=None, fields=None) -> JSON decodificado; levanta TargetError
PUBLISHABLE = ("APPROVE", "REQUEST_CHANGES")
REVIEW_STATE = {"APPROVE": "APPROVED", "REQUEST_CHANGES": "CHANGES_REQUESTED"}   # `event` do POST -> `state` que o GitHub devolve na listagem
ENV_KEEP = {"PATH", "SYSTEMROOT", "WINDIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "COMSPEC", "PATHEXT", "HOME"}
_SHA = re.compile(r"^[0-9a-f]{40}$")


def marker(key: str) -> str:
    """Marcador invisivel no corpo do review: e por ele que a reconciliacao acha o efeito."""
    return f"<!-- fp060-outbox-key:{key} -->"


GH_CALL_TIMEOUT_S = 60.0                                          # teto DURO de cada chamada `gh api` (o subprocesso e morto no timeout)
DISPOSABLE_MARKER = "<!-- fp060-disposable-e2e -->"               # marcador verificavel, no corpo, de PR DESCARTAVEL para a prova E2E


class NotDisposable(RuntimeError):
    """O PR nao e comprovadamente descartavel: a prova E2E nao publica nada nele."""


def require_disposable_pr(pr: object, reviewer: str) -> tuple[str, str]:
    """Guarda da prova E2E (sem `assert`, vale com `python -O`): PR aberto, em draft, com o marcador de descartavel no corpo, SEM arquivos alterados e de autor
    diferente do revisor. Devolve (head_sha, autor); qualquer desvio levanta `NotDisposable` ANTES de existir entrada no outbox."""
    if not isinstance(pr, dict):
        raise NotDisposable("resposta do PR ilegivel")
    problems = []
    if pr.get("state") != "open" or pr.get("draft") is not True:
        problems.append("precisa estar aberto e em draft")
    if DISPOSABLE_MARKER not in (pr.get("body") or ""):
        problems.append(f"corpo sem o marcador {DISPOSABLE_MARKER}")
    if pr.get("changed_files") != 0:
        problems.append(f"altera {pr.get('changed_files')!r} arquivo(s); precisa alterar 0")
    head, author = str((pr.get("head") or {}).get("sha") or ""), str((pr.get("user") or {}).get("login") or "")
    if not _SHA.match(head):
        problems.append("HEAD invalido")
    if not author or author == reviewer:
        problems.append("autor e revisor precisam ser contas diferentes")
    if problems:
        raise NotDisposable("PR nao e descartavel: " + "; ".join(problems))
    return head, author


def gh_api(method: str, path: str, *, token: str | None = None, fields: dict | None = None) -> Any:
    """Chamada real via `gh api`. O token vai so no ambiente do filho; falha vira `TargetError` sem o token."""
    argv = [shutil.which("gh") or "gh", "api", "-X", method, path]
    for name, value in (fields or {}).items():
        argv += ["-f", f"{name}={value}"]
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_KEEP}
    env["GH_PROMPT_DISABLED"] = "1"
    if token:
        env["GH_TOKEN"] = token
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=GH_CALL_TIMEOUT_S,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TargetError(f"gh api {method} indisponivel: {type(exc).__name__}") from exc
    if r.returncode != 0:
        raise TargetError(f"gh api {method} falhou: {_scrub((r.stderr or r.stdout).strip()[-300:], token)}")
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except ValueError as exc:
        raise TargetError(f"gh api {method}: resposta nao e JSON") from exc


def _scrub(text: str, token: str | None) -> str:
    return text.replace(token, "***") if token else text


class GitHubReviewTarget:
    # `send` faz um GET e um POST, cada um com teto de GH_CALL_TIMEOUT_S: o publicador mantem o lease por todo esse prazo (+ folga) antes de enviar. Sem idempotencia
    # atomica no GitHub (nao ha POST condicionado a chave), esse teto e o que impede outro publicador de reconciliar enquanto o POST ainda pode aparecer.
    send_timeout_s = 2 * GH_CALL_TIMEOUT_S

    def __init__(self, api: Api, *, token: str, reviewer: str, repo: str, page_size: int = 100, max_pages: int = 10):
        if not token or not reviewer or not repo:
            raise ValueError("token, reviewer e repo sao obrigatorios")
        self._api, self._token, self.reviewer, self.repo = api, token, reviewer, repo
        self.page_size, self.max_pages = page_size, max_pages

    def _call(self, method: str, path: str, fields: dict | None = None) -> Any:
        try:
            return self._api(method, path, token=self._token, fields=fields)
        except TargetError as exc:
            raise TargetError(_scrub(str(exc), self._token)) from None

    @staticmethod
    def _payload(entry: dict) -> dict:
        p = entry.get("payload")
        problems = []
        if not isinstance(p, dict):
            raise TargetError("payload invalido: nao e um objeto")
        if not isinstance(p.get("pr"), int) or isinstance(p.get("pr"), bool) or p["pr"] <= 0:
            problems.append("pr")
        if not isinstance(p.get("head_sha"), str) or not _SHA.match(p["head_sha"]):
            problems.append("head_sha")
        if p.get("verdict") not in PUBLISHABLE:
            problems.append("verdict")
        if not isinstance(p.get("body"), str) or not p["body"].strip():
            problems.append("body")
        if problems:
            raise TargetError("payload invalido: " + ", ".join(problems))
        return p

    def find(self, entry: dict) -> str | None:
        p = self._payload(entry)
        key = marker(entry["idempotency_key"])
        for page in range(1, self.max_pages + 1):
            rows = self._call("GET", f"repos/{self.repo}/pulls/{p['pr']}/reviews?per_page={self.page_size}&page={page}")
            if not isinstance(rows, list):
                raise TargetError("listagem de reviews em formato inesperado")
            for row in rows:
                if (row.get("user") or {}).get("login") == self.reviewer and key in (row.get("body") or ""):
                    # o marcador sozinho nao confirma o EFEITO: o review achado precisa ser do HEAD e do veredito da entrada; diferente = falha sem ACK nem novo POST
                    want_state = REVIEW_STATE.get(p["verdict"])
                    if str(row.get("commit_id", "")).lower() != p["head_sha"] or row.get("state") != want_state:
                        raise TargetError(f"review {row.get('id')} tem o marcador da chave mas outro efeito (commit {str(row.get('commit_id'))[:8]}, estado {row.get('state')!r}; "
                                          f"esperado {p['head_sha'][:8]}/{want_state}): nao reconcilio nem reenvio")
                    return f"github-review:{row['id']}"
            if len(rows) < self.page_size:
                return None
        raise TargetError(f"listagem de reviews nao terminou em {self.max_pages} paginas: nao afirmo que o efeito nao existe")

    def send(self, entry: dict) -> str:
        p = self._payload(entry)
        pr = self._call("GET", f"repos/{self.repo}/pulls/{p['pr']}")
        if pr.get("state") != "open":
            raise TargetError(f"PR #{p['pr']} nao esta aberto")
        head = pr.get("head") or {}
        if (head.get("repo") or {}).get("full_name") != self.repo:
            raise TargetError("PR de fork ou sem repositorio de origem: nao publico")
        if str(head.get("sha", "")).lower() != p["head_sha"]:
            raise TargetError(f"HEAD do PR mudou ({str(head.get('sha', ''))[:8]} != {p['head_sha'][:8]}): o parecer nao vale mais")
        review = self._call("POST", f"repos/{self.repo}/pulls/{p['pr']}/reviews",
                            {"event": p["verdict"], "commit_id": p["head_sha"],
                             "body": f"{p['body']}\n\n{marker(entry['idempotency_key'])}"})
        if not isinstance(review, dict) or "id" not in review:
            raise TargetError("resposta do GitHub sem id de review")
        return f"github-review:{review['id']}"


def from_policy(policy: dict, repo: str, api: Api = gh_api, *, token: str | None = None,
                gh_user: Callable[[str], str | None] | None = None) -> GitHubReviewTarget:
    """Monta o destino SO com identidade independente: login do token em `reviewers` e fora de `executor_logins`.
    `token=None` le `CODEX_REVIEWER_GH_TOKEN` (sem BOM). Nao usa, nem simula, a credencial do executor."""
    if token is None:
        token = os.environ.get("CODEX_REVIEWER_GH_TOKEN", "").strip().lstrip("﻿")
    if not token:
        raise TargetError("sem identidade independente: token do revisor ausente (nao uso a credencial do executor)")

    def default_user(value: str) -> str | None:
        try:
            return (api("GET", "user", token=value) or {}).get("login")
        except TargetError:
            return None

    login = (gh_user or default_user)(token)
    if not login:
        raise TargetError("token do revisor invalido (consulta do usuario falhou)")
    if login in policy.get("executor_logins", []):
        raise TargetError(f"o token e do executor ({login}): revisor deve ser independente")
    if login not in policy.get("reviewers", []):
        raise TargetError(f"login {login!r} nao esta em review_policy.reviewers")
    return GitHubReviewTarget(api, token=token, reviewer=login, repo=repo)
