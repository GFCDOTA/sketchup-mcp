"""auto_merge.py — merge automatico PROTEGIDO de PR do executor (FP-060 MT-15, #647). DESLIGADO por padrao.

    python -m tools.orchestration.auto_merge            # so o plano: decisao e motivos por PR candidato (nada e mesclado)
    python -m tools.orchestration.auto_merge --apply    # mescla o que a decisao autorizar (exige AUTOMERGE_ENABLED=1)

NAO e um caminho paralelo: o estado dos checks e a aprovacao vem de `lifecycle` (`checks_state`, `latest_review`), o teto de diff e os caminhos
criticos vem de `execution_guards` e a politica de revisores vem de `docs/governance/review_policy.json`. Este modulo so DECIDE e executa o merge;
nao altera protecao de branch, workflow, guarda nem politica, e o GitHub continua recusando o merge se a protecao da branch nao estiver satisfeita.

Politica (autorizada pelo proprietario em 2026-11-15; NENHUMA label manual de autorizacao e exigida para merge tecnico ordinario):
  DISABLED  `AUTOMERGE_ENABLED` != 1, ou o interruptor `AUTOMERGE_DISABLED` existe ao lado do estado do bridge.
  REFUSE    ha uma decisao que e HUMANA ou uma falha dura: PR de fork, rascunho, base != develop, autor que nao e o executor, label de decisao humana
            (seguranca, governanca, validacao visual, `aprovação-humana-pendente`, `blocked`...), Issue citada fechada/inexistente ou com decisao humana,
            PR sem `Refs #N`, diff que toca GOVERNANCA (`.github/`, `docs/governance/`, `.claude/`, `docs/adr/`: sempre humano), binario ou tipo fora de
            .py/.md/.txt/.json, checks reprovados, revisor independente pedindo mudancas, conflito de merge.
            PR AUTONOMO (label `executor-ok`, entregue pelo executor) mantem os tetos de diff e recusa QUALQUER caminho critico.
  REFORCADO PR tecnico (sem `executor-ok`) que toca caminho critico (`tools/orchestration/`, `tools/validation/`, geometria...) so e mesclado com
            revisao REFORCADA: toda Issue citada com `gpt-review-required` e aprovacao do revisor independente com confianca HIGH vinda do
            `codex_reviewer` (marcador do outbox, que so publica APPROVE com a prova de isolamento dos testes). Sem isso: WAIT.
  WAIT      nada decidido ainda: checks obrigatorios pendentes, sem aprovacao independente NO HEAD ATUAL, branch atrasada/bloqueada.
  MERGE     todos os checks obrigatorios verdes NO HEAD EXATO, aprovacao de revisor independente (autorizado, nao-executor) vinculada a esse mesmo HEAD
            e nenhuma decisao humana pendente. O merge usa `--match-head-commit`: um commit novo entre a decisao e o merge o recusa.
Conversas pendentes: os reviews do Codex nao abrem threads; a exigencia de "conversas resolvidas" e da protecao da branch (configuracao do proprietario).
O que NAO e: nao liga o merge automatico em producao (o padrao e DISABLED), nao aprova nem revisa nada, nao decide visual, nao usa `--auto`
(o merge nativo agendado nao verifica a identidade do revisor nem os caminhos; aqui o merge so ocorre depois que tudo isso foi verificado)."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tools.orchestration import event_bridge as eb
from tools.orchestration import execution_guards as guards
from tools.orchestration import lifecycle

ENABLE_ENV = "AUTOMERGE_ENABLED"
HARD_HUMAN_PREFIXES = (".github/", "docs/governance/", ".claude/", "docs/adr/")          # governanca: nunca automatico
GPT_LABEL = "gpt-review-required"
REINFORCED_BODY = re.compile(r"confianca\s+HIGH", re.I)


def outbox_provenance(store) -> Callable[..., bool]:
    """Prova de PROVENIENCIA que o texto de um review nao consegue forjar: o EventStore LOCAL registra, com producer `codex_reviewer` e status DONE, a publicacao do
    APPROVE deste repositorio, PR e HEAD (o `codex_reviewer` so conclui esse evento depois de gravar o parecer com a prova de isolamento dos testes). O marcador no
    corpo do review e publico; este registro nao."""
    def check(repo: str, number: int, head: str, review_id=None) -> bool:
        """Com `review_id`, o registro precisa ser DESSE review (o publicador grava o id que o GitHub devolveu): um APPROVE do Codex dispensado nao empresta a
        proveniencia a um review manual posterior que copie o marcador no mesmo HEAD."""
        base = f"review:{repo}#{int(number)}:{head}:APPROVE"
        try:
            for e in store.events(job_id=f"review:{repo}#{int(number)}"):
                if e["producer"] != "codex_reviewer" or e["status"] != "DONE" or not (e["idempotency_key"] == base or e["idempotency_key"].startswith(base + ":")):
                    continue
                if review_id is None:
                    return True
                try:
                    if str(json.loads(e.get("result") or "{}").get("review_id")) == str(review_id):
                        return True
                except ValueError:
                    continue
            return False
        except Exception:  # noqa: BLE001 — sem como consultar o registro local = sem prova (fail-closed)
            return False
    return check


def reinforced(review: dict | None, repo: str, number: int, head: str, provenance: Callable[[str, int, str], bool] | None = None) -> bool:
    """Aprovacao REFORCADA: o review e do revisor independente (ja filtrado por `latest_review`), diz `confianca HIGH`, carrega o marcador do outbox com EXATAMENTE este
    repositorio, PR, HEAD e veredito APPROVE E tem PROVENIENCIA no registro local do publicador (`provenance`; sem ela, nunca e reforcada: o texto de um review manual
    pode copiar o marcador). Marcador de outro PR/HEAD/veredito, ou so texto parecido, nao vale."""
    body = (review or {}).get("body") or ""
    marker = f"<!-- fp060-outbox-key:review:{repo}#{int(number)}:{head}:APPROVE -->"
    textual = bool(REINFORCED_BODY.search(body)) and marker in body and str((review or {}).get("commit_id", "")).lower() == head.lower()
    rid = (review or {}).get("id")                                         # a proveniencia e do REVIEW selecionado, nao so do HEAD
    return textual and rid is not None and provenance is not None and bool(provenance(repo, int(number), head, rid))
HUMAN_LABELS = frozenset({"aprovação-humana-pendente", "aprovacao-humana-pendente", "needs-human", "human-decision", "bloqueio:human-decision",
                          "visual-review", "security", "governance", "blocked", "do-not-merge"})
ALLOWED_SUFFIXES = (".py", ".md", ".txt", ".json")
FILES_API_CAP = 3000                                            # `GET /pulls/{n}/files` nunca devolve mais que isto, nem paginando
BASE_BRANCH = "develop"


@dataclass
class Decision:
    code: str                                                   # DISABLED | REFUSE | WAIT | MERGE
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"code": self.code, "reasons": self.reasons}


def kill_switch() -> Path:
    return eb.bridge_path().with_name("AUTOMERGE_DISABLED")


def enabled(env: dict | None = None) -> tuple[bool, str]:
    import os
    e = os.environ if env is None else env
    if kill_switch().exists():
        return False, f"interruptor {kill_switch().name} presente"
    if e.get(ENABLE_ENV) != "1":
        return False, f"{ENABLE_ENV} != 1 (padrao: desligado)"
    return True, ""


def _names(labels: object) -> set[str]:
    return {(x.get("name") if isinstance(x, dict) else x) for x in (labels or []) if isinstance(x, (dict, str))} - {None}


def numstat_from_files(files: list[dict]) -> str:
    """O formato de `git diff --numstat -z --no-renames` que `execution_guards.evaluate_diff` exige (registro terminado em NUL; binario = `-`)."""
    rows = []
    for f in files:
        add, rem = f.get("additions"), f.get("deletions")
        binary = f.get("patch") is None and not add and not rem and f.get("changes", 0) == 0          # sem patch e sem linhas, em QUALQUER status (inclusive `removed`): ambiguo = binario
        rows.append(f"{'-' if binary else add}\t{'-' if binary else rem}\t{f.get('filename')}")
        if f.get("previous_filename"):                                       # renomeacao: o caminho de ORIGEM tambem conta
            rows.append(f"0\t0\t{f['previous_filename']}")
    return "".join(f"{r}\0" for r in rows)


def decide(pr: dict, files: list[dict], runs: list[dict], reviews: list[dict], issues: dict[int, dict], policy: dict, cfg: guards.Config,
           is_enabled: tuple[bool, str] = (True, ""), provenance: Callable[[str, int, str], bool] | None = None) -> Decision:
    """Puro. `issues` mapeia numero -> Issue (REST) para cada `Refs #N` do PR; ausente = inexistente."""
    ok, why = is_enabled
    if not ok:
        return Decision("DISABLED", [why])
    if pr.get("merged") or pr.get("state") != "open":
        return Decision("REFUSE", ["PR nao esta aberto"])
    head = (pr.get("head") or {}).get("sha") or ""
    refuse: list[str] = []
    if pr.get("draft"):
        refuse.append("PR em rascunho")
    if (pr.get("base") or {}).get("ref") != BASE_BRANCH:
        refuse.append(f"base != {BASE_BRANCH}")
    if ((pr.get("head") or {}).get("repo") or {}).get("full_name") != ((pr.get("base") or {}).get("repo") or {}).get("full_name"):
        refuse.append("PR de fork")
    author = (pr.get("user") or {}).get("login")
    if author not in policy.get("executor_logins", []):
        refuse.append(f"autor {author!r} nao e o executor: so PR do executor e mesclado automaticamente")
    labels = {str(n).casefold() for n in _names(pr.get("labels"))}
    autonomous = cfg.label in labels                                           # PR entregue pelo executor: regras estritas
    human = sorted(labels & {x.casefold() for x in HUMAN_LABELS})
    if human:
        refuse.append(f"decisao humana pendente (label {', '.join(human)})")
    refs = sorted({int(n) for n in re.findall(r"\brefs?\s*:?\s*#(\d+)", pr.get("body") or "", re.I)})
    issue_labels: dict[int, set[str]] = {}
    if not refs:
        refuse.append("PR sem `Refs #N`")
    for n in refs:
        iss = issues.get(n)
        if not isinstance(iss, dict) or iss.get("state") != "open":
            refuse.append(f"Issue #{n} inexistente ou fechada")
            continue
        il = {str(x).casefold() for x in _names(iss.get("labels"))}
        issue_labels[n] = il
        if il & {x.casefold() for x in HUMAN_LABELS}:
            refuse.append(f"Issue #{n} tem decisao humana pendente ({', '.join(sorted(il & {x.casefold() for x in HUMAN_LABELS}))})")
    if not files:
        refuse.append("PR sem arquivos")
    declared = pr.get("changed_files")
    if not isinstance(declared, int) or isinstance(declared, bool) or declared != len(files) or declared > FILES_API_CAP:
        # A API lista no maximo 3000 arquivos mesmo paginando; sem `changed_files` igual ao recebido nao ha como provar que nenhum caminho de governanca,
        # binario ou tipo proibido ficou de fora: fail-closed.
        refuse.append(f"lista de arquivos nao comprovada completa (recebidos {len(files)}, `changed_files`={declared!r}, teto da API {FILES_API_CAP})")
    paths = [f.get("filename") for f in files] + [f["previous_filename"] for f in files if f.get("previous_filename")]
    hard = tuple(x.casefold() for x in HARD_HUMAN_PREFIXES)
    for p in paths:
        try:
            normalized = guards.norm(str(p))                                       # mesma normalizacao do executor: caixa, barras, `./`, `..`, NTFS
        except ValueError:
            refuse.append(f"caminho invalido: {p!r} (decisao humana)")
            continue
        if normalized.startswith(hard):
            refuse.append(f"governanca: {p} (decisao humana)")
    verdict = guards.evaluate_diff(numstat_from_files(files), cfg)
    critical = [v for v in verdict.violations if v["rule"] == "path_critico"]
    # PR autonomo: tetos e caminhos criticos valem integralmente. PR tecnico: so binario/ilegivel/invalido recusam; o caminho critico exige revisao reforcada.
    soft = {"path_critico", "max_files", "max_lines"}
    refuse += [f"{v['rule']}: {v['detail']}" for v in verdict.violations if autonomous or v["rule"] not in soft]
    for f in files:                                                                        # destino E origem de renomeacao: `deploy.sh` -> `deploy.py` toca um tipo proibido
        for name in (f.get("filename"), f.get("previous_filename")):
            if name and not str(name).lower().endswith(ALLOWED_SUFFIXES):
                refuse.append(f"tipo nao permitido: {name}")
    state = lifecycle.checks_state(runs)
    if state == "failed":
        refuse.append("checks obrigatorios reprovados no HEAD")
    review = lifecycle.latest_review(reviews, head, policy)
    if review is not None and review.get("state") == "CHANGES_REQUESTED":
        refuse.append(f"o revisor independente pede mudancas no HEAD atual (review {review.get('id')})")
    if (pr.get("mergeable_state") or "") == "dirty":
        refuse.append("conflito de merge")
    if refuse:
        return Decision("REFUSE", refuse)
    wait: list[str] = []
    if critical and not autonomous:
        no_gpt = [n for n in refs if GPT_LABEL not in issue_labels.get(n, set())]
        if no_gpt:
            wait.append(f"caminho critico: Issue(s) {', '.join('#%d' % n for n in no_gpt)} sem a label `{GPT_LABEL}` (revisao reforcada)")
        repo = ((pr.get("base") or {}).get("repo") or {}).get("full_name") or ""
        if review is not None and not reinforced(review, repo, pr.get("number") or 0, head, provenance):
            wait.append("caminho critico: a aprovacao nao e a reforcada (confianca HIGH + marcador do outbox deste repositorio, PR, HEAD e veredito APPROVE + registro "
                        "local do publicador)")
    if state != "passed":
        wait.append(f"checks obrigatorios {state}")
    if review is None:
        wait.append("sem aprovacao do revisor independente NO HEAD ATUAL")
    elif review.get("state") != "APPROVED":
        wait.append("review no HEAD atual nao e APPROVED")
    if (pr.get("mergeable_state") or "") != "clean":
        wait.append(f"mergeable_state={pr.get('mergeable_state')!r} (protecao da branch ainda nao satisfeita)")
    if wait:
        return Decision("WAIT", wait)
    return Decision("MERGE", [f"checks verdes e aprovacao (review {review['id']}) no HEAD {head[:12]}"])


# --------------------------------------------------------------------------------------------------------------- facts / effect
# Contrato do cliente `gh(path)` DESTE modulo: devolve o resultado COMPLETO (todas as paginas ja reunidas). O `eb.gh_json` do bridge (`--paginate`) nao serve para
# check-runs (objetos concatenados) e os helpers de `lifecycle` pedem pagina a pagina por cima dele (duplicaria): por isso o cliente de producao e `slurp_client`.
def slurp_client(path: str, runner=subprocess.run, gh_bin: str | None = None):
    """`gh api --paginate --slurp`: cada pagina vira um item de um array; reune as paginas (listas concatenadas; objetos com uma lista, como `check_runs`,
    concatenam a lista e mantem o `total_count`). Falha do `gh` levanta RuntimeError."""
    import os
    done = runner([gh_bin or os.environ.get("GH_BIN", "gh"), "api", "--paginate", "--slurp", path], capture_output=True, text=True, encoding="utf-8",
                  errors="replace", timeout=120)
    if done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout or "").strip()[:300] or f"gh api falhou ({done.returncode})")
    pages = json.loads(done.stdout or "[]")
    if not isinstance(pages, list) or not pages:
        raise RuntimeError("resposta paginada vazia ou malformada")
    if all(isinstance(p, list) for p in pages):
        return [x for p in pages for x in p]
    if all(isinstance(p, dict) for p in pages):
        merged = dict(pages[0])
        for key, value in pages[0].items():
            if isinstance(value, list):
                merged[key] = [x for p in pages for x in (p.get(key) or [])]
        return merged
    raise RuntimeError("paginas de tipos diferentes")


def complete_list(gh: eb.Gh, path: str) -> list[dict]:
    data = gh(path)
    if not isinstance(data, list) or any(not isinstance(x, dict) for x in data):
        raise RuntimeError(f"resposta de {path.split('?')[0]} nao e uma lista de objetos")
    return data


def complete_check_runs(gh: eb.Gh, repo: str, head: str) -> list[dict]:
    """Check-runs do HEAD COMPLETOS: `total_count` precisa bater com o que veio (fail-closed; parcial nunca vira `passed`)."""
    data = gh(f"repos/{repo}/commits/{head}/check-runs?per_page=100")
    if not isinstance(data, dict) or not isinstance(data.get("check_runs"), list):
        raise RuntimeError("resposta de check-runs malformada")
    if data.get("total_count") != len(data["check_runs"]):
        raise RuntimeError(f"check-runs incompletos: {len(data['check_runs'])} de {data.get('total_count')}")
    return data["check_runs"]


def gather(gh: eb.Gh, repo: str, number: int) -> tuple[dict, list[dict], list[dict], list[dict], dict[int, dict]]:
    """Fatos FRESCOS do GitHub para um PR (paginados e fail-closed: `lifecycle` levanta em resposta incompleta/malformada)."""
    pr = gh(f"repos/{repo}/pulls/{number}")
    if not isinstance(pr, dict):
        raise RuntimeError("resposta do PR nao e um objeto")
    head = (pr.get("head") or {}).get("sha") or ""
    files = complete_list(gh, f"repos/{repo}/pulls/{number}/files?per_page=100")
    runs = complete_check_runs(gh, repo, head)
    reviews = complete_list(gh, f"repos/{repo}/pulls/{number}/reviews?per_page=100")
    refs = sorted({int(n) for n in re.findall(r"\brefs?\s*:?\s*#(\d+)", pr.get("body") or "", re.I)})
    issues = {}
    for n in refs:
        try:
            iss = gh(f"repos/{repo}/issues/{n}")
            issues[n] = iss if isinstance(iss, dict) and "pull_request" not in iss else None
        except RuntimeError:
            issues[n] = None
    return pr, files, runs, reviews, {k: v for k, v in issues.items() if v}


def protection_gaps(gh: eb.Gh, repo: str, base: str = BASE_BRANCH) -> list[str]:
    """O que a protecao da branch ainda NAO garante. So LE (nunca altera a protecao: ela e configuracao do proprietario). Merge sem aprovacao independente nao pode
    acontecer nem com CI verde: a protecao precisa EXIGIR >= 1 aprovacao, descartar aprovacoes velhas quando o codigo muda e valer tambem para administradores.
    Protecao ilegivel (sem permissao, erro) = fail-closed."""
    try:
        prot = gh(f"repos/{repo}/branches/{base}/protection")
    except (RuntimeError, OSError, ValueError) as exc:
        return [f"protecao de {base} nao pode ser lida ({type(exc).__name__}): sem prova de que exige aprovacao, nao mescla"]
    if not isinstance(prot, dict):
        return [f"protecao de {base} em formato inesperado: nao mescla"]
    gaps = []
    reviews = prot.get("required_pull_request_reviews")
    count = reviews.get("required_approving_review_count") if isinstance(reviews, dict) else None
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        gaps.append(f"a protecao de {base} nao exige aprovacao de PR (required_approving_review_count >= 1)")
    elif not reviews.get("dismiss_stale_reviews"):
        gaps.append(f"a protecao de {base} nao descarta aprovacoes velhas quando o codigo muda (dismiss_stale_reviews)")
    if not (prot.get("enforce_admins") or {}).get("enabled"):
        gaps.append(f"a protecao de {base} nao vale para administradores (enforce_admins)")
    try:
        rules = gh(f"repos/{repo}/rules/branches/{base}")
    except (RuntimeError, OSError, ValueError) as exc:
        return [*gaps, f"regras de {base} nao podem ser lidas ({type(exc).__name__}): nao sei se ha fila de merge; nao mescla"]
    if not isinstance(rules, list) or any(not isinstance(r, dict) for r in rules):
        return [*gaps, f"regras de {base} em formato inesperado: nao mescla"]
    if any(r.get("type") == "merge_queue" for r in rules):
        gaps.append(f"{base} usa merge queue: o merge aconteceria DEPOIS, sem a revalidacao local (Issues, labels, base); o merge automatico fica desligado nesta branch")
    return gaps


def gh_bin() -> str:
    import os
    return os.environ.get("GH_BIN", "gh")


def merge_identity(policy: dict, runner=subprocess.run) -> tuple[bool, str]:
    """Quem o `gh` e, NO MESMO AMBIENTE do merge (`executor_env`: sem tokens de env, so o keyring): tem de ser um login executor autorizado e nunca um revisor.
    Remover o token do ambiente nao prova qual conta o keyring ativa; falha na consulta = recusa."""
    from tools.orchestration import event_executor as ex
    try:
        done = runner([gh_bin(), "api", "user", "--jq", ".login"], env=ex.executor_env(), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"identidade do gh nao verificada: {type(exc).__name__}"
    login = (done.stdout or "").strip()
    if done.returncode != 0 or not login:
        return False, "identidade do gh nao verificada: a consulta falhou"
    executors = {x.lower() for x in policy.get("executor_logins", [])}
    reviewers = {x.lower() for x in policy.get("reviewers", [])}
    if login.lower() in reviewers or login.lower() not in executors:
        return False, f"o gh esta autenticado como {login!r}, que nao e um executor autorizado (ou e revisor): o merge nao e feito com esta conta"
    return True, login


def merge(number: int, head: str, repo: str, runner=subprocess.run) -> tuple[bool, str]:
    """`gh pr merge --merge --match-head-commit <sha>` com a identidade do executor: o GitHub recusa se o HEAD mudou ou se a protecao nao vale."""
    from tools.orchestration import event_executor as ex
    if not re.fullmatch(r"[0-9a-f]{40}", head or ""):
        return False, f"HEAD invalido: {head!r}"
    try:
        done = runner([gh_bin(), "pr", "merge", str(int(number)), "--repo", repo, "--merge", "--match-head-commit", head],
                      env=ex.executor_env(), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"gh pr merge falhou: {type(exc).__name__}: {exc}"[:300]
    if done.returncode != 0:
        return False, f"gh pr merge recusado: {ex.redact((done.stderr or done.stdout or '')[:300])}"
    return True, "comando aceito"


DIVERGENT_HEAD = "HEAD_DIVERGENTE"


def confirm_merged(gh: eb.Gh, repo: str, number: int, head: str) -> tuple[bool, str]:
    """Exit 0 de `gh pr merge` NAO prova merge: com fila de merge ou auto-merge configurado o GitHub apenas AGENDA. So conta como mesclado o PR com `merged: true`,
    base develop e o commit de merge presente; qualquer outra coisa e reportada como NAO mesclado (agendado) e, se o PR ficou com auto-merge, o desliga."""
    try:
        pr = gh(f"repos/{repo}/pulls/{number}")
    except (RuntimeError, OSError, ValueError) as exc:
        return False, f"merge nao confirmado ({type(exc).__name__}): nao conto como mesclado"
    if isinstance(pr, dict) and pr.get("merged") is True and (pr.get("base") or {}).get("ref") == BASE_BRANCH and pr.get("merge_commit_sha"):
        merged_head = str((pr.get("head") or {}).get("sha") or "").lower()
        if merged_head != str(head).lower():                                 # outro ator mesclou OUTRO HEAD: sem prova do que foi autorizado, nunca e sucesso
            return False, f"{DIVERGENT_HEAD}: o PR foi mesclado com o HEAD {merged_head[:12] or '(ilegivel)'}, nao com o autorizado {str(head)[:12]}: REQUER INTERVENCAO do proprietario"
        return True, f"mesclado em {str(pr['merge_commit_sha'])[:12]}"
    return False, "o GitHub aceitou o comando mas o PR NAO esta mesclado (fila de merge/agendamento): nao conto como mesclado"


def default_provenance() -> Callable[[str, int, str], bool]:
    """O registro LOCAL do publicador (EventStore): so abre quando a decisao realmente precisa dele (caminho critico)."""
    def check(repo: str, number: int, head: str, review_id=None) -> bool:
        try:
            from tools.orchestration.store_factory import get_store
            return outbox_provenance(get_store())(repo, number, head, review_id)
        except Exception:  # noqa: BLE001 — sem registro local = sem prova
            return False
    return check


MUTABLE_FIELDS = ("state", "draft", "merged")


def mutable_facts(pr: dict) -> dict:
    """Os fatos mutaveis do PR que autorizam o merge e que `--match-head-commit` NAO cobre: base, labels, estado, rascunho e o CORPO (dele saem as Issues obrigatorias:
    acrescentar uma Issue de decisao humana ou remover as referencias depois da avaliacao muda a autorizacao sem mudar o HEAD)."""
    import hashlib
    body = pr.get("body")
    return {"base": (pr.get("base") or {}).get("ref"), "labels": sorted(str(n).casefold() for n in _names(pr.get("labels"))),
            "head": (pr.get("head") or {}).get("sha"), **{k: pr.get(k) for k in MUTABLE_FIELDS}, "auto_merge": bool(pr.get("auto_merge")),
            "body_sha": hashlib.sha256((body if isinstance(body, str) else "").encode("utf-8")).hexdigest()}


MERGED_DURING_CANCEL = "MERGED_DURING_CANCEL"


def cancel_scheduled(gh: eb.Gh, repo: str, number: int, policy: dict, runner=subprocess.run, head: str | None = None) -> tuple[bool | str, str]:
    """O comando foi aceito mas o PR so foi AGENDADO (auto-merge/fila): desliga o agendamento e CONFIRMA que sumiu. Se nao der para confirmar, e erro que exige
    intervencao humana (nunca deixa um merge futuro sem revalidacao). Se o PR aparecer MESCLADO nessa leitura, o merge e CONFERIDO como qualquer outro
    (`confirm_merged`: HEAD autorizado, base, commit de merge): confirmado => `MERGED_DURING_CANCEL`; HEAD divergente ou prova insuficiente => False (intervencao)."""
    from tools.orchestration import event_executor as ex
    try:
        done = runner([gh_bin(), "pr", "merge", str(int(number)), "--repo", repo, "--disable-auto"], env=ex.executor_env(), capture_output=True, text=True, timeout=120)
        after = gh(f"repos/{repo}/pulls/{number}")
    except (OSError, subprocess.SubprocessError, RuntimeError, ValueError) as exc:
        return False, f"agendamento NAO cancelado ({type(exc).__name__}): REQUER INTERVENCAO do proprietario no PR #{number}"
    if done.returncode == 0 and isinstance(after, dict) and not after.get("auto_merge") and after.get("merged") is not True:
        return True, "agendamento cancelado e confirmado (sem auto-merge no PR)"
    if isinstance(after, dict) and after.get("merged") is True:
        if head is None:
            return False, f"o PR #{number} foi mesclado durante o cancelamento e nao ha HEAD autorizado para conferir: REQUER INTERVENCAO do proprietario"
        ok, why = confirm_merged(gh, repo, number, head)
        if ok:
            return MERGED_DURING_CANCEL, f"mesclado durante o cancelamento, conferido: {why}"
        return False, f"mesclado durante o cancelamento SEM conferir o HEAD autorizado ({why}): REQUER INTERVENCAO do proprietario"
    return False, f"agendamento NAO confirmado como cancelado no PR #{number}: REQUER INTERVENCAO do proprietario"


def cycle(gh: eb.Gh, policy: dict, repo: str = eb.REPO, apply: bool = False, runner=subprocess.run, is_enabled: tuple[bool, str] | None = None,
          provenance: Callable[[str, int, str], bool] | None = None) -> dict:
    """Um ciclo: para cada PR aberto com a label `automerge-ok`, decide com fatos frescos e, so com `apply` e decisao MERGE, mescla (rechecando o HEAD)."""
    on = enabled() if is_enabled is None else is_enabled
    if not on[0]:
        return {"enabled": False, "reason": on[1], "prs": []}
    cfg = guards.load_config()
    provenance = provenance or default_provenance()
    out = []
    try:
        executors = set(policy.get("executor_logins", []))
        candidates = [p for p in complete_list(gh, f"repos/{repo}/pulls?state=open&per_page=100")
                      if not p.get("draft") and (p.get("user") or {}).get("login") in executors]
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        return {"enabled": True, "applied": apply, "prs": [{"pr": None, "code": "ERROR", "reasons": [f"listagem de PRs falhou: {type(exc).__name__}: {exc}"[:200]]}]}
    for cand in candidates:
        number = cand["number"]
        row: dict = {"pr": number}
        try:
            pr, files, runs, reviews, issues = gather(gh, repo, number)
            decision = decide(pr, files, runs, reviews, issues, policy, cfg, on, provenance)
            if decision.code == "MERGE":
                gaps = protection_gaps(gh, repo)
                if gaps:                                                                       # CI verde + aprovacao nao bastam se a protecao permitir merge sem revisao
                    decision = Decision("WAIT", [*gaps, "configuracao do proprietario: a protecao da branch precisa exigir aprovacao independente antes de qualquer merge automatico"])
            row.update(head=(pr.get("head") or {}).get("sha"), **decision.as_dict())
            if apply and decision.code == "MERGE":
                # Ordem: 1) a identidade (a chamada que pode demorar); 2) TODOS os fatos que autorizam o merge (base, labels, Issues, arquivos, checks, reviews, protecao,
                # fila) lidos e decididos DE NOVO; 3) o interruptor; 4) o merge. Nada mutavel e consultado ANTES da identidade. `--match-head-commit` protege so o HEAD:
                # a janela que sobra e UMA ida ao servidor (entre a ultima leitura e o merge); o GitHub nao oferece condicao atomica sobre base/labels, e quem a fecha no
                # servidor e a protecao da branch (aprovacao exigida + aprovacoes velhas descartadas), que o ciclo exige antes de qualquer merge.
                who_ok, who = merge_identity(policy, runner)
                if not who_ok:
                    row.update(code="REFUSE", reasons=[who])
                else:
                    pr2, files2, runs2, reviews2, issues2 = gather(gh, repo, number)
                    again = decide(pr2, files2, runs2, reviews2, issues2, policy, cfg, on, provenance)
                    gaps2 = protection_gaps(gh, repo) if again.code == "MERGE" else []
                    if gaps2:
                        again = Decision("WAIT", ["a protecao da branch deixou de garantir o merge so com aprovacao: " + "; ".join(gaps2)[:200]])
                    if again.code == "MERGE" and pr2.get("auto_merge"):
                        again = Decision("WAIT", ["o PR ja tem auto-merge/agendamento habilitado no GitHub: o merge nao seria revalidado"])
                    still_on = enabled() if is_enabled is None else is_enabled                # o interruptor e RELIDO imediatamente antes do comando de merge
                    if not still_on[0]:
                        row.update(code="DISABLED", reasons=[f"desligado durante o ciclo: {still_on[1]}"])
                    elif again.code != "MERGE" or (pr2.get("head") or {}).get("sha") != row["head"]:
                        row.update(code="WAIT", reasons=[f"os fatos mudaram entre a decisao e o merge ({again.code}: {'; '.join(again.reasons)[:160]})"])
                    else:
                        # ULTIMA leitura, COMPLETA (PR, arquivos, checks, reviews e as Issues obrigatorias) e decidida de novo, a uma ida ao servidor do merge: Issue fechada ou com
                        # label de decisao humana depois da leitura anterior tambem impede o merge. O interruptor e relido DEPOIS dela (imediatamente antes do comando).
                        pr3, files3, runs3, reviews3, issues3 = gather(gh, repo, number)
                        last = decide(pr3, files3, runs3, reviews3, issues3, policy, cfg, on, provenance)
                        still_on2 = enabled() if is_enabled is None else is_enabled
                        if not still_on2[0]:
                            row.update(code="DISABLED", reasons=[f"desligado durante a ultima leitura: {still_on2[1]}"])
                        elif not isinstance(pr3, dict) or mutable_facts(pr3) != mutable_facts(pr2) or last.code != "MERGE" or (pr3.get("head") or {}).get("sha") != row["head"]:
                            row.update(code="WAIT", reasons=["base, labels, estado, corpo ou Issues do PR mudaram na ultima leitura antes do merge: nada e mesclado nesta rodada"])
                        elif not isinstance(pr4 := gh(f"repos/{repo}/pulls/{number}"), dict) or mutable_facts(pr4) != mutable_facts(pr2):
                            # `gather` le o PR ANTES de arquivos/checks/reviews/Issues (consultas demoradas): base ou label podem mudar no meio. Esta releitura do PR e a
                            # ULTIMA chamada antes do comando. Janela residual (nao fechavel pela API: nao ha merge condicionado a base/labels): o tempo de UMA ida ao servidor
                            # entre esta leitura e o merge; quem a cobre no servidor e a protecao da branch (aprovacao exigida, aprovacoes velhas descartadas).
                            row.update(code="WAIT", reasons=["base, labels, estado ou corpo do PR mudaram depois das consultas da ultima leitura: nada e mesclado nesta rodada"])
                        else:
                            done, msg = merge(number, row["head"], repo, runner)
                            # QUALQUER desfecho do comando (aceito, recusado, timeout, erro de comunicacao) deixa o resultado REMOTO a provar: o GitHub pode ter aceito o comando e a
                            # resposta se perdeu. Sempre consulta o PR: mesclado => confirmado; senao desliga qualquer agendamento e CONFIRMA que sumiu; se nao for possivel
                            # reconciliar, ERROR com intervencao do proprietario (nunca um merge futuro sem revalidacao).
                            confirmed, cmsg = confirm_merged(gh, repo, number, row["head"])
                            if confirmed:
                                done, msg = True, cmsg
                            elif DIVERGENT_HEAD in cmsg:                                    # mesclado, mas NAO o HEAD autorizado: nada a cancelar, so intervencao
                                done, msg = False, cmsg
                                row.update(code="ERROR", reasons=[cmsg])
                            else:
                                cancelled, why = cancel_scheduled(gh, repo, number, policy, runner, head=row["head"])
                                msg = f"{msg}; {cmsg}; {why}" if not done else f"{cmsg}; {why}"
                                done = cancelled == MERGED_DURING_CANCEL                    # mesclado no HEAD AUTORIZADO enquanto cancelava: sucesso confirmado
                                if cancelled is False:
                                    row.update(code="ERROR", reasons=[why])
                            row.update(merged=done, merge_message=msg)
        except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
            row.update(code="ERROR", reasons=[f"{type(exc).__name__}: {exc}"[:200]])
        out.append(row)
    return {"enabled": True, "applied": apply, "prs": out}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="mescla o que for autorizado (exige AUTOMERGE_ENABLED=1); sem isto so planeja")
    ap.add_argument("--repo", default=eb.REPO)
    a = ap.parse_args(argv)
    report = cycle(slurp_client, eb.load_policy(), a.repo, a.apply)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 1 if any(p.get("code") == "ERROR" for p in report["prs"]) else 0


if __name__ == "__main__":
    sys.exit(main())
