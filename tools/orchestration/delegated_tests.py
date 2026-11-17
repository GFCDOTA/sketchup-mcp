"""delegated_tests.py — validacao DISTRIBUIDA dos testes que comprovadamente nao rodam no AppContainer do revisor (FP-060 MT-03).

Por que existe: o sandbox do revisor (AppContainer sem capacidades, sem rede, sem os arquivos do usuario) NAO consegue operar o `git` (nao ha `git` no PATH e, mesmo com ele,
`git init` falha ao criar `.git/HEAD`: o AppContainer nao enxerga os ancestrais do workspace). Os testes que montam repositorios git de verdade erram la dentro por
FileNotFoundError, sem relacao com o codigo do PR. Em vez de reduzir o isolamento (ampliar permissao) ou de pular arquivos inteiros, cada um desses testes e DELEGADO ao CI.

Contrato (tudo fail-closed; qualquer duvida => a delegacao nao vale e o teste NAO e dispensado):
  1. A POLITICA e lida de uma referencia confiavel e imutavel — o commit da base (`origin/develop` resolvido para SHA) — com `git show <sha>:<caminho>`, nunca da arvore do PR. Um
     PR nao altera a propria politica: a politica do PR so passa a valer depois de mesclada (docs/governance e `.github/` ja exigem aprovacao humana) e um PR que TOCA a politica,
     o workflow ou o coletor perde a delegacao.
  2. A lista e de NODE IDs EXATOS (`tests/arquivo.py::teste` ou `...[param]`): sem curingas, sem arquivo inteiro, sem categoria. A deselecao dentro do sandbox e por IGUALDADE exata do
     node id (plugin do coordenador), nao por prefixo como o `--deselect` do pytest. Todos os demais testes rodam normalmente no AppContainer.
  3. Cada teste delegado exige EVIDENCIA INDIVIDUAL de execucao e aprovacao no CI para o HEAD exato: o workflow autorizado (definicao fixada pelo blob da base, disparado por
     `workflow_run`, entao a definicao vem da branch padrao e nao do PR) executa os node ids da politica contra o HEAD e publica um artefato; o revisor confere repositorio, workflow,
     SHA, execucao, tentativa, conclusao, integridade do artefato (digest que o GitHub calcula) e que CADA node id da politica esta `passed` (nunca skipped/xfail/ausente/extra).
  4. CI verde nunca substitui a revisao substantiva independente: este modulo so decide se os testes delegados contam como executados e aprovados.

Limite declarado: a evidencia vale o que vale o CI (o PR executa codigo la). Ela impede esquecimento, SHA velho, teste pulado e relatorio adulterado depois do job; nao e defesa contra
um autor malicioso que consiga mentir DENTRO do job — para isso existem a revisao do diff e o isolamento do AppContainer para todo o resto.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

POLICY_PATH = "docs/governance/sandbox_delegated_tests.v1.json"
WORKFLOW_PATH = ".github/workflows/delegated-tests.yml"
COLLECTOR_PATH = "tools/orchestration/delegated_results.py"
ARTIFACT_NAME = "delegated-test-results"
RESULT_FILE = "results.json"
BASE_BRANCH = "develop"                                              # branch padrao do repositorio (workflow_run so dispara da padrao; trocada de main em 2026-11-16)
RUN_TITLE_PREFIX = "delegated-tests "                                # `run-name` do workflow: prefixo + HEAD exato do PR
SCHEMA = 1
# Arquivos que o PR nunca pode alterar para manter a delegacao: a politica, o workflow que gera a evidencia e o coletor.
PROTECTED = (POLICY_PATH, WORKFLOW_PATH, COLLECTOR_PATH)
NODE_ID = re.compile(r"tests/[A-Za-z0-9_./-]+\.py::(?:[A-Za-z_][A-Za-z0-9_]*::)?[A-Za-z0-9_]+(?:\[[^\]\r\n]+\])?")   # `arquivo::teste` ou `arquivo::Classe::metodo` EXATO; id so de classe nunca casa item coletado (fail-closed)
MAX_DELEGATED = 96                                                   # teto duro: ampliar alem disto exige mudar o codigo (e revisar), nao so a lista. 64 -> 96 por decisao do proprietario em 2026-11-16 (28 do executor + 53 do laboratorio = 81)


class DelegationError(RuntimeError):
    """A politica ou a evidencia nao e confiavel: a delegacao nao vale (fail-closed)."""


@dataclass(frozen=True)
class Policy:
    ids: tuple[str, ...]
    workflow_path: str
    workflow_blob_sha: str
    base_sha: str
    reasons: dict = field(default_factory=dict)


def validate_policy(raw: object, base_sha: str) -> Policy:
    """Valida a estrutura e devolve a politica; qualquer desvio levanta `DelegationError`."""
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise DelegationError("politica sem schema 1")
    ci = raw.get("ci")
    if not isinstance(ci, dict) or ci.get("workflow_path") != WORKFLOW_PATH or ci.get("artifact_name") != ARTIFACT_NAME:
        raise DelegationError("politica: workflow/artefato fora do autorizado")
    pin = ci.get("workflow_blob_sha")
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{40}", pin):
        raise DelegationError("politica: `workflow_blob_sha` ausente ou invalido")
    items = raw.get("delegated")
    if not isinstance(items, list) or not items:
        raise DelegationError("politica sem testes delegados")
    if len(items) > MAX_DELEGATED:
        raise DelegationError(f"politica com {len(items)} testes: acima do teto de {MAX_DELEGATED}")
    ids, reasons = [], {}
    for entry in items:
        nid = entry.get("node_id") if isinstance(entry, dict) else None
        if (not isinstance(nid, str) or not NODE_ID.fullmatch(nid) or any(ch in nid.split("::", 1)[1].split("[")[0] for ch in "*?")
                or any(part in ("", ".", "..") for part in nid.split("::", 1)[0].split("/"))):     # sem travessia/segmento vazio: o arquivo fica SOB tests/
            raise DelegationError(f"node id invalido (so ids EXATOS; sem curinga, arquivo inteiro ou categoria): {str(nid)[:120]!r}")
        if nid in reasons:
            raise DelegationError(f"node id duplicado: {nid}")
        if not isinstance(entry.get("reason"), str) or not entry["reason"] or not isinstance(entry.get("sandbox_proof"), dict) or not entry["sandbox_proof"].get("first_error"):
            raise DelegationError(f"{nid}: sem motivo e prova individual de incompatibilidade ambiental")
        ids.append(nid)
        reasons[nid] = entry["reason"]
    if ids != sorted(ids):
        raise DelegationError("lista fora de ordem (mantida ordenada para diff auditavel)")
    return Policy(tuple(ids), WORKFLOW_PATH, pin, base_sha, reasons)


def trusted_base_sha(root: Path, run_git: Callable[[list, Path], tuple[int, str]], ref: str = "origin/develop") -> str:
    """Resolve a referencia confiavel para um SHA (imutavel durante a revisao). Atualiza `origin/develop` antes; sem resolucao, nada vale."""
    rc, out = run_git(["fetch", "-q", "origin", "develop"], root)
    if rc != 0:                                                       # sem atualizar, `origin/develop` local pode guardar uma politica VELHA: nada vale
        raise DelegationError(f"git fetch de origin/develop falhou (rc={rc}): {out.strip()[:120]}")
    rc, out = run_git(["rev-parse", "--verify", f"{ref}^{{commit}}"], root)
    sha = out.strip().lower()
    if rc != 0 or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise DelegationError(f"referencia confiavel {ref} nao resolvida: {out.strip()[:120]}")
    return sha


def load_policy(root: Path, run_git: Callable[[list, Path], tuple[int, str]], base_sha: str) -> Policy | None:
    """Politica da BASE (`git show <sha>:<caminho>` no repositorio do coordenador). `None` = a base ainda nao tem politica: nada e delegado. Politica invalida = erro."""
    rc, out = run_git(["cat-file", "-e", f"{base_sha}:{POLICY_PATH}"], root)
    if rc != 0:
        return None
    rc, text = run_git(["show", f"{base_sha}:{POLICY_PATH}"], root)
    if rc != 0:
        raise DelegationError("politica da base ilegivel")
    try:
        raw = json.loads(text)
    except ValueError as exc:
        raise DelegationError(f"politica da base nao e JSON: {exc}") from exc
    return validate_policy(raw, base_sha)


def eligible(policy: Policy | None, changed_files: list[str]) -> tuple[bool, str]:
    """A delegacao vale para ESTE PR? Nao se o PR toca a politica, o workflow, o coletor ou `.github/` (o PR nao muda a propria regra de validacao)."""
    if policy is None:
        return False, "a base nao tem politica de delegacao"
    touched = [p for p in changed_files if p in PROTECTED or p.startswith(".github/")]
    if touched:
        return False, "o PR altera a propria regra de validacao (" + ", ".join(sorted(touched)[:3]) + "): nenhum teste e delegado"
    return True, ""


def delegated_in_selection(policy: Policy, selected: list[str]) -> list[str]:
    """Node ids delegados cujo ARQUIVO esta entre os testes selecionados para a revisao (a selecao e por arquivo)."""
    chosen = {s.split("::", 1)[0] for s in selected}
    return [nid for nid in policy.ids if nid.split("::", 1)[0] in chosen]


# ---------------------------------------------------------------------------------------------------------------- plugin do coordenador
PLUGIN_NAME = "fp060_delegate"
PLUGIN_SOURCE = '''"""Plugin do COORDENADOR (nao do PR): deseleciona node ids EXATOS e relata o que fez."""
import json

IDS = frozenset(json.loads({ids_json!r}))
REPORT = {report!r}
_done = {{"deselected": [], "present": []}}


def pytest_collection_modifyitems(config, items):
    keep = []
    for item in items:
        _done["present"].append(item.nodeid)
        if item.nodeid in IDS:
            _done["deselected"].append(item.nodeid)
        else:
            keep.append(item)
    config.hook.pytest_deselected(items=[i for i in items if i.nodeid in IDS])
    items[:] = keep


def pytest_sessionfinish(session, exitstatus):
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump({{"deselected": sorted(_done["deselected"]), "requested": sorted(IDS), "not_collected": sorted(IDS - set(_done["present"]))}}, handle)
'''


def plugin_source(ids: list[str], report_path: str) -> str:
    return PLUGIN_SOURCE.format(ids_json=json.dumps(sorted(ids)), report=report_path)


# ---------------------------------------------------------------------------------------------------------------- evidencia do CI
def _api(gh, path: str):
    try:
        return gh(path)
    except Exception as exc:  # noqa: BLE001 — falha de comunicacao com o GitHub: sem evidencia, fail-closed
        raise DelegationError(f"GitHub indisponivel para a evidencia ({type(exc).__name__}): {str(exc)[:120]}") from exc


def verify_ci_evidence(gh, download: Callable[[str], bytes], repo: str, head_sha: str, policy: Policy,
                       run_git: Callable[[list, Path], tuple[int, str]], root: Path) -> dict:
    """Confere, para o HEAD EXATO, a evidencia individual de CADA teste delegado. Devolve os fatos (run, tentativa, digest); levanta `DelegationError` em qualquer inconsistencia."""
    head_sha = head_sha.lower()
    rc, blob = run_git(["rev-parse", f"{policy.base_sha}:{policy.workflow_path}"], root)
    if rc != 0 or blob.strip().lower() != policy.workflow_blob_sha:
        raise DelegationError("o workflow autorizado na base nao confere com o blob fixado na politica")
    # Semantica do `workflow_run` (docs do GitHub): a execucao roda no contexto da branch padrao — o `head_sha`/`head_branch` DELA sao a ponta da `develop` no disparo, nunca
    # o HEAD do PR. Por isso nao se filtra por `head_sha` do PR: a execucao e encontrada pelo titulo (`run-name` da definicao confiavel, com o HEAD do PR) e o `head_sha` dela
    # tem de ser um commit da base cujo workflow e o blob fixado. O `path` da API vem sem sufixo de ref. So as 100 execucoes mais recentes sao lidas (fail-closed se sair da janela).
    runs = _api(gh, f"repos/{repo}/actions/workflows/{Path(policy.workflow_path).name}/runs?event=workflow_run&branch={BASE_BRANCH}&status=completed&per_page=100")
    rows = runs.get("workflow_runs") if isinstance(runs, dict) else None
    if not isinstance(rows, list):
        raise DelegationError("lista de execucoes do workflow ilegivel")
    title = f"{RUN_TITLE_PREFIX}{head_sha}"
    good = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if (r.get("display_title") != title or r.get("event") != "workflow_run" or r.get("conclusion") != "success" or r.get("head_branch") != BASE_BRANCH
                or str(r.get("path", "")).partition("@")[0] != policy.workflow_path
                or str(r.get("path", "")).partition("@")[2] not in ("", BASE_BRANCH, f"refs/heads/{BASE_BRANCH}") or not re.fullmatch(r"[0-9a-f]{40}", str(r.get("head_sha", "")).lower())
                or (r.get("repository") or {}).get("full_name") != repo or (r.get("head_repository") or {}).get("full_name") != repo):
            continue
        good.append(r)
    if not good:
        raise DelegationError("nenhuma execucao do workflow autorizado, bem-sucedida, para este HEAD exato e este repositorio")
    run = max(good, key=lambda r: (int(r.get("run_number") or 0), int(r.get("run_attempt") or 0)))
    run_id, attempt = int(run["id"]), int(run.get("run_attempt") or 1)
    run_base = str(run["head_sha"]).lower()
    # a definicao que EXECUTOU e a do commit da base no disparo: tem de estar na historia da base atual e ter o workflow fixado
    rc, _ = run_git(["merge-base", "--is-ancestor", run_base, policy.base_sha], root)
    if rc != 0:
        raise DelegationError(f"a execucao rodou num commit ({run_base[:8]}) que nao esta na historia da base ({policy.base_sha[:8]})")
    rc, ran = run_git(["rev-parse", f"{run_base}:{policy.workflow_path}"], root)
    if rc != 0 or ran.strip().lower() != policy.workflow_blob_sha:
        raise DelegationError("o workflow que executou nao e o blob fixado na politica")
    arts = _api(gh, f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100")
    found = [a for a in (arts.get("artifacts") if isinstance(arts, dict) else None) or [] if isinstance(a, dict) and a.get("name") == ARTIFACT_NAME and not a.get("expired")]
    if len(found) != 1:
        raise DelegationError(f"esperava exatamente 1 artefato {ARTIFACT_NAME!r} valido na execucao {run_id}, achei {len(found)}")
    art = found[0]
    if str((art.get("workflow_run") or {}).get("head_sha", "")).lower() != run_base or int((art.get("workflow_run") or {}).get("id") or 0) != run_id:
        raise DelegationError("artefato nao pertence a execucao/HEAD verificados")
    try:
        blob_bytes = download(f"repos/{repo}/actions/artifacts/{art['id']}/zip")
    except Exception as exc:  # noqa: BLE001
        raise DelegationError(f"download do artefato falhou ({type(exc).__name__})") from exc
    digest = "sha256:" + hashlib.sha256(blob_bytes).hexdigest()
    if art.get("digest") != digest:
        raise DelegationError("integridade do artefato: o digest calculado pelo GitHub nao confere com o conteudo baixado")
    try:
        with zipfile.ZipFile(io.BytesIO(blob_bytes)) as z:
            names = z.namelist()
            if names != [RESULT_FILE]:
                raise DelegationError(f"artefato com conteudo inesperado: {names[:5]}")
            report = json.loads(z.read(RESULT_FILE).decode("utf-8"))
    except (zipfile.BadZipFile, ValueError, KeyError) as exc:
        raise DelegationError(f"artefato ilegivel ({type(exc).__name__})") from exc
    if not isinstance(report, dict):                                  # JSON valido que nao e objeto ([], "x", 3): rejeicao controlada, nunca AttributeError
        raise DelegationError(f"relatorio do artefato nao e um objeto JSON ({type(report).__name__})")
    want = {"schema": SCHEMA, "repository": repo, "head_sha": head_sha, "run_id": run_id, "run_attempt": attempt, "workflow_path": policy.workflow_path}
    for key, value in want.items():
        if (str(report.get(key)).lower() if key == "head_sha" else report.get(key)) != value:
            raise DelegationError(f"relatorio inconsistente em `{key}`: {report.get(key)!r} != {value!r}")
    # a base usada pelo CI pode ser anterior a `origin/develop` de agora: o que importa e que politica, workflow e coletor sejam BYTE A BYTE os mesmos nos dois commits
    used = str(report.get("policy_base_sha", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{40}", used):
        raise DelegationError("relatorio sem `policy_base_sha` valido")
    if used != run_base:
        raise DelegationError(f"o relatorio diz ter usado a base {used[:8]}, mas a execucao rodou em {run_base[:8]}")
    for path in PROTECTED:
        rc1, now = run_git(["rev-parse", f"{policy.base_sha}:{path}"], root)
        rc2, then = run_git(["rev-parse", f"{used}:{path}"], root)
        if rc1 != 0 or rc2 != 0 or now.strip() != then.strip():
            raise DelegationError(f"`{path}` difere entre a base usada pelo CI ({used[:8]}) e a base atual ({policy.base_sha[:8]}): evidencia de outra regra")
    results = report.get("results")
    if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
        raise DelegationError("relatorio sem `results`")
    seen: dict[str, str] = {}
    for r in results:
        nid = r.get("node_id")
        if not isinstance(nid, str) or nid in seen:
            raise DelegationError(f"resultado invalido ou duplicado: {str(nid)[:100]!r}")
        seen[nid] = str(r.get("outcome"))
    missing = sorted(set(policy.ids) - set(seen))
    extra = sorted(set(seen) - set(policy.ids))
    if missing or extra:
        raise DelegationError(f"resultados nao batem com a politica: ausentes={missing[:3]} extras={extra[:3]}")
    bad = sorted(n for n, o in seen.items() if o != "passed")
    if bad:
        raise DelegationError(f"{len(bad)} teste(s) delegado(s) nao passaram no CI (skipped/xfail/falha): {bad[:3]}")
    return {"run_id": run_id, "run_attempt": attempt, "head_sha": head_sha, "artifact_digest": digest, "workflow": policy.workflow_path, "policy_base_sha": policy.base_sha,
            "tests": len(seen)}


# ---------------------------------------------------------------------------------------------------------------- orquestracao
@dataclass
class Delegation:
    """O que o revisor sabe do PR para decidir a delegacao (tudo vem do coordenador/GitHub, nada da arvore do PR)."""
    gh: Callable
    repo: str
    head_sha: str
    changed_files: list[str]
    root: Path
    run_git: Callable[[list, Path], tuple[int, str]]
    download: Callable[[str], bytes] | None = None


def default_download(path: str) -> bytes:
    """Baixa o artefato com o `gh` do revisor (leitura). Qualquer falha levanta e vira `DelegationError` no chamador."""
    import os
    import subprocess
    out = subprocess.run([os.environ.get("GH_BIN", "gh"), "api", path], capture_output=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError((out.stderr or b"").decode("utf-8", "replace")[:200])
    return out.stdout


def plan(d: Delegation, selected: list[str]) -> dict:
    """Decide ANTES de rodar: quais node ids exatos serao deselecionados. Qualquer falha na politica => nada e deselecionado (os testes erram e o PR nao fica verde)."""
    try:
        base = trusted_base_sha(d.root, d.run_git)
        policy = load_policy(d.root, d.run_git, base)
        ok, why = eligible(policy, d.changed_files)
        if not ok:
            return {"active": False, "ids": [], "note": why}
        ids = delegated_in_selection(policy, selected)
        return {"active": bool(ids), "ids": ids, "policy": policy, "base_sha": base}
    except DelegationError as exc:
        return {"active": False, "ids": [], "error": str(exc)[:300]}


def settle(d: Delegation, planned: dict, facts: dict) -> dict:
    """Depois de rodar: confere que o plugin deselecionou EXATAMENTE os ids pedidos e exige a evidencia do CI. Devolve {ok, reasons, evidence}; fail-closed."""
    ids = planned["ids"]
    if not ids:
        return {"ok": True, "reasons": [], "evidence": None}
    rep = facts.get("delegation")
    if not isinstance(rep, dict) or sorted(rep.get("requested") or []) != sorted(ids):
        return {"ok": False, "reasons": ["relatorio de delecao do plugin ausente ou diferente do pedido"], "evidence": None}
    if rep.get("not_collected"):
        return {"ok": False, "reasons": [f"teste(s) delegado(s) nao coletado(s) no PR (removido/renomeado?): {rep['not_collected'][:3]}"], "evidence": None}
    if sorted(rep.get("deselected") or []) != sorted(ids):
        return {"ok": False, "reasons": ["o plugin deselecionou ids diferentes dos delegados"], "evidence": None}
    try:
        evidence = verify_ci_evidence(d.gh, d.download or default_download, d.repo, d.head_sha, planned["policy"], d.run_git, d.root)
    except DelegationError as exc:
        return {"ok": False, "reasons": [str(exc)[:300]], "evidence": None}
    return {"ok": True, "reasons": [], "evidence": evidence}
