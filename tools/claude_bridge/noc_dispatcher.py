"""NOC dispatcher — o ATUADOR que faltava: poe Claude pra trabalhar, nao so vigia.

Um ciclo seguro:
  lock (1 atuador) -> pega 1 task SEGURA da fila -> guarda de colisao ->
  worktree ISOLADO off origin/develop (fora do glob sketchup-mcp*) ->
  `claude -p` escopado SO aquele worktree -> verify DETERMINISTICO ->
  commit + push da BRANCH (NUNCA main, NUNCA auto-merge) -> ledger.

Rails (por que e seguro deixar agir):
- lock com TTL: nunca 2 atuadores ao mesmo tempo (base do DIFF-004).
- isolacao por worktree: o worker nao enxerga/edita o tree de uma sessao viva.
- worker e PROIBIDO de tocar main/outros worktrees ou dar push/merge (prompt + o
  dispatcher e quem comita).
- verify deterministico antes de manter qualquer coisa; falhou -> descarta a branch.
- mudanca de APARENCIA de planta -> NAO auto-aprova: enfileira VISUAL_REVIEW pro humano.
- roda PARALELO ao NOC read-only; nao mata/reinicia peers.

Uso:
  python -m tools.claude_bridge.noc_dispatcher --once --dry-run     # prova o loop sem Claude
  python -m tools.claude_bridge.noc_dispatcher --once               # 1 ciclo real
  python -m tools.claude_bridge.noc_dispatcher --once --task-id T1  # task especifica
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Segredos NUNCA vao pro ledger/stdout (o worker pode ecoar token em erro de auth).
_SECRET_RE = re.compile(r"sk-ant-[A-Za-z0-9_\-]+")


def _redact(s):
    return _SECRET_RE.sub("sk-ant-***REDACTED***", s) if isinstance(s, str) else s

REPO_ROOT = Path(__file__).resolve().parents[2]
# Estado NOC e' relativo ao tree onde se roda. Dispatcher e cockpit compartilham
# quando rodam do MESMO tree (o normal pos-merge: ambos no main).
NOC_DIR = REPO_ROOT / ".ai_bridge" / "noc"
QUEUE = NOC_DIR / "queue.jsonl"
LEDGER = NOC_DIR / "actions.jsonl"
LOCK_PATH = NOC_DIR / "dispatcher.lock"
WT_PARENT = REPO_ROOT.parent  # E:/Claude — worktrees ficam FORA do glob sketchup-mcp*

MODEL = "claude-opus-4-8"
CLAUDE_TIMEOUT = 900  # 15 min por worker; estoura -> falha o ciclo, nao trava

# --- kind:local_llm (papel "Ollama = compute gratis" do brain_muscle.md) ----------
# Purposes que PODEM rodar em modelo local (texto barato, sem editar repo nem julgar
# visual). Fora desta lista -> SKIPPED_PURPOSE_NOT_ALLOWED (nada vaza pro local).
LOCAL_LLM_OK = {
    "summarize_log", "classify_test_failure", "draft_design_intent",
    "checklist_from_reference", "prompt_prepare", "cheap_triage",
}
# Modelo default por purpose (override por task["model"]). Medido nesta maquina:
# llama3.1:8b frio ~25s/quente <0.2s; qwen2.5-coder:14b ~3s. Token = 0 sempre.
DEFAULT_MODEL_BY_PURPOSE = {
    "summarize_log": "llama3.1:8b",
    "classify_test_failure": "qwen2.5-coder:14b",
    "draft_design_intent": "planta-assistant:latest",
    "checklist_from_reference": "llama3.1:8b",
    "prompt_prepare": "llama3.1:8b",
    "cheap_triage": "llama3.1:8b",
}
# Texto gerado vai pro scratch gitignored (runs/); o ledger (.ai_bridge/noc) audita
# so backend/model/latency/out_file — nunca o corpo verboso no contexto do cerebro.
LOCAL_LLM_DIR = REPO_ROOT / "runs" / "local_llm"
LOCAL_LLM_TERMINAL = {"LOCAL_LLM_DONE", "LOCAL_LLM_OFFLINE", "SKIPPED_PURPOSE_NOT_ALLOWED"}


def _claude_bin() -> str:
    return shutil.which("claude") or shutil.which("claude.cmd") or "claude"


# Token files candidatos (mesmos do start.ps1/watchdog). NUNCA logar o conteudo.
_TOKEN_FILES = (
    REPO_ROOT / "tools" / "claude_bridge" / ".oauth_token",
    Path(r"E:\Claude\claude-bridge\.oauth_token"),
)


def _worker_env() -> dict:
    """Env do worker com o OAuth token (senao `claude -p` da 'Not logged in')."""
    env = dict(os.environ)
    for tf in _TOKEN_FILES:
        try:
            tok = tf.read_text("utf-8-sig").strip().lstrip("﻿")  # utf-8-sig: mata o BOM
        except OSError:
            continue
        if tok:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = tok
            break
    return env


def _bash():
    """Git Bash REAL (o `bash` do PATH no Windows e o WSL, que aqui esta quebrado)."""
    for p in (r"C:\Program Files\Git\bin\bash.exe",
              r"C:\Program Files\Git\usr\bin\bash.exe",
              r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if Path(p).is_file():
            return p
    return None


def _run(cmd, cwd=None, timeout=120):
    p = subprocess.run(cmd, cwd=cwd and str(cwd), capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def _git(args, cwd=REPO_ROOT, timeout=120):
    return _run(["git", *args], cwd=cwd, timeout=timeout)


def load_queue() -> list:
    if not QUEUE.is_file():
        return []
    out = []
    for line in QUEUE.read_text("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def _ledger_rows() -> list:
    if not LEDGER.is_file():
        return []
    rows = []
    for line in LEDGER.read_text("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def ledger_append(entry: dict) -> None:
    NOC_DIR.mkdir(parents=True, exist_ok=True)
    line = _redact(json.dumps(entry, ensure_ascii=False))  # safety-net: zero segredo no ledger
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _terminal_ids() -> set:
    """Tasks ja em estado terminal (nao re-disparar)."""
    term = {"COMMITTED", "VISUAL_REVIEW_QUEUED", "NOOP", "VERIFY_FAILED"} | LOCAL_LLM_TERMINAL
    return {r.get("task_id") for r in _ledger_rows() if r.get("status") in term}


def pick_task(queue, done, task_id=None):
    for t in queue:
        if task_id and t.get("id") != task_id:
            continue
        if t.get("id") in done and not task_id:
            continue
        if t.get("safe") is False:
            continue
        return t
    return None


def _worker_prompt(task, wt: Path) -> str:
    return (
        f"Voce e um WORKER autonomo do NOC. Trabalhe SOMENTE dentro deste worktree:\n"
        f"  {wt}\n\n"
        f"REGRAS DURAS:\n"
        f"- NAO toque em outros worktrees, NAO toque em main, NAO faca git push/merge/commit.\n"
        f"  So EDITE arquivos dentro deste worktree. O dispatcher cuida de verify/commit/PR.\n"
        f"- Siga o CLAUDE.md / Hard Rules deste repo.\n"
        f"- Se a task exigir mudar a APARENCIA de uma planta/.skp, PARE e crie\n"
        f"  NEEDS_VISUAL_REVIEW.md explicando o que mostrar; NAO autoavalie fidelidade.\n\n"
        f"TASK [{task.get('id')}]: {task.get('title','')}\n"
        f"{task.get('prompt','')}\n\n"
        f"Ao terminar, pare."
    )


def _run_worker(task, wt: Path):
    """Lanca claude -p escopado ao worktree. Prompt via STDIN (no Windows claude e .CMD
    e precisa de shell — mesmo padrao do gate). acceptEdits: deixa o worker editar
    arquivos sozinho, mas a isolacao do worktree + verify + no-merge sao as travas."""
    prompt = _worker_prompt(task, wt)
    bin_ = _claude_bin()
    base = ["-p", "--model", MODEL, "--permission-mode", "acceptEdits"]
    try:
        env = _worker_env()
        if sys.platform == "win32":
            cmd = '"' + bin_ + '" ' + " ".join(base)
            p = subprocess.run(cmd, input=prompt, cwd=str(wt), capture_output=True,
                               text=True, shell=True, timeout=CLAUDE_TIMEOUT, env=env)
        else:
            p = subprocess.run([bin_, *base], input=prompt, cwd=str(wt),
                               capture_output=True, text=True, timeout=CLAUDE_TIMEOUT, env=env)
    except subprocess.SubprocessError as e:
        return 1, "", f"{type(e).__name__}: {e}"
    return p.returncode, _redact((p.stdout or "")[-800:]), _redact((p.stderr or "")[-400:])


def _appearance_changed(wt: Path) -> bool:
    """Mudou .skp / render / builder / consensus? -> aparencia -> gate humano."""
    rc, out, _ = _git(["status", "--porcelain"], cwd=wt)
    touched = [ln[3:] for ln in out.splitlines() if ln.strip()]
    pat = (".skp", ".png", "build_plan_shell", "consensus", "renderer", "/renders/")
    return any(any(p in f for p in pat) for f in touched)


def _branch_exists(branch: str) -> bool:
    rc, _, _ = _git(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"])
    return rc == 0


def _branch_has_work(branch: str) -> bool:
    """Branch tem commit unico alem de origin/develop? -> NAO apagar (protege trabalho)."""
    rc, out, _ = _git(["rev-list", "--count", f"origin/develop..{branch}"])
    try:
        return int(out.strip()) > 0
    except ValueError:
        return False


def dispatch(task, dry_run=False) -> dict:
    tid = task.get("id", "T?")
    branch = f"chore/noc-{tid.lower()}"
    wt = WT_PARENT / f"wt-noc-{tid.lower()}"
    now = time.time()
    entry = {"t": now, "task_id": tid, "title": task.get("title", ""),
             "branch": branch, "worktree": str(wt), "dry_run": dry_run}

    wt_created = False
    try:
        # guarda de colisao: worktree path livre + branch sem trabalho a perder
        if wt.exists():
            entry["status"] = "SKIPPED_WT_EXISTS"
            return entry
        if _branch_exists(branch):
            if _branch_has_work(branch):
                entry["status"] = "SKIPPED_BRANCH_HAS_WORK"
                return entry
            _git(["branch", "-D", branch])  # leftover vazio (ex.: dry-run) -> recria limpo

        _git(["fetch", "origin"], timeout=60)
        rc, _, err = _git(["worktree", "add", str(wt), "-b", branch, "origin/develop"])
        if rc != 0:
            entry["status"], entry["error"] = "WT_ADD_FAILED", err[-300:]
            return entry
        wt_created = True

        worker = {"rc": None, "note": "dry-run: worker NAO lancado"}
        if not dry_run:
            rc, out, err = _run_worker(task, wt)
            worker = {"rc": rc, "out_tail": out, "err_tail": err}
        entry["worker"] = worker

        # verify deterministico (no proprio worktree) — so apos worker real
        if not dry_run:
            vinfo, ok = {}, True
            vf = task.get("verify_file")
            if vf:
                files = [vf] if isinstance(vf, str) else list(vf)
                missing = [f for f in files
                           if not (wt / f).is_file() or (wt / f).stat().st_size == 0]
                vinfo["verify_file"] = {"checked": files, "missing": missing}
                ok = ok and not missing
            vsh = task.get("verify")
            if vsh:
                sh = _bash()
                if sh:
                    vrc, vout, verr = _run([sh, "-lc", vsh], cwd=wt, timeout=600)
                    vinfo["verify"] = {"cmd": vsh, "rc": vrc, "tail": (vout + verr)[-300:]}
                    ok = ok and vrc == 0
                else:
                    vinfo["verify"] = {"cmd": vsh, "skipped": "git-bash nao encontrado"}
            if vinfo:
                entry["verify"] = vinfo
            if not ok:
                entry["status"] = "VERIFY_FAILED"
                return entry

        # ha mudancas?
        _, st, _ = _git(["status", "--porcelain"], cwd=wt)
        if not st.strip():
            entry["status"] = "DRY_RUN" if dry_run else "NOOP"
            return entry

        # mudou aparencia -> NAO auto-aprova: enfileira visual review
        if _appearance_changed(wt):
            _git(["add", "-A"], cwd=wt)
            _git(["commit", "-m", f"wip(noc-{tid}): {task.get('title','')} [needs VISUAL_REVIEW]"], cwd=wt)
            _git(["push", "-u", "origin", branch], cwd=wt, timeout=120)
            entry["status"] = "VISUAL_REVIEW_QUEUED"
            return entry

        # mudanca determinista (sem aparencia): comita + push a branch (NUNCA main/merge)
        _git(["add", "-A"], cwd=wt)
        _git(["commit", "-m",
              f"chore(noc-{tid}): {task.get('title','')}\n\nAutonomo via NOC dispatcher. Verify: {task.get('verify','-')}"],
             cwd=wt)
        prc, _, perr = _git(["push", "-u", "origin", branch], cwd=wt, timeout=120)
        entry["status"] = "COMMITTED" if prc == 0 else "PUSH_FAILED"
        if prc != 0:
            entry["error"] = perr[-300:]
        return entry
    finally:
        if wt_created:
            _git(["worktree", "remove", "--force", str(wt)])
            if dry_run:
                _git(["branch", "-D", branch])  # dry-run e' efemero: nao deixa branch
        ledger_append(entry)


def dispatch_local_llm(task, dry_run=False) -> dict:
    """kind:local_llm — roda um modelo LOCAL (Ollama) p/ um purpose ALLOWLISTADO e
    devolve so o resultado compacto (texto -> runs/local_llm/<id>.md + ledger). Token = 0.
    NUNCA toca git, NUNCA spawna claude, NUNCA da veredito visual. Offline ->
    on_offline:'error' (default, status LOCAL_LLM_OFFLINE) ou 'claude' (fallback explicito).
    Sem git = independente do caminho pesado do dispatch() -> testavel hermeticamente."""
    from tools.claude_bridge import ollama_client  # lazy (mesmo padrao do noc_lock)

    tid = task.get("id", "T?")
    purpose = task.get("purpose", "")
    entry = {"t": time.time(), "task_id": tid, "title": task.get("title", ""),
             "kind": "local_llm", "purpose": purpose, "backend": "ollama"}
    try:
        if purpose not in LOCAL_LLM_OK:
            entry["status"] = "SKIPPED_PURPOSE_NOT_ALLOWED"
            entry["error"] = f"purpose {purpose!r} fora da allowlist {sorted(LOCAL_LLM_OK)}"
            return entry
        prompt = (task.get("prompt") or "").strip()
        if not prompt:
            entry["status"], entry["error"] = "NOOP", "prompt vazio"
            return entry
        model = task.get("model") or DEFAULT_MODEL_BY_PURPOSE.get(purpose, "llama3.1:8b")
        entry["model"] = model
        if dry_run:
            entry["status"] = "DRY_RUN"
            return entry
        try:
            res = ollama_client.generate(prompt, model=model, purpose=purpose,
                                         options=task.get("options"))
        except ollama_client.OllamaUnavailable as e:
            if (task.get("on_offline") or "error") == "claude":
                entry["status"], entry["error"] = "LOCAL_LLM_FALLBACK_CLAUDE", _redact(str(e))
            else:
                entry["status"], entry["error"] = "LOCAL_LLM_OFFLINE", _redact(str(e))
            return entry
        entry["latency_ms"] = res.get("latency_ms")
        entry["eval_count"] = res.get("eval_count")
        LOCAL_LLM_DIR.mkdir(parents=True, exist_ok=True)
        out = LOCAL_LLM_DIR / f"{tid}.md"
        out.write_text(
            f"# {task.get('title', tid)}\n\n"
            f"- purpose: `{purpose}`\n- model: `{model}`\n"
            f"- latency: {res.get('latency_ms')}ms (load {res.get('load_ms')}ms)\n"
            f"- backend: ollama (token=0)\n\n---\n\n{res.get('response', '')}\n",
            encoding="utf-8")
        try:
            out_rel = str(out.relative_to(REPO_ROOT))
        except ValueError:  # LOCAL_LLM_DIR fora do repo (ex.: tmp em teste)
            out_rel = str(out)
        entry["out_file"] = out_rel.replace("\\", "/")
        entry["status"] = "LOCAL_LLM_DONE"
        return entry
    finally:
        ledger_append(entry)


def dispatch_by_kind(task, dry_run=False) -> dict:
    """Roteia a task pelo `kind` (default 'claude' = comportamento existente):
      - local_llm -> Ollama local (token=0); se LOCAL_LLM_FALLBACK_CLAUDE, cai pro claude.
      - tool      -> reservado pro muscle.py INLINE (brain_muscle.md), nao o dispatcher.
      - claude    -> caminho existente: worktree isolado + `claude -p` (INALTERADO)."""
    kind = (task.get("kind") or "claude").lower()
    if kind == "local_llm":
        result = dispatch_local_llm(task, dry_run=dry_run)
        if result.get("status") == "LOCAL_LLM_FALLBACK_CLAUDE":
            return dispatch(task, dry_run=dry_run)
        return result
    if kind == "tool":
        entry = {"t": time.time(), "task_id": task.get("id", "T?"),
                 "title": task.get("title", ""), "kind": "tool",
                 "status": "SKIPPED_KIND_TOOL",
                 "note": "deterministico inline = tools/muscle.py (brain_muscle.md), nao o dispatcher"}
        ledger_append(entry)
        return entry
    return dispatch(task, dry_run=dry_run)


def main():
    ap = argparse.ArgumentParser(description="NOC dispatcher — poe Claude pra trabalhar (1 atuador por vez)")
    ap.add_argument("--once", action="store_true", help="roda 1 ciclo e sai")
    ap.add_argument("--loop", action="store_true", help="daemon: roda ciclos ate a fila esgotar (ou --max-cycles)")
    ap.add_argument("--interval", type=int, default=20, help="segundos entre ciclos no --loop")
    ap.add_argument("--max-cycles", type=int, default=50, help="teto de ciclos no --loop (anti-runaway)")
    ap.add_argument("--dry-run", action="store_true", help="NAO lanca Claude; prova o loop (lock/worktree/ledger)")
    ap.add_argument("--task-id", default=None, help="dispara uma task especifica da fila")
    ap.add_argument("--owner", default=f"dispatcher-{int(time.time())}")
    args = ap.parse_args()

    from tools.claude_bridge.noc_lock import Lock
    lock = Lock(LOCK_PATH, owner=args.owner)
    if not lock.acquire():
        h = lock.held_by_other() or {}
        print(json.dumps({"status": "LOCKED", "held_by": h.get("owner"), "since": h.get("ts")}))
        return
    try:
        if args.loop:
            n = 0
            attempted = set()  # nao re-pegar a mesma task no mesmo run (status nao-terminal)
            while n < args.max_cycles:
                n += 1
                lock.heartbeat()  # mantem a posse durante o loop
                task = pick_task(load_queue(), _terminal_ids() | attempted)
                if not task:
                    print(json.dumps({"status": "NO_TASK", "cycle": n, "note": "fila esgotada -> parando"}))
                    break
                attempted.add(task.get("id"))
                result = dispatch_by_kind(task, dry_run=args.dry_run)
                print(json.dumps({"cycle": n, "task_id": result.get("task_id"),
                                  "status": result.get("status")}, ensure_ascii=False), flush=True)
                time.sleep(max(0, args.interval))
            else:
                print(json.dumps({"status": "MAX_CYCLES", "cycles": n}))
        else:
            task = pick_task(load_queue(), _terminal_ids(), task_id=args.task_id)
            if not task:
                print(json.dumps({"status": "NO_TASK", "queue_len": len(load_queue())}))
                return
            result = dispatch_by_kind(task, dry_run=args.dry_run)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        lock.release()


if __name__ == "__main__":
    main()
