"""FP-060 MT-06: coleta a evidencia do E2E real (PRs/Issues descartaveis) do GitHub e dos EventStores ISOLADOS que o executor usou.

Uso: collect_evidence.py <diretorio novo de saida> <fluxo>=<store.db> [...]      ex.: A_correcao=.../store.db C_continua=.../store.db
Fluxos conhecidos (PR/Issue): A_correcao 651/650, B_implementacao 655/653 (mesmo store), C_continua 659/658. Somente leitura (gh api com a
credencial do executor; SQLite aberto so para ler). Nada de token, caminho de maquina ou e-mail vai para o arquivo: so numeros, SHAs, estados,
logins publicos do repositorio e horarios."""
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = "GFCDOTA/sketchup-mcp"
FLOWS = {"A_correcao": (651, 650), "B_implementacao": (655, 653), "C_continua": (659, 658)}
GH = r"C:\Program Files\GitHub CLI\gh.exe"


def gh(path: str):
    out = subprocess.run([GH, "api", "--paginate", path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if out.returncode != 0:
        sys.exit(f"gh api {path} falhou: {out.stderr.strip()[:200]}")
    text = out.stdout.strip()
    if text.startswith("[") and "][" in text:
        text = "[" + text.replace("][", ",")[1:-1] + "]"
    return json.loads(text or "[]")


def scrub(text: str) -> str:
    return re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<caminho>", text or "")


out = Path(sys.argv[1])
stores = dict(arg.split("=", 1) for arg in sys.argv[2:])
out.mkdir(parents=True)
report: dict = {"repo": REPO, "fluxos": {}, "stores": {}}

for name, (number, issue) in FLOWS.items():
    pr = gh(f"repos/{REPO}/pulls/{number}")
    head = pr["head"]["sha"]
    report["fluxos"][name] = {
        "pr": number, "issue": issue, "estado": pr["state"], "merged": pr["merged"], "autor": pr["user"]["login"],
        "criado_em": pr["created_at"], "labels": sorted(x["name"] for x in pr["labels"]), "head_final": head, "base": pr["base"]["ref"],
        "arquivos": sorted(f["filename"] for f in gh(f"repos/{REPO}/pulls/{number}/files")),
        "commits": [{"sha": c["sha"], "autor": c["commit"]["author"]["name"], "mensagem": c["commit"]["message"].splitlines()[0]}
                    for c in gh(f"repos/{REPO}/pulls/{number}/commits")],
        "reviews": [{"id": r["id"], "revisor": r["user"]["login"], "estado": r["state"], "commit": r["commit_id"], "em": r["submitted_at"],
                     "marcador_outbox": (re.search(r"fp060-outbox-key:(\S+)", r["body"] or "") or [None, None])[1]}
                    for r in gh(f"repos/{REPO}/pulls/{number}/reviews")],
        "checks_no_head_final": {c["name"]: c["conclusion"] or c["status"] for c in gh(f"repos/{REPO}/commits/{head}/check-runs")["check_runs"]},
        "issue_estado": gh(f"repos/{REPO}/issues/{issue}")["state"],
    }

for label, db_path in stores.items():
    with sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        report["stores"][label] = {
            "eventos": [{k: ev[k] for k in ev.keys()} | {"error": scrub(ev["error"] or "")[:200] or None} for ev in db.execute(
                "SELECT id,event_type,idempotency_key,job_id,status,attempt,max_attempts,producer,created_at,updated_at,error FROM events ORDER BY id")],
            "transicoes": [{k: tr[k] for k in tr.keys()} | {"detail": scrub(tr["detail"] or "")[:200]} for tr in db.execute(
                "SELECT event_id,at,from_status,to_status,actor,detail FROM transitions ORDER BY id")],
        }

(out / "evidence.json").write_text(json.dumps(report, indent=1, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({k: {"pr": v["pr"], "head_final": v["head_final"][:8], "reviews": [(r["estado"], r["commit"][:8]) for r in v["reviews"]],
                      "checks": sorted(set(v["checks_no_head_final"].values()))} for k, v in report["fluxos"].items()}, indent=1))
