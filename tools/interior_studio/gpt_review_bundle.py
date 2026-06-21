"""gpt_review_bundle.py — gera um PACOTE DE REVISÃO único pro Consult GPT (stdlib, offline).

Problema: o GPT não acessa localhost nem arquivo local não-commitado. Solução: empacotar o estado
atual do Interior Studio num `.ai_bridge/gpt_review/GPT_REVIEW_BUNDLE.{md,json}` com:
repo (branch/SHA) · links raw dos arquivos principais · estado do /api/state · ciclo atual ·
reference pack curado · consult bridge · mudanças desde a última revisão · pergunta objetiva.

Git info vem de LER `.git/*` direto (o container python:3.12-slim não tem git CLI). Status/diff são
best-effort via git CLI (se existir). NÃO toca :8765 nem geometria.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / ".ai_bridge" / "gpt_review"
MD_PATH = OUT_DIR / "GPT_REVIEW_BUNDLE.md"
JSON_PATH = OUT_DIR / "GPT_REVIEW_BUNDLE.json"
LAST_SHA = OUT_DIR / ".last_review_sha"

# arquivos principais cujo raw link entra no bundle (só se existirem no working tree)
KEY_FILES = [
    "tools/studio_dashboard.py",
    "tools/interior_studio/cycles.py",
    "tools/interior_studio/reference_packs.py",
    ".ai_bridge/interior_studio/HANDOFF.md",
    ".ai_bridge/ROOM_CYCLE_PLAN.md",
    ".claude/memory/felipe_style_dna.md",
    "artifacts/reference_lab/sofa/SOFA_REFERENCE_PACK.md",
    ".ai_bridge/reference_packs/sofa_reference_pack_001.json",
    ".ai_bridge/interior_cycles/CYCLE-003.json",
    ".ai_bridge/gpt_review/GPT_REVIEW_BUNDLE.md",
]


def _git_info() -> dict:
    """branch/sha/remote lidos de `.git/*` direto (sem depender de git CLI no container)."""
    g = ROOT / ".git"
    info = {"branch": None, "sha": None, "remote_url": None, "owner": None, "repo": None}
    try:
        head = (g / "HEAD").read_text("utf-8").strip()
        if head.startswith("ref:"):
            ref = head[4:].strip()
            info["branch"] = ref.split("refs/heads/", 1)[-1]
            refp = g / ref
            if refp.exists():
                info["sha"] = refp.read_text("utf-8").strip()
            elif (g / "packed-refs").exists():
                for ln in (g / "packed-refs").read_text("utf-8").splitlines():
                    if ln.strip().endswith(ref):
                        info["sha"] = ln.split()[0]
                        break
        else:
            info["sha"] = head
    except OSError:
        pass
    try:
        cfg = (g / "config").read_text("utf-8")
        m = re.search(r'\[remote "origin"\](.*?)(?=\n\[|\Z)', cfg, re.S)
        if m:
            um = re.search(r'url\s*=\s*(\S+)', m.group(1))
            if um:
                url = um.group(1).strip()
                info["remote_url"] = url
                gh = re.search(r'github\.com[:/]+([^/]+)/([^/.\s]+)', url)
                if gh:
                    info["owner"], info["repo"] = gh.group(1), gh.group(2)
    except OSError:
        pass
    return info


def _git_cli(args: list[str]) -> str:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=8)
        return (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _raw(owner, repo, branch, path) -> str:
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def _now_iso(now: str | None) -> str:
    return now or time.strftime("%Y-%m-%dT%H:%M:%S")


def short_question(state: dict) -> str:
    fac = state.get("factory") or {}
    cid = fac.get("cycle_id", "CYCLE-?")
    return (f"Revise o estado atual do Interior Studio (:8782) pelos arquivos raw linkados. "
            f"(1) O dashboard está CLARO pra operar o ciclo {cid} / SOFA_REFERENCE_PACK? "
            f"(2) O que ainda compete por atenção / está confuso? "
            f"(3) O que priorizar ANTES de construir o sofá? "
            f"(4) A curadoria VISUAL e a regra-trava (Arquiteto bloqueado sem ⭐ principal) estão bem resolvidas? "
            f"Responda objetivo, com prioridades.")


def build(state: dict, *, now: str | None = None) -> dict:
    """Monta o bundle (md+json) a partir do state do dashboard. Idempotente; sobrescreve os 2 arquivos."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gi = _git_info()
    owner, repo, branch, sha = gi["owner"], gi["repo"], gi["branch"], gi["sha"]
    ts = _now_iso(now)
    can_link = bool(owner and repo and branch)

    links = []
    for f in KEY_FILES:
        if (ROOT / f).exists() and can_link:
            links.append({"path": f, "raw": _raw(owner, repo, branch, f)})
    tree_url = f"https://github.com/{owner}/{repo}/tree/{branch}" if can_link else None

    fac = state.get("factory") or {}
    rp = state.get("refpack") or {}
    co = state.get("consult") or {}
    ll = state.get("learning") or {}
    bk = state.get("backlog") or {}

    # mudanças desde a última revisão (best-effort; git CLI pode não existir no container)
    last = LAST_SHA.read_text("utf-8").strip() if LAST_SHA.exists() else ""
    changed = _git_cli(["diff", "--stat", f"{last}..HEAD"]) if (last and sha) else ""
    if sha:
        LAST_SHA.write_text(sha, "utf-8")

    # ---- markdown ----
    L = []
    L.append("# GPT REVIEW BUNDLE — Interior Studio (:8782)")
    L.append(f"> Gerado {ts} · fonte única pro Consult GPT revisar o dashboard sem localhost.\n")
    L.append("## 1. Repo")
    L.append(f"- branch: `{branch}`\n- commit: `{sha}`\n- remote: `{gi['remote_url']}`\n- gerado_em: {ts}")
    if tree_url:
        L.append(f"- tree: {tree_url}")
    if changed:
        L.append(f"\n<details><summary>git diff --stat desde a última revisão</summary>\n\n```\n{changed}\n```\n</details>")
    L.append("\n## 2. Links raw (arquivos principais)")
    L += [f"- [`{x['path']}`]({x['raw']})" for x in links] or ["- (sem remote git resolvido — rode com origin GitHub)"]
    L.append("\n## 3. Estado atual (resumo do /api/state)")
    L.append(f"- projeto: **{fac.get('project','?')}** · cômodo: **{fac.get('room','?')}** · asset: **{fac.get('asset','?')}**")
    L.append(f"- ciclo: **{fac.get('cycle_id','?')}** · microtarefa: **{fac.get('microtask','?')}** · modo: **{fac.get('mode','?')}**")
    L.append(f"- status: **{fac.get('status','?')}** · próxima ação: **{fac.get('next_action','?')}**")
    L.append(f"- arquiteto_bloqueado: **{fac.get('architect_blocked')}**")
    L.append(f"- reference pack: {rp.get('counts')}")
    L.append(f"- backlog: {bk.get('total','?')} microtarefas, {bk.get('done','?')} done")
    L.append(f"- learning: {len(ll.get('new_rules',[]))} regra(s), {len(ll.get('anti_patterns',[]))} anti-pattern(s), {len(ll.get('golden_samples',[]))} golden")
    L.append("\n## 4. Ciclo atual — timeline")
    for st in fac.get("timeline", []):
        line = f"- {st.get('face','')} **{st.get('agent')}** — `{st.get('status')}`"
        if st.get("model"):
            line += f" _(via {st['model']})_"
        if st.get("summary"):
            line += f": {st['summary']}"
        L.append(line)
        for fp in st.get("files", []):
            L.append(f"    - arquivo: `{fp}`")
    L.append("\n## 5. Reference Pack — curadoria do Felipe")
    if rp.get("ok"):
        L.append(f"_{rp.get('honesty','')}_\n")
        for r in rp.get("references", []):
            tag = {"main": "⭐ PRINCIPAL", "approved": "👍 aprovada", "rejected": "👎 rejeitada",
                   "anti": "🚫 anti-pattern", "pending": "• pendente"}.get(r.get("status"), r.get("status"))
            L.append(f"- **{r.get('title')}** [{tag}] ({r.get('type')}) — {r.get('link')}")
            if r.get("comment"):
                L.append(f"    - comentário Felipe: {r['comment']}")
    else:
        L.append("- (sem reference pack ativo)")
    L.append("\n## 6. Consult GPT Bridge")
    lq = co.get("latest_question") or {}
    L.append(f"- modo: {co.get('bridge_mode','manual')} · OpenAI: {'on' if co.get('openai_enabled') else 'off'}")
    L.append(f"- última pergunta: {lq.get('question_id','—')} · pendentes: {len(co.get('pending_questions',[]))} · ingeridas: {co.get('ingested_count',0)}")
    L.append("\n## 7. Mudanças desde a última revisão")
    L.append(f"- último SHA revisado: `{last or '(primeira revisão)'}`")
    L.append(f"- SHA atual: `{sha}`")
    if changed:
        L.append(f"```\n{changed}\n```")
    else:
        L.append("- (sem diff disponível — git CLI ausente no container ou primeira revisão)")
    L.append("\n## Pergunta para o GPT")
    L.append(short_question(state))
    md = "\n".join(L) + "\n"

    bundle = {
        "generated_at": ts, "repo": gi, "tree_url": tree_url, "links": links,
        "factory": fac, "refpack": rp, "consult": co, "learning": ll,
        "backlog": {"total": bk.get("total"), "done": bk.get("done")},
        "changes_since_last": {"last_sha": last, "current_sha": sha, "diffstat": changed},
        "question": short_question(state),
    }
    MD_PATH.write_text(md, "utf-8")
    JSON_PATH.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), "utf-8")

    raw_link = _raw(owner, repo, branch, ".ai_bridge/gpt_review/GPT_REVIEW_BUNDLE.md") if can_link else None
    return {"ok": True, "md": md, "md_path": str(MD_PATH.relative_to(ROOT)),
            "json_path": str(JSON_PATH.relative_to(ROOT)), "raw_link": raw_link,
            "question": short_question(state), "branch": branch, "sha": sha, "links": links}
