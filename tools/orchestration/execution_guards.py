"""execution_guards.py — protecoes puras e fail-closed do executor local (FP-057/P8, Issue #589). SEM rede, SEM subprocesso, SEM LLM.

Tres perguntas, todas respondidas por funcao pura (a ligacao no executor vem em PRs seguintes):
  - `label_ok`        o PR tem a label de execucao (`executor-ok`)?
  - `is_critical`     o caminho e critico (workflows, politica de revisao, gates, governanca/execucao)? Une `critical_paths` da
                      `review_policy.json` com `extra_critical_paths` de `executor_guards.json`.
  - `evaluate_diff`   o diff (saida de `git diff --numstat --no-renames`) respeita paths criticos e o teto de arquivos/linhas?

Fail-closed: entrada ilegivel, caminho com `..`, numero invalido ou binario => violacao (nunca "assume que esta ok"). A comparacao de
caminhos normaliza barras, ignora caixa e remove ponto/espaco final de cada componente (NTFS). Configuracao incompleta ou de tipo errado
RECUSA a carga (`ValueError`): nunca cai num conjunto parcial. Tetos iniciais: 8 arquivos / 300 linhas (confirmados pelo TL na SPEC).

CONTRATO DO CALLER: a entrada de `evaluate_diff` e EXATAMENTE a saida de `git` com `NUMSTAT_ARGS` (`--numstat -z --no-renames`): registros
`adicionadas<TAB>removidas<TAB>caminho<NUL>`, caminho CRU (sem aspas C do `core.quotePath`). Saida sem terminador NUL e recusada.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Piso imutavel no codigo: vale mesmo que review_policy.json e executor_guards.json sejam editados/esvaziados.
BASELINE_CRITICAL = (".github/workflows/", "docs/governance/")
NUMSTAT_ARGS = ("diff", "--numstat", "-z", "--no-renames")
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
    comps = [c.rstrip(". ") if c not in (".", "") else c for c in parts]       # NTFS: "workflows /" e "workflows./" == "workflows"
    joined = "/".join(x for x in comps if x not in ("", ".")).casefold()
    return joined + "/" if p.endswith("/") else joined                  # preserva a marca de diretorio das regras


def _str_list(value: object, what: str, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value) or (not value and not allow_empty):
        raise ValueError(f"{what}: esperado lista{'' if allow_empty else ' NAO vazia'} de strings nao vazias; recusa a carga (fail-closed)")
    return value


def _pos_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{what}: esperado inteiro positivo, veio {value!r}; recusa a carga (fail-closed)")
    return value


def load_config(guards_path: Path | None = None, policy_path: Path | None = None) -> Config:
    """Carrega e VALIDA. Qualquer ausencia/tipo errado/limite nao positivo => ValueError (nunca um conjunto parcial)."""
    g = json.loads((guards_path or GUARDS_PATH).read_text(encoding="utf-8"))
    pol = json.loads((policy_path or POLICY_PATH).read_text(encoding="utf-8"))
    if not isinstance(g, dict) or not isinstance(pol, dict):
        raise ValueError("configuracao: esperado objeto JSON; recusa a carga (fail-closed)")
    if "critical_paths" not in pol:
        raise ValueError("review_policy.json sem `critical_paths`: recusa a carga (fail-closed)")
    policy_paths = _str_list(pol["critical_paths"], "review_policy.critical_paths", allow_empty=False)
    extra = _str_list(g.get("extra_critical_paths"), "executor_guards.extra_critical_paths", allow_empty=True)
    label = g.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("executor_guards.label: esperado string nao vazia; recusa a carga (fail-closed)")
    limits = g.get("limits")
    if not isinstance(limits, dict):
        raise ValueError("executor_guards.limits: esperado objeto; recusa a carga (fail-closed)")
    critical = tuple(sorted({norm(x) for x in [*BASELINE_CRITICAL, *policy_paths, *extra]}))
    return Config(label=label.strip().casefold(), critical=critical, max_files=_pos_int(limits.get("max_files"), "limits.max_files"),
                  max_lines=_pos_int(limits.get("max_lines"), "limits.max_lines"))


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
    """Saida de `git diff --numstat -z --no-renames` (ver `NUMSTAT_ARGS`): `adicionadas<TAB>removidas<TAB>caminho` terminado em NUL.
    O caminho e CRU (pode conter TAB ou aspas): so os dois primeiros TAB separam campos. Binario = `-<TAB>-` (=> None). Formato ambiguo
    (sem NUL final, campo faltando, numero invalido, caminho vazio) levanta ValueError."""
    if not text:
        return []
    if not text.endswith("\0"):
        raise ValueError("numstat sem terminador NUL: use `git diff --numstat -z --no-renames` (formato com aspas C e ambiguo)")
    out = []
    for rec in text[:-1].split("\0"):
        parts = rec.split("\t", 2)
        if len(parts) != 3 or not parts[2]:
            raise ValueError(f"registro numstat invalido: {rec!r}")
        a, r, path = parts
        for n in (a, r):
            if n != "-" and not (n.isascii() and n.isdigit()):
                raise ValueError(f"numero invalido no numstat: {n!r}")
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
