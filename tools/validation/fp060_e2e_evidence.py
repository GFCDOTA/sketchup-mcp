"""FP-060 MT-06: coleta a evidencia do E2E real (PRs/Issues descartaveis) do GitHub e dos EventStores ISOLADOS que o executor usou.

Uso: python -m tools.validation.fp060_e2e_evidence <diretorio novo de saida> <fluxo>=<PR>:<Issue>:<store.db> [...]
     ex.: A_correcao=<PR>:<Issue>:<store A/B>  C_continua=<PR>:<Issue>:<store C>
Os numeros do PR e da Issue sao SEMPRE informados (nada fixo no codigo): uma nova execucao coleta o que ela mesma criou. Somente leitura: `gh api` com a
credencial do executor e o SQLite aberto em `mode=ro` por URI com o caminho codificado. A saida nao leva token, e-mail nem caminho de maquina: todo texto
livre passa por `clean`, e o arquivo SO e gravado se uma verificacao final nao achar nenhum padrao proibido."""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = "GFCDOTA/sketchup-mcp"
GH = r"C:\Program Files\GitHub CLI\gh.exe"

TOKEN = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{10,}|github_pat_[A-Za-z0-9_]{10,}"                              # GitHub
    r"|sk-[A-Za-z0-9][A-Za-z0-9_-]{15,}"                                                        # Anthropic (sk-ant-) e OpenAI (sk-, sk-proj-, sk-svcacct-)
    r"|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{20,}|AKIA[0-9A-Z]{12,}"                    # Slack, Google, AWS
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"                           # JWT
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)"          # chave privada PEM COMPLETA (cabecalho, corpo e rodape; sem rodape, ate o fim)
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/=-]{8,}|(?i:basic)\s+[A-Za-z0-9+/=]{8,}"                             # esquema em qualquer caixa (Bearer e Basic)
    r"|(?i:(?<![A-Za-z0-9])[A-Za-z0-9_-]*(?:api[_-]?key|secret|password|passwd|token|credential|private[_-]?key)[A-Za-z0-9_-]*)[\"']?\s*[:=]\s*"   # client_secret, refresh_token, x-api-key...
    r"(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[^\s;}\"']{4,}))")                 # inclui JSON ({"password": "..."}) e valores entre aspas inteiros (virgulas, espacos, escapes)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
WIN_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\"'<>|\r\n]*")
UNC_PATH = re.compile(r"(?:\\\\|(?<![:\w/.])//)[A-Za-z0-9_.$-]+[\\/][^\"'<>|\r\n]*")                   # \\servidor\compartilhamento\... (e //servidor/compartilhamento/...)                    # ate o fim da linha/aspas: cobre espacos no caminho
UNIX_PATH = re.compile(r"(?<![\w.:#/-])/(?:(?:[\w.@+~()\[\]&=!%-]|[:#](?=[\w.@+~()\[\]&=!%/-]))+(?: (?:[\w.@+~()\[\]&=!%-]|[:#](?=[\w.@+~()\[\]&=!%/-]))+)*/)+(?:[\w.@+~()\[\]&=!%-]|[:#](?=[\w.@+~()\[\]&=!%/-]))+(?: (?:[\w.@+~()\[\]&=!%-]|[:#](?=[\w.@+~()\[\]&=!%/-]))+)*|(?<![\w.:#/-])/(?:(?:[\w.@+~()\[\]&=!%-]|[:#](?=[\w.@+~()\[\]&=!%/-]))+(?: (?:[\w.@+~()\[\]&=!%-]|[:#](?=[\w.@+~()\[\]&=!%/-]))+)*/)+")      # caminho absoluto Unix (2+ segmentos) de QUALQUER raiz; componentes (e o ultimo) podem ter espacos e parenteses/colchetes/& = ! %; dois-pontos DENTRO do componente (valido em nome Unix); prefere redigir demais a vazar
UNIX_SPACED = re.compile(r"(?<![\w.:#/-])/(?:home|Users|users|root|mnt|srv|opt|var|tmp|Volumes|workspace|data|media)/[^\"'<>|\r\n]*")     # raiz de usuario/maquina: ate o fim da linha (cobre espacos)
FORBIDDEN = (TOKEN, EMAIL, WIN_PATH, UNC_PATH, UNIX_SPACED, UNIX_PATH)


def scrub(text: str) -> str:
    text = TOKEN.sub("<token>", text or "")
    text = EMAIL.sub("<email>", text)
    text = UNC_PATH.sub("<caminho>", text)
    text = WIN_PATH.sub("<caminho>", text)
    text = UNIX_SPACED.sub("<caminho>", text)
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
            # NENHUM caractere do valor achado vai para a mensagem (stderr/logs): so o tipo do padrao e a posicao
            raise SystemExit(f"evidencia RECUSADA: padrao proibido na saida (padrao #{FORBIDDEN.index(pattern)}, posicao {found.start()}); nada foi gravado")


def sqlite_ro_uri(path: Path) -> str:
    """URI `mode=ro` com o caminho absoluto CODIFICADO (`#`, `?`, `%` e espacos no nome nao viram fragmento/consulta)."""
    return Path(path).resolve().as_uri() + "?mode=ro"


def parse_flow(arg: str) -> tuple[str, int, int, Path]:
    name, _, rest = arg.partition("=")
    parts = rest.split(":", 2)
    if not name or len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit() or not parts[2]:
        raise SystemExit(f"fluxo invalido {arg!r}: use NOME=<PR>:<Issue>:<store.db>")
    return name, int(parts[0]), int(parts[1]), Path(parts[2])


def merge_pages(pages):
    """Combina as paginas de `gh api --paginate --slurp` ESTRUTURALMENTE (nunca por substituicao de texto: `][` pode estar dentro de um valor). Listas sao
    concatenadas; objetos (ex.: `check_runs`) tem cada lista concatenada entre as paginas; uma unica pagina volta como veio."""
    if not isinstance(pages, list):
        raise ValueError("resposta paginada nao e uma lista de paginas")
    if not pages:
        return []
    if all(isinstance(p, list) for p in pages):
        return [item for page in pages for item in page]
    if all(isinstance(p, dict) for p in pages):
        merged = dict(pages[0])
        for key, value in pages[0].items():
            if isinstance(value, list):
                merged[key] = [item for page in pages for item in page.get(key, [])]
        return merged
    raise ValueError("paginas de tipos misturados")


def gh(path: str):
    out = subprocess.run([GH, "api", "--paginate", "--slurp", path], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if out.returncode != 0:
        raise SystemExit(f"gh api {path} falhou: {scrub(out.stderr.strip())[:200]}")
    return merge_pages(json.loads(out.stdout.strip() or "[]"))


def store_id(db_path: Path) -> str:
    """Identidade do store pelo caminho CANONICO do banco (dois bancos com o mesmo nome de diretorio sao dois stores; o caminho real nao vai para a saida)."""
    canonical = os.path.normcase(str(Path(db_path).resolve()))
    return "store-" + hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:8]


def read_store(db_path: Path) -> dict:
    with sqlite3.connect(sqlite_ro_uri(db_path), uri=True) as db:
        db.row_factory = sqlite3.Row
        return {
            "eventos": [dict(r) for r in db.execute(
                "SELECT id,event_type,idempotency_key,job_id,status,attempt,max_attempts,producer,created_at,updated_at,error FROM events ORDER BY id")],
            "transicoes": [dict(r) for r in db.execute("SELECT event_id,at,from_status,to_status,actor,detail FROM transitions ORDER BY id")],
        }


def checks_of(runs: list[dict]) -> list[dict]:
    """TODO check run, cada um com id, nome, origem e conclusao: dois checks de mesmo nome (ex.: reexecucao) aparecem os dois, nunca um sobrescreve o outro."""
    return sorted(({"id": c.get("id"), "nome": c.get("name"), "origem": (c.get("app") or {}).get("slug"), "estado": c.get("conclusion") or c.get("status")} for c in runs),
                  key=lambda c: (str(c["nome"]), c["id"] or 0))


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
        "checks_no_head_final": checks_of(gh(f"repos/{REPO}/commits/{head}/check-runs?filter=all&per_page=100")["check_runs"]),
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
        flow = collect_flow(number, issue)
        sid = store_id(db_path)
        flow["store"] = sid                                                                          # cada fluxo fica associado ao SEU store
        report["fluxos"][name] = flow
        if sid not in report["stores"]:
            report["stores"][sid] = read_store(db_path)                                              # um banco compartilhado entre fluxos entra uma vez
    text = json.dumps(clean(report), indent=1, ensure_ascii=True, sort_keys=True) + "\n"
    assert_clean(text)
    (out / "evidence.json").write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({k: {"pr": v["pr"], "head_final": v["head_final"][:8], "reviews": [(r["estado"], r["commit"][:8]) for r in v["reviews"]]}
                      for k, v in report["fluxos"].items()}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
