"""Auditoria por arquivo ("handoff de cada arquivo") + revisao de imports. Somente leitura: classifica, nunca apaga.

Para cada arquivo versionado responde: de que modulo/comodo ele e, quem depende dele, se ainda e alcancado (import,
entrypoint `-m`, citacao em CI/docs/skills/Ruby), quando foi tocado pela ultima vez e qual o proximo passo. Para o codigo
Python, levanta o grafo de imports: ciclos de import de topo, imports quebrados (alvo `tools.*`/`core.*` que nao existe),
`import *` e imports nao usados (ruff F401, sem `--fix`).

    python -m tools.navigation.file_audit --out docs/reports/file_audit         # JSON + resumo + um handoff por comodo
    python -m tools.navigation.file_audit --summary                             # so as contagens no terminal

Classificacao (a primeira regra que casa vence; `reason` diz qual):
  HISTORICAL        retrato datado (docs/archive, artifacts/_archive, docs/handoffs, docs/reports) — nao editar
  EVIDENCE_OR_DATA  artifacts/, fixtures/, references/, assets/, projects/ — protegido por hash (FP-042 P6)
  AGENT_INSTRUCTION .claude/** e .ai_bridge/** — guardado por tests/test_claude_assets.py
  SPEC              docs/specs/** — fonte das regras
  TEST              tests/**
  PACKAGE_MARKER    __init__.py sem logica
  ACTIVE_IMPORTED   modulo importado por outro arquivo do repo
  ACTIVE_ENTRYPOINT modulo/script citado por caminho ou `-m` em CI, docs, skills, configs ou outro codigo
  RUBY_JOB          .rb citado por codigo Python
  LEGACY_FACADE     inventario FP-042 marca como API/fachada legada
  CLI_DOC_ONLY      script com __main__ citado so em documentacao: nenhum teste/CI o executa
  ORPHAN_CANDIDATE  ninguem importa nem cita — candidato a arquivar, SO com decisao humana (Hard Rule #4)
  DOC / CONFIG      demais documentos e configuracoes
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "file_audit.v1"
PY_ROOTS = ("tools", "core", "tests", "interior", "artifacts", "ops", "docs", "scripts")
HISTORICAL = ("docs/archive/", "artifacts/_archive/", "docs/handoffs/", "docs/reports/", ".ai_bridge/questions/",
              ".ai_bridge/responses/", ".ai_bridge/gpt_review/", ".ai_bridge/fidelity/")
EVIDENCE = ("artifacts/", "fixtures/", "references/", "assets/", "projects/")
INSTRUCTION = (".claude/", ".ai_bridge/")
TEXT_EXT = (".py", ".rb", ".md", ".json", ".yml", ".yaml", ".toml", ".ps1", ".cmd", ".bat", ".sh", ".txt", ".cfg", ".ini")
# onde uma citacao conta como "uso" (evidencia/arquivo historico citando nao mantem codigo vivo)
MENTION_SCOPE_EXCLUDE = ("artifacts/", "fixtures/", "docs/archive/", "references/", "assets/", "docs/specs/fp042_")
REMOVED_SYSTEMS = re.compile(r":8765|claude_bridge server|noc_dispatcher|GPT-via-Chrome", re.I)
ROOMS = ("balcony", "bathroom", "bedroom", "circulation", "closet", "home_office", "kitchen", "living", "service", "shared")


def git(*args: str, root: Path = ROOT) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, encoding="utf-8", errors="replace")


def tracked(root: Path = ROOT) -> list[str]:
    return sorted(git("ls-files", root=root).splitlines())


def last_touch(root: Path = ROOT) -> dict[str, str]:
    """Data (AAAA-MM-DD) do ultimo commit que tocou cada arquivo, numa passada so do git log."""
    out: dict[str, str] = {}
    date = None
    for line in git("log", "--format=%x00%cs", "--name-only", root=root).splitlines():
        if line.startswith("\x00"):
            date = line[1:]
        elif line and line not in out:
            out[line] = date
    return out


def module_name(path: str) -> str | None:
    if not path.endswith(".py"):
        return None
    parts = path[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts and all(p.isidentifier() for p in parts) else None


def room_of(path: str) -> str:
    m = re.match(r"tools/rooms/([a-z_]+)/", path)
    if m and m.group(1) in ROOMS:
        return m.group(1)
    if path.startswith("tools/rooms/"):
        return "rooms_core"
    for prefix, label in (("core/", "core"), ("tools/sketchup/", "sketchup_executor"), ("tools/validation/", "validation"),
                          ("tools/", "tooling"), ("tests/", "tests"), ("interior/", "interior"), (".claude/", "agent"),
                          ("docs/", "docs")):
        if path.startswith(prefix):
            return label
    return "repo"


class PyFile:
    def __init__(self, path: str, text: str, modules: dict[str, str]):
        self.path, self.module = path, module_name(path)
        self.imports: set[str] = set()          # modulos do repo importados (qualquer nivel)
        self.top_imports: set[str] = set()      # so imports de topo (contam para ciclo)
        self.broken: list[str] = []
        self.star: list[str] = []
        self.has_main = "__name__" in text and "__main__" in text
        self.logic = False
        try:
            tree = ast.parse(text)
        except SyntaxError:
            self.syntax_error = True
            return
        self.syntax_error = False
        package = self.module if path.endswith("__init__.py") else (self.module or "").rpartition(".")[0]
        top = set(id(n) for n in tree.body)
        for node in tree.body:
            if not isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)) or (
                    isinstance(node, ast.Expr) and not isinstance(getattr(node, "value", None), ast.Constant)):
                self.logic = True
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = package.split(".") if package else []
                    keep = len(parts) - (node.level - 1)
                    parent = ".".join(parts[:keep]) if keep > 0 else ""
                    base = f"{parent}.{base}".strip(".") if base else parent
                for a in node.names:
                    if a.name == "*":
                        self.star.append(base)
                    sub = f"{base}.{a.name}"
                    targets.append(sub if sub in modules else base)
            for t in targets:
                # alvo do proprio repo precisa existir inteiro (cair para o prefixo `tools` esconderia o import quebrado)
                resolved = (t if t in modules else None) if t.split(".")[0] in ("tools", "core") else _resolve_module(t, modules)
                if resolved:
                    self.imports.add(resolved)
                    if id(node) in top:
                        self.top_imports.add(resolved)
                elif t.split(".")[0] in ("tools", "core") and not _optional_import(tree, node):
                    self.broken.append(t)


def _resolve_module(dotted: str, modules: dict[str, str]) -> str | None:
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        cand = ".".join(parts[:cut])
        if cand in modules:
            return cand
    return None


def _optional_import(tree: ast.AST, node: ast.AST) -> bool:
    """Import dentro de try/except ImportError e opcional por desenho (nao e quebrado)."""
    for t in ast.walk(tree):
        if isinstance(t, ast.Try) and any(node is n for b in t.body for n in ast.walk(b)):
            return True
    return False


def scc_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Ciclos de import (componentes fortemente conexos de tamanho > 1, ou auto-import). Tarjan iterativo: O(V + E)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on, stack, out = set(), [], []
    counter = 0
    for start in sorted(graph):
        if start in index:
            continue
        work = [(start, iter(sorted(graph.get(start, ()))))]
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on.add(start)
        while work:
            node, it = work[-1]
            nxt = next(it, None)
            if nxt is None:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    comp = []
                    while True:
                        w = stack.pop()
                        on.discard(w)
                        comp.append(w)
                        if w == node:
                            break
                    if len(comp) > 1 or node in graph.get(node, ()):
                        out.append(sorted(comp))
            elif nxt not in index:
                index[nxt] = low[nxt] = counter
                counter += 1
                stack.append(nxt)
                on.add(nxt)
                work.append((nxt, iter(sorted(graph.get(nxt, ())))))
            elif nxt in on:
                low[node] = min(low[node], index[nxt])
    return sorted(out)


def unused_imports(paths: list[str], root: Path = ROOT) -> list[dict] | None:
    """ruff F401 (sem --fix). `None` se o ruff nao rodou — a auditoria marca `ruff_checked: false` em vez de lista vazia falsa."""
    if not paths:
        return []
    try:
        proc = subprocess.run([sys.executable, "-m", "ruff", "check", "--select", "F401", "--output-format", "json",
                               "--no-cache", *paths], cwd=root, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError:
        return None
    if proc.returncode not in (0, 1):                  # 0 = limpo, 1 = achados; outro = ruff ausente/quebrado
        return None
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    out = []
    for r in rows:
        rel = Path(r["filename"]).resolve().relative_to(root.resolve()).as_posix()
        out.append({"path": rel, "line": r["location"]["row"], "message": r["message"]})
    return sorted(out, key=lambda r: (r["path"], r["line"]))


def audit(root: Path = ROOT, *, with_ruff: bool = True) -> dict:
    files = tracked(root)
    touched = last_touch(root)
    inv_path = root / "docs/specs/fp042_inventory.v1.json"
    inventory = {e["path"]: e for e in json.loads(inv_path.read_text(encoding="utf-8"))["entries"]} if inv_path.is_file() else {}
    py_paths = [p for p in files if p.endswith(".py")]
    modules = {m: p for p in py_paths if (m := module_name(p))}
    texts: dict[str, str] = {}
    for p in files:
        if p.endswith(TEXT_EXT):
            try:
                texts[p] = (root / p).read_text(encoding="utf-8", errors="replace")
            except OSError:
                texts[p] = ""
    pyfiles = {p: PyFile(p, texts.get(p, ""), modules) for p in py_paths}
    _TEXTS.clear()
    _TEXTS.update(texts)

    importers: dict[str, set[str]] = defaultdict(set)
    for p, f in pyfiles.items():
        for m in f.imports:
            if modules[m] != p:
                importers[modules[m]].add(p)

    # citacoes por caminho ou nome pontilhado, num indice unico (O(texto total), nao O(arquivos x modulos))
    mentioned_by: dict[str, set[str]] = defaultdict(set)
    token = re.compile(r"[A-Za-z0-9_./\\-]+")
    by_path = set(files)
    by_base = defaultdict(list)
    for p in files:
        by_base[p.rsplit("/", 1)[-1]].append(p)
    for src, text in texts.items():
        if src.startswith(MENTION_SCOPE_EXCLUDE):
            continue
        for tok in set(token.findall(text)):
            tok = tok.replace("\\", "/").removeprefix("./").rstrip(".")      # nunca strip("./"): comeria o "." de ".claude/"
            if tok in by_path and tok != src:
                mentioned_by[tok].add(src)
            elif tok in modules and modules[tok] != src:
                mentioned_by[modules[tok]].add(src)
            elif tok.endswith(".rb") and tok.rsplit("/", 1)[-1] in by_base and src.endswith(".py"):
                for cand in by_base[tok.rsplit("/", 1)[-1]]:
                    mentioned_by[cand].add(src)

    records = []
    for p in files:
        rec = {"path": p, "room": room_of(p), "last_touch": touched.get(p)}
        inv = inventory.get(p, {})
        owner = next((inv[k] for k in ("tool_owner", "document_owner", "owner", "domain") if k in inv), None)
        if owner:
            rec["owner"] = owner
        f = pyfiles.get(p)
        users = sorted(importers.get(p, set()))
        cites = sorted(mentioned_by.get(p, set()) - set(users))
        if f is not None:
            rec["imported_by"] = len(users)
            rec["tests_importing"] = len([u for u in users if u.startswith("tests/")])
            if f.broken:
                rec["broken_imports"] = sorted(set(f.broken))
            if f.star:
                rec["star_imports"] = sorted(set(f.star))
        if cites:
            rec["cited_by"] = len(cites)
        status, reason, action = classify(p, rec, f, inv, texts.get(p, ""), users, cites)
        rec.update(status=status, reason=reason, next_action=action)
        records.append(rec)

    graph = {m: {i for i in f.top_imports if i != m and in_cycle_scope(i)} for p, f in pyfiles.items()
             if (m := f.module) and in_cycle_scope(m)}
    cycles = scc_cycles(graph)
    live = [p for p in py_paths if not p.startswith(HISTORICAL + EVIDENCE)]
    unused = unused_imports(live, root) if with_ruff else None
    by_status = Counter(r["status"] for r in records)
    rooms = defaultdict(Counter)
    for r in records:
        rooms[r["room"]][r["status"]] += 1
    return {"schema_version": SCHEMA, "commit": git("rev-parse", "--short", "HEAD", root=root).strip(),
            "files": len(records), "by_status": dict(sorted(by_status.items())),
            "by_room": {k: dict(sorted(v.items())) for k, v in sorted(rooms.items())},
            "imports": {"cycles": cycles,
                        "broken": sorted({(r["path"], b) for r in records for b in r.get("broken_imports", [])
                                          if not r["path"].startswith(HISTORICAL + EVIDENCE)}),
                        "star": sorted({(r["path"], s) for r in records for s in r.get("star_imports", [])}),
                        "unused": unused or [], "ruff_checked": unused is not None},
            "records": records}


_TEXTS: dict[str, str] = {}


def citation_kind(path: str) -> str:
    """Peso de uma citacao: codigo e CI/config mantem um arquivo vivo; documentacao sozinha nao."""
    if path.endswith((".py", ".rb")):
        return "code"
    if path.startswith((".github/", ".claude/")) or path.endswith((".toml", ".yml", ".yaml", ".ps1", ".cmd", ".bat", ".sh", ".cfg", ".ini")):
        return "config"
    if path.endswith(".json") and not path.startswith("docs/"):
        return "config"
    return "doc"


def rec_module(path: str) -> str:
    return module_name(path) or path


def cites_text(cites: list[str]):
    return (_TEXTS.get(c, "") for c in cites)


def in_cycle_scope(module: str) -> bool:
    return module.split(".")[0] in ("tools", "core", "interior")


def classify(p, rec, f, inv, text, users, cites) -> tuple[str, str, str]:
    if p.startswith(HISTORICAL):
        return "HISTORICAL", "retrato datado", "nao editar; nova evidencia vai num arquivo novo"
    if p.startswith(EVIDENCE):
        return "EVIDENCE_OR_DATA", "dado/evidencia com hash FP-042", "ler e copiar; nunca escrever no canonico"
    if p.startswith(INSTRUCTION):
        stale = bool(REMOVED_SYSTEMS.search(text)) and not re.search(r"removid|antigo|legad|hist[oó]ric", text, re.I)
        return ("AGENT_INSTRUCTION", "instrucao do agente" + (" com sistema removido" if stale else ""),
                "revisar a instrucao" if stale else "manter (tests/test_claude_assets.py)")
    if p.startswith("docs/specs/"):
        return "SPEC", "spec SDD", "manter; mudar so com PR da frente dona"
    if p.startswith("tests/"):
        return "TEST", "suite de regressao", "manter verde"
    if f is not None:
        if f.syntax_error:
            return "BROKEN", "SyntaxError ao parsear", "corrigir ou arquivar"
        if p.endswith("__init__.py") and not f.logic:
            return "PACKAGE_MARKER", "pacote sem logica", "manter"
        if users:
            return "ACTIVE_IMPORTED", f"importado por {len(users)} arquivo(s)", "manter"
        strong = [c for c in cites if citation_kind(c) != "doc"]
        if strong:
            return "ACTIVE_ENTRYPOINT", f"citado por {len(strong)} arquivo(s) de codigo/CI/config/skill", "manter"
        if "legacy" in json.dumps(inv).lower() or "facade" in json.dumps(inv).lower():
            return "LEGACY_FACADE", "inventario marca fachada/API legada", "remover quando o consumidor sair"
        if cites and f.has_main:
            return ("CLI_DOC_ONLY", f"CLI manual citada so em documentacao ({len(cites)} doc); nenhum teste/CI a executa",
                    "dar teste de fumaca (vira ACTIVE) ou arquivar com decisao do Felipe")
        if cites:
            return ("ORPHAN_CANDIDATE", f"so citado em documentacao ({len(cites)} doc)",
                    "decidir com o Felipe: arquivar em docs/archive ou religar a um fluxo")
        return "ORPHAN_CANDIDATE", "ninguem importa nem cita", "decidir com o Felipe: arquivar em docs/archive ou remover"
    if p.endswith(".rb"):
        return (("RUBY_JOB", f"citado por {len(cites)} arquivo(s)", "manter") if cites else
                ("ORPHAN_CANDIDATE", "Ruby que nenhum codigo cita", "decidir com o Felipe"))
    if p.endswith((".md", ".txt")):
        if REMOVED_SYSTEMS.search(text) and not re.search(r"removid|antigo|legad|hist[oó]ric", text, re.I):
            return "DOC", "cita sistema removido (:8765/NOC/GPT-via-Chrome) como vigente", "atualizar ou mover para docs/archive"
        return "DOC", "documentacao", "manter"
    return "CONFIG", "configuracao/outro", "manter"


ROOM_TITLE = {"kitchen": "Cozinha", "living": "Sala", "bedroom": "Quarto", "bathroom": "Banheiro", "service": "Serviço",
              "balcony": "Varanda", "closet": "Closet", "home_office": "Home office", "circulation": "Circulação",
              "shared": "Compartilhado (shared)", "rooms_core": "Núcleo de cômodos (tools/rooms/*.py)"}


AREA_TITLE = {**ROOM_TITLE, "core": "core/ (domínio)", "sketchup_executor": "tools/sketchup/ (executor SketchUp)",
              "validation": "tools/validation/ (gates transversais)", "tooling": "tools/ (demais ferramentas)",
              "tests": "tests/", "interior": "interior/", "agent": ".claude/ (instruções do agente)", "docs": "docs/",
              "repo": "raiz, artifacts, fixtures, references, assets, ops, projects"}
# evidencia e historico sao muitos e homogeneos: resumidos por diretorio, nao linha a linha
AGGREGATE = ("EVIDENCE_OR_DATA", "HISTORICAL")


def _row(r: dict) -> str:
    return (f"| `{r['path']}` | {r['status']} | {r['reason']} | {r.get('imported_by', '')} | {r.get('cited_by', '')} | "
            f"{r.get('last_touch') or ''} | {r['next_action']} |")


def write(report: dict, out: Path) -> None:
    """JSON completo + um handoff markdown por area (comodo, shared, core, executor, ...). Escrita deterministica."""
    out.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in report.items() if k != "records"}
    slim["records"] = [r for r in report["records"] if r["status"] not in AGGREGATE]       # evidencia/historico: so contagem
    (out / "file_audit.v1.json").write_text(json.dumps(slim, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    areas_dir = out / "areas"
    areas_dir.mkdir(exist_ok=True)
    by_area = defaultdict(list)
    for r in report["records"]:
        by_area[r["room"]].append(r)
    for area, rows in sorted(by_area.items()):
        title = AREA_TITLE.get(area, area)
        lines = [f"# Handoff por arquivo — {title}", "",
                 f"> Gerado por `python -m tools.navigation.file_audit --out docs/reports/file_audit` em `{report['commit']}`.",
                 "> Retrato datado: regenere, não edite. Estados e regras no docstring de `tools/navigation/file_audit.py`.", "",
                 "Contagem: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r["status"] for r in rows).items())), ""]
        detail = [r for r in rows if r["status"] not in AGGREGATE]
        if detail:
            lines += ["| Arquivo | Estado | Por quê | Importado por | Citado por | Último toque | Próximo passo |",
                      "|---|---|---|---|---|---|---|"] + [_row(r) for r in sorted(detail, key=lambda r: r["path"])]
        bulk = defaultdict(list)
        for r in rows:
            if r["status"] in AGGREGATE:
                bulk[(r["status"], "/".join(r["path"].split("/")[:3]))].append(r)
        if bulk:
            lines += ["", "## Evidência e histórico (por diretório)", "", "| Diretório | Estado | Arquivos | Último toque | Regra |",
                      "|---|---|---|---|---|"]
            for (status, d), rs in sorted(bulk.items(), key=lambda kv: kv[0][1]):
                last = max((r.get("last_touch") or "" for r in rs), default="")
                lines.append(f"| `{d}/` | {status} | {len(rs)} | {last} | {rs[0]['next_action']} |")
        (areas_dir / f"{area}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--no-ruff", action="store_true")
    args = ap.parse_args(argv)
    report = audit(with_ruff=not args.no_ruff)
    if args.out:
        write(report, args.out)
    brief = {k: report[k] for k in ("commit", "files", "by_status")}
    brief["imports"] = {k: (len(v) if isinstance(v, list) else v) for k, v in report["imports"].items()}
    print(json.dumps(brief, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
