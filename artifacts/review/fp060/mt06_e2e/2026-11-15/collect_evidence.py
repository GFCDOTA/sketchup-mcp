"""FP-060 MT-06: coleta a evidencia do E2E real (PRs/Issues descartaveis) do GitHub e dos EventStores ISOLADOS que o executor usou.

Uso: collect_evidence.py <diretorio novo de saida> <fluxo>=<PR>:<Issue>:<store.db> [...]
     ex.: A_correcao=<PR>:<Issue>:<store A/B>  C_continua=<PR>:<Issue>:<store C>
Os numeros do PR e da Issue sao SEMPRE informados (nada fixo no codigo): uma nova execucao coleta o que ela mesma criou. Somente leitura: `gh api` com a
credencial do executor e o SQLite aberto em `mode=ro` por URI com o caminho codificado. A saida nao leva token, e-mail nem caminho de maquina: todo texto
livre passa por `clean`, e o arquivo SO e gravado se uma verificacao final nao achar nenhum padrao proibido."""
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = "GFCDOTA/sketchup-mcp"
GH = r"C:\Program Files\GitHub CLI\gh.exe"

TOKEN = re.compile(r"(gh[pousr]_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}|sk-ant-[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._~+/-]{10,}|AKIA[0-9A-Z]{12,})")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
WIN_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\"'<>|\r\n]*")                    # ate o fim da linha/aspas: cobre espacos no caminho
UNIX_PATH = re.compile(r"(?<![\w.:-])/(?:home|Users|users|root|var|tmp|mnt|opt|usr|etc|c|d|e)/[^\s\"'<>|]+")
FORBIDDEN = (TOKEN, EMAIL, WIN_PATH, UNIX_PATH)


def scrub(text: str) -> str:
    text = TOKEN.sub("<token>", text or "")
    text = EMAIL.sub("<email>", text)
    text = WIN_PATH.sub("<caminho>", text)
    return UNIX_PATH.sub("<caminho>", text)


def clean(value):
    """Aplica `scrub` a TODA string do relatorio (chaves e valores), recursivamente."""
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {scrub(str(k)): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def assert_clean(text: str) -> None:
    for pattern in FORBIDDEN:
        found = pattern.search(text)
        if found:
            raise SystemExit(f"evidencia RECUSADA: padrao proibido na saida ({pattern.pattern[:30]}...): {found.group(0)[:12]}...")


def sqlite_ro_uri(path: Path) -> str:
    """URI `mode=ro` com o caminho absoluto CODIFICADO (`#`, `?`, `%` e espacos no nome nao viram fragmento/consulta)."""
    return Path(path).resolve().as_uri() + "?mode=ro"


def parse_flow(arg: str) -> tuple[str, int, int, Path]:
    name, _, rest = arg.partition("=")
    parts = rest.split(":", 2)
    if not name or len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit() or not parts[2]:
        raise SystemExit(f"fluxo invalido {arg!r}: use NOME=<PR>:<Issue>:<store.db>")
    return name, int(parts[0]), int(parts[1]), Path(parts[2])


def gh(path: str):
    out = subprocess.run([GH, "api", "--paginate", path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if out.returncode != 0:
        raise SystemExit(f"gh api {path} falhou: {scrub(out.stderr.strip())[:200]}")
    text = out.stdout.strip()
    if text.startswith("[") and "][" in text:
        text = "[" + text.replace("][", ",")[1:-1] + "]"
    return json.loads(text or "[]")


def read_store(db_path: Path) -> dict:
    with sqlite3.connect(sqlite_ro_uri(db_path), uri=True) as db:
        db.row_factory = sqlite3.Row
        return {
            "eventos": [dict(r) for r in db.execute(
                "SELECT id,event_type,idempotency_key,job_id,status,attempt,max_attempts,producer,created_at,updated_at,error FROM events ORDER BY id")],
            "transicoes": [dict(r) for r in db.execute("SELECT event_id,at,from_status,to_status,actor,detail FROM transitions ORDER BY id")],
        }


def collect_flow(number: int, issue: int) -> dict:
    pr = gh(f"repos/{REPO}/pulls/{number}")
    head = pr["head"]["sha"]
    return {
        "pr": number, "issue": issue, "estado": pr["state"], "merged": pr["merged"], "autor": pr["user"]["login"], "criado_em": pr["created_at"],
        "labels": sorted(x["name"] for x in pr["labels"]), "head_final": head, "base": pr["base"]["ref"],
        "arquivos": sorted(f["filename"] for f in gh(f"repos/{REPO}/pulls/{number}/files")),
        "commits": [{"sha": c["sha"], "autor": c["commit"]["author"]["name"], "mensagem": c["commit"]["message"].splitlines()[0]}
                    for c in gh(f"repos/{REPO}/pulls/{number}/commits")],
        "reviews": [{"id": r["id"], "revisor": r["user"]["login"], "estado": r["state"], "commit": r["commit_id"], "em": r["submitted_at"],
                     "marcador_outbox": (re.search(r"fp060-outbox-key:(\S+)", r["body"] or "") or [None, None])[1]}
                    for r in gh(f"repos/{REPO}/pulls/{number}/reviews")],
        "checks_no_head_final": {c["name"]: c["conclusion"] or c["status"] for c in gh(f"repos/{REPO}/commits/{head}/check-runs")["check_runs"]},
        "issue_estado": gh(f"repos/{REPO}/issues/{issue}")["state"],
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit(__doc__)
    out = Path(argv[0])
    flows = [parse_flow(a) for a in argv[1:]]
    out.mkdir(parents=True)
    report: dict = {"repo": REPO, "fluxos": {}, "stores": {}}
    for name, number, issue, db_path in flows:
        report["fluxos"][name] = collect_flow(number, issue)
        report["stores"].setdefault(db_path.parent.parent.name or "store", read_store(db_path))      # um store compartilhado entre fluxos entra uma vez
    text = json.dumps(clean(report), indent=1, ensure_ascii=True, sort_keys=True) + "\n"
    assert_clean(text)
    (out / "evidence.json").write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({k: {"pr": v["pr"], "head_final": v["head_final"][:8], "reviews": [(r["estado"], r["commit"][:8]) for r in v["reviews"]]}
                      for k, v in report["fluxos"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
