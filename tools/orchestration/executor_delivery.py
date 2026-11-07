"""executor_delivery.py — entrega PELO EXECUTOR (nao pelo LLM) da correcao feita na worktree (FP-057/P8, Issue #589, regra R4).

Fail-closed e em tres barreiras de autorizacao (o review do Tech Lead exige):
  1. ANTES de tocar no indice e DE NOVO imediatamente antes do push: `revalidate()` (preflight no GitHub: PR aberto, mesmo repo, branch,
     HEAD == SHA revisado, review valido, label `executor-ok`, identidade do executor) + o HEAD remoto da branch == SHA revisado (`ls-remote`).
  2. Nada e staged em massa (sem add com flag -A): os candidatos vem de `git status -z`, cada caminho e validado (arquivo REGULAR, nao symlink, tipo
     permitido, nao critico, dentro da worktree) e so entao staged EXPLICITAMENTE; depois os modos do diff (`--raw`) recusam symlink/gitlink
     e `execution_guards` mede arquivos/linhas/binario/paths criticos.
  3. APOS os testes: revalidacao de integridade do indice (diff staged identico ao pre-teste) para detectar side effects de testes maliciosos.
Testes: so roda o que da para SELECIONAR com seguranca (testes alterados + `tests/test_<modulo>*.py` do codigo alterado); sem selecao
segura (codigo sem teste, fixtures/conftest, tipos sem teste) => BLOCKED, nada e publicado.
Sandbox: `run_checks` recusa execucao sem sandbox de SO (FP-060 P2); ambiente SEMPRE por allowlist (FP-060 7.1)."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import Callable

from tools.orchestration import execution_guards as guards

ALLOWED_SUFFIXES = (".py", ".md", ".txt", ".json")
SANDBOX_AVAILABLE = False

ENV_KEEP = {k.upper() for k in (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "OS", "USERNAME", "LANG", "LC_ALL", "PYTHONUTF8", "PYTHONIOENCODING", "PT_TO_M", "MPLBACKEND")}
SAFE_MODES = {"100644", "100755"}
Run = Callable[[list, Path], "tuple[int, str]"]
Revalidate = Callable[[], "tuple[bool, str]"]


def _git(args: list, cwd: Path) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


def _git_raw(args: list, cwd: Path) -> tuple[int, bytes]:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout


def status_candidates(wt: Path) -> list[tuple[str, str]]:
    """[(XY, caminho)] de `git status --porcelain=v1 -z --untracked-files=all` sem deteccao de renomeacao (cada caminho vira entrada propria)."""
    rc, raw = _git_raw(["-c", "status.renames=false", "status", "--porcelain=v1", "-z", "--untracked-files=all"], wt)
    if rc != 0:
        raise ValueError("git status falhou")
    out = []
    for rec in raw.decode("utf-8", "surrogateescape").split("\0"):
        if rec:
            out.append((rec[:2], rec[3:]))
    return out


def validate_candidate(wt: Path, rel: str, status: str, cfg: "guards.Config") -> str | None:
    """Motivo da recusa de um caminho candidato, ou None. Nao toca no indice."""
    try:
        rule = guards.is_critical(rel, cfg)
    except ValueError as exc:
        return str(exc)
    if rule:
        return f"{rel}: caminho critico (regra {rule})"
    name = Path(rel).name.lower()
    if name.startswith(".env") or name.startswith(".git") or name in ("conftest.py",) or "/fixtures/" in "/" + rel.replace("\\", "/"):
        return f"{rel}: arquivo nao autorizado (segredo/git/conftest/fixtures)"
    if not rel.lower().endswith(ALLOWED_SUFFIXES):
        return f"{rel}: tipo nao autorizado (permitido: {', '.join(ALLOWED_SUFFIXES)})"
    full = wt / rel
    if "D" not in status:                                                   # remocao: nada a inspecionar no disco
        try:
            st = os.lstat(full)                                             # lstat ANTES de resolver: nao segue o symlink
        except OSError:
            return f"{rel}: ilegivel"
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            return f"{rel}: nao e arquivo regular (symlink/diretorio/especial)"
    try:
        inside = full.parent.resolve(strict=False).is_relative_to(wt.resolve())   # resolve so o diretorio pai
    except OSError:
        inside = False
    if not inside:
        return f"{rel}: fora da worktree"
    return None


def raw_mode_violations(wt: Path, base: str) -> list[str]:
    """Modos do diff indice x base: recusa symlink (120000), gitlink (160000) e qualquer modo fora de 100644/100755 (remocao 000000 ok)."""
    rc, raw = _git_raw(["diff", "--cached", "--raw", "-z", "--no-renames", "--no-abbrev", base], wt)
    if rc != 0:
        return ["git diff --raw falhou"]
    parts = raw.decode("utf-8", "surrogateescape").split("\0")
    bad = []
    i = 0
    while i + 1 < len(parts) and parts[i].startswith(":"):
        meta, path = parts[i].split(), parts[i + 1]
        new_mode = meta[1] if len(meta) > 1 else "?"
        if new_mode != "000000" and new_mode not in SAFE_MODES:
            bad.append(f"{path}: modo {new_mode} nao permitido")
        i += 2
    return bad


def select_tests(files: list[str], root: Path) -> tuple[list[str] | None, str]:
    """(testes a rodar | None se NAO ha selecao segura, motivo). So docs (docs/**.md) dispensam testes."""
    tests: list[str] = []
    for f in files:
        p = f.replace("\\", "/")
        name = Path(p).name
        if p.startswith("docs/") and p.endswith((".md", ".txt")):
            continue
        if not p.endswith(".py"):
            return None, f"{p}: sem selecao segura de testes para este tipo de arquivo"
        if p.startswith("tests/"):
            if not name.startswith("test_"):
                return None, f"{p}: helper de teste (fixtures/conftest/util) pode afetar outros testes; sem selecao segura"
            tests.append(p)
            continue
        stem = Path(p).stem
        found = sorted(x.relative_to(root).as_posix() for x in (root / "tests").glob(f"test_{stem}*.py"))
        if not found:
            return None, f"{p}: codigo de producao sem teste correspondente (tests/test_{stem}*.py); nao publico sem prova"
        tests += found
    return sorted(set(tests)), ""


def _check_env() -> dict:
    """Ambiente dos processos de teste por ALLOWLIST: nada de token, segredo de nuvem, agente SSH ou variavel de CI herdado.
    Mesma politica do `event_executor.child_env`; nao e sandbox de SO (FP-060 P2)."""
    return {k: v for k, v in os.environ.items() if k.upper() in ENV_KEEP}


def run_checks(py: str, wt: Path, files: list, tests: list[str] | None = None) -> tuple[bool, str]:
    """ruff em todos os .py tocados e pytest na selecao. Falha => (False, trecho).
    Sem sandbox de SO (FP-060 P2): recusa execucao de testes nao confiaveis. Ambiente SEMPRE por allowlist.
    SANDBOX_AVAILABLE e a unica autoridade; nenhum parametro externo pode declarar isolamento."""
    if not SANDBOX_AVAILABLE:
        return False, "BLOCKED: execucao de testes requer sandbox de SO (FP-060 P2); edicoes preservadas na worktree"
    env = _check_env()
    pys = [f for f in files if f.endswith(".py")]
    chosen = tests if tests is not None else [f for f in pys if f.startswith("tests/") and Path(f).name.startswith("test_")]
    for argv in ([py, "-m", "ruff", "check", *pys] if pys else None, [py, "-m", "pytest", "-q", *chosen] if chosen else None):
        if not argv:
            continue
        r = subprocess.run(argv, cwd=wt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, env=env)
        if r.returncode != 0:
            return False, f"{' '.join(argv[2:4])} rc={r.returncode}: {(r.stdout + r.stderr).strip()[-400:]}"
    return True, ""


def remote_head(wt: Path, branch: str, run: Run) -> str | None:
    rc, out = run(["ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"], wt)
    return out.split()[0] if rc == 0 and out else None


def deliver(wt: Path, branch: str, base: str, py: str, item: dict, run: Run = _git, check=run_checks,
            cfg: "guards.Config | None" = None, revalidate: Revalidate | None = None) -> tuple[str, str]:
    """('NOOP'|'PUSHED'|'STALE'|'BLOCKED_GUARDS'|'FAILED_CHECKS'|'ERROR', msg). Nunca publica sem as duas barreiras de autorizacao."""
    cfg = cfg or guards.load_config()

    def authorized(stage: str) -> tuple[bool, str]:
        if revalidate is None:
            return False, f"sem revalidacao de autorizacao ({stage}): fail-closed"
        ok, why = revalidate()
        return ok, f"{stage}: {why}"

    ok, why = authorized("antes de stagear")
    if not ok:
        return "STALE", why
    if remote_head(wt, branch, run) != base:
        return "STALE", "HEAD remoto da branch difere do SHA revisado (alguem publicou): nao publico"
    rc, head = run(["rev-parse", "HEAD"], wt)
    if rc != 0:
        return "ERROR", f"rev-parse falhou: {head[:200]}"
    if head.strip().lower() != base.lower():
        # Commit local previo (tentativa anterior que nao publicou, ou qualquer outro) NAO passou pelos guards. Em vez de publica-lo,
        # devolve TODO o diff base..HEAD ao indice (`reset --soft`, conteudo intacto) e o submete aos MESMOS guards de uma edicao nova;
        # o que sai e um unico commit do executor sobre o SHA revisado.
        rc, _ = run(["merge-base", "--is-ancestor", base, "HEAD"], wt)
        if rc != 0:
            return "BLOCKED_GUARDS", f"HEAD local {head.strip()[:12]} nao descende do SHA revisado {base[:12]}: nao publico"
        rc, out = run(["reset", "--soft", base], wt)
        if rc != 0:
            return "ERROR", f"reset --soft para o SHA revisado falhou: {out[:200]}"
    try:
        cands = status_candidates(wt)
    except ValueError as exc:
        return "ERROR", str(exc)
    if len(cands) > cfg.max_files * 4:
        return "BLOCKED_GUARDS", f"{len(cands)} caminhos pendentes na worktree: acima do razoavel, nao stageio"
    refusals = [r for st, rel in cands if (r := validate_candidate(wt, rel, st, cfg))]
    if refusals:
        return "BLOCKED_GUARDS", "; ".join(refusals)[:400]
    paths = [rel for _st, rel in cands]
    if paths:
        rc, out = run(["add", "--", *paths], wt)                            # staging EXPLICITO da allowlist validada (nunca -A)
        if rc != 0:
            return "ERROR", f"git add falhou: {out[:200]}"

    def unstage() -> None:
        run(["reset", "-q"], wt)

    modes = raw_mode_violations(wt, base)
    if modes:
        unstage()
        return "BLOCKED_GUARDS", "; ".join(modes)[:400]
    rc, raw = _git_raw([*guards.NUMSTAT_ARGS[:1], "--cached", *guards.NUMSTAT_ARGS[1:], base], wt)
    if rc != 0:
        unstage()
        return "ERROR", "git diff --numstat falhou"
    numstat = raw.decode("utf-8", "replace")
    if not numstat:
        return "NOOP", "nenhuma alteracao em relacao ao HEAD revisado"
    verdict = guards.evaluate_diff(numstat, cfg)
    if not verdict.ok:
        unstage()
        return "BLOCKED_GUARDS", "; ".join(verdict.reasons())[:400]
    files = [path for _a, _r, path in guards.parse_numstat(numstat)]
    tests, why = select_tests(files, wt)
    if tests is None:
        unstage()
        return "BLOCKED_GUARDS", why
    rc_tree, tree_before = run(["write-tree"], wt)
    if rc_tree != 0:
        unstage()
        return "ERROR", "write-tree pre-teste falhou"
    ok, why = check(py, wt, files, tests)
    if not ok:
        return "FAILED_CHECKS", why
    rc_tree2, tree_after = run(["write-tree"], wt)
    if rc_tree2 != 0 or tree_after.strip() != tree_before.strip():
        unstage()
        return "BLOCKED_GUARDS", "indice alterado durante a execucao dos testes (possivel side effect): nao publico"
    post_modes = raw_mode_violations(wt, base)
    if post_modes:
        unstage()
        return "BLOCKED_GUARDS", "modo de arquivo alterado durante os testes: " + "; ".join(post_modes)[:300]
    rc, _ = run(["diff", "--cached", "--quiet"], wt)
    if rc != 0:
        msg = f"fix: atende review {item['event_id'].split(':')[1]} do PR #{item['pr']} (executor, Refs #{item['issue']})"
        rc, out = run(["commit", "-m", msg], wt)
        if rc != 0:
            return "ERROR", f"git commit falhou: {out[:200]}"
    rc, parent = run(["rev-parse", "HEAD^"], wt)                            # exatamente UM commit, o do executor, sobre o SHA revisado
    rc2, count = run(["rev-list", "--count", f"{base}..HEAD"], wt)
    if rc != 0 or rc2 != 0 or parent.strip().lower() != base.lower() or count.strip() != "1":
        return "BLOCKED_GUARDS", "o que seria publicado nao e exatamente um commit do executor sobre o SHA revisado: nao publico"
    ok, why = authorized("imediatamente antes do push")                     # TOCTOU: os checks levaram minutos
    if not ok:
        return "STALE", why
    if remote_head(wt, branch, run) != base:
        return "STALE", "HEAD remoto mudou durante a validacao: nao publico"
    rc, out = run(["push", "origin", f"HEAD:refs/heads/{branch}"], wt)      # push normal: git recusa nao-fast-forward
    if rc != 0:
        return "ERROR", f"git push recusado: {out[:200]}"
    return "PUSHED", f"{len(files)} arquivo(s), {verdict.lines} linha(s); publicado em {branch}"
