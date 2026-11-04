"""execution_guards.py — protecoes puras e fail-closed do executor local (FP-057/P8, Issue #589). SEM rede, SEM subprocesso, SEM LLM.

Tres perguntas, todas respondidas por funcao pura (a ligacao no executor vem em PRs seguintes):
  - `label_ok`        o PR tem a label de execucao (`executor-ok`)?
  - `is_critical`     o caminho e critico (workflows, politica de revisao, gates, governanca/execucao)? Une `critical_paths` da
                      `review_policy.json` com `extra_critical_paths` de `executor_guards.json`.
  - `evaluate_diff`   o diff (saida de `git diff --numstat --no-renames`) respeita paths criticos e o teto de arquivos/linhas?

Fail-closed: entrada ilegivel, caminho com `..`, numero invalido ou binario => violacao (nunca "assume que esta ok"). A comparacao de
caminhos normaliza barras e ignora caixa (NTFS). Os tetos iniciais sao PROPOSTAS (decisao do Tech Lead na SPEC FP-057/P8).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUARDS_PATH = ROOT / "docs/governance/executor_guards.json"
POLICY_PATH = ROOT / "docs/governance/review_policy.json"


@dataclass(frozen=True)
class Config:
    label: str
    critical: tuple[str, ...]
    max_files: int
    max_lines: int


@dataclass
class Verdict:
    ok: bool
    files: int = 0
    lines: int = 0
    violations: list[dict] = field(default_factory=list)

    def reasons(self) -> list[str]:
        return [f"{v['rule']}: {v['detail']}" for v in self.violations]


def norm(path: str) -> str:
    """Caminho normalizado para comparacao: barras `/`, sem `./` inicial, caixa ignorada. `..` e absoluto levantam ValueError."""
    p = (path or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    parts = p.split("/")
    if not p or p.startswith("/") or (len(p) > 1 and p[1] == ":") or ".." in parts:
        raise ValueError(f"caminho invalido: {path!r}")
    joined = "/".join(x for x in parts if x not in ("", ".")).casefold()
    return joined + "/" if p.endswith("/") else joined                  # preserva a marca de diretorio das regras


def load_config(guards_path: Path | None = None, policy_path: Path | None = None) -> Config:
    g = json.loads((guards_path or GUARDS_PATH).read_text(encoding="utf-8"))
    pol = json.loads((policy_path or POLICY_PATH).read_text(encoding="utf-8"))
    critical = tuple(sorted({norm(x) for x in [*pol.get("critical_paths", []), *g.get("extra_critical_paths", [])]}))
    if not critical:
        raise ValueError("nenhum caminho critico configurado: recusa (fail-closed)")
    limits = g["limits"]
    return Config(label=g["label"].casefold(), critical=critical, max_files=int(limits["max_files"]), max_lines=int(limits["max_lines"]))


def label_ok(labels: object, cfg: Config) -> bool:
    """Aceita lista de strings ou de objetos `{"name": ...}` (formato da API). Qualquer outra coisa => False."""
    if not isinstance(labels, list):
        return False
    names = [(x.get("name") if isinstance(x, dict) else x) for x in labels]
    return any(isinstance(n, str) and n.strip().casefold() == cfg.label for n in names)


def is_critical(path: str, cfg: Config) -> str | None:
    """Regra critica que casa com `path` (entrada terminada em `/` = prefixo de diretorio; senao arquivo exato), ou None."""
    p = norm(path)
    for rule in cfg.critical:
        if rule.endswith("/"):
            if p.startswith(rule):
                return rule
        elif p == rule:
            return rule
    return None


def parse_numstat(text: str) -> list[tuple[int | None, int | None, str]]:
    """`git diff --numstat --no-renames`: `added<TAB>removed<TAB>path`; binario vem como `-<TAB>-<TAB>path` (=> None). Linha ruim levanta."""
    out = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError(f"linha numstat invalida: {line!r}")
        a, r, path = parts
        out.append((None if a == "-" else int(a), None if r == "-" else int(r), path))
    return out


def evaluate_diff(numstat: str, cfg: Config) -> Verdict:
    """Aplica paths criticos e tetos. `ok=False` se QUALQUER violacao (todas sao listadas, para auditoria)."""
    v = Verdict(ok=True)
    try:
        rows = parse_numstat(numstat)
    except ValueError as exc:
        return Verdict(ok=False, violations=[{"rule": "numstat_ilegivel", "detail": str(exc)}])
    v.files = len(rows)
    for added, removed, path in rows:
        try:
            rule = is_critical(path, cfg)
        except ValueError as exc:
            v.violations.append({"rule": "caminho_invalido", "detail": str(exc)})
            continue
        if rule:
            v.violations.append({"rule": "path_critico", "detail": f"{path} (regra {rule})"})
        if added is None or removed is None:
            v.violations.append({"rule": "binario", "detail": f"{path}: arquivo binario nao e medivel em linhas"})
        else:
            v.lines += added + removed
    if v.files > cfg.max_files:
        v.violations.append({"rule": "max_files", "detail": f"{v.files} arquivos > teto {cfg.max_files}"})
    if v.lines > cfg.max_lines:
        v.violations.append({"rule": "max_lines", "detail": f"{v.lines} linhas > teto {cfg.max_lines}"})
    v.ok = not v.violations
    return v
