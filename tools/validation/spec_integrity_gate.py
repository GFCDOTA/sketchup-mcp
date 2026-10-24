"""spec_integrity_gate.py — as SPECs FP-055/FP-056 nao podem apontar para o vazio (Quality Guardian, P1).

- SPEC_ISSUE_MISSING   `#N` citado numa SPEC que nao existe no repositorio.
- SPEC_PATH_MISSING    caminho `docs/...`, `artifacts/review/...` ou `tools/...` citado em crase numa SPEC que nao existe.
- SPEC_DONE_OPEN_ISSUE linha de tabela marcada `feita`/`entregue` cuja Issue citada (so uma) segue aberta sem decisao pendente.
                       (a SPEC nao pode declarar pronto o que o backlog mantem aberto)

So le texto e a lista de Issues; nenhuma regra de geometria. Excecoes em `docs/governance/backlog_exceptions.json`
(chave `"spec:<arquivo>"`).
Uso:  python -m tools.validation.spec_integrity_gate
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from tools.validation.backlog_gate import REPO, Finding, _gh

ROOT = Path(__file__).resolve().parent.parent.parent
SPECS = ("FP-055_intelligent_pipeline_recovery.md", "FP-056_usable_space_support_barriers.md")
_PATH = re.compile(r"`((?:docs|artifacts/review|tools|tests)/[A-Za-z0-9_./\-]+)`")
_DONE_ROW = re.compile(r"^\|[^|]*\|\s*(?:\*\*)?(feitas?|entregues?)(?:\*\*)?[^|]*\|(.*)\|\s*$", re.IGNORECASE)


def check(spec_texts: dict[str, str], issues: dict[int, dict], root: Path = ROOT, exceptions: dict | None = None) -> list[Finding]:
    found: list[Finding] = []
    ok = exceptions or {}
    for name, text in sorted(spec_texts.items()):
        skip = ok.get(f"spec:{name}", {})
        for n in sorted({int(x) for x in re.findall(r"#(\d{2,4})\b", text)}):
            if n not in issues and "SPEC_ISSUE_MISSING" not in skip:
                found.append(Finding(n, "SPEC_ISSUE_MISSING", f"{name} cita #{n}, inexistente"))
        for p in sorted(set(_PATH.findall(text))):
            if "*" in p or p.endswith("/"):
                continue
            if not (root / p).exists() and "SPEC_PATH_MISSING" not in skip:
                found.append(Finding(0, "SPEC_PATH_MISSING", f"{name} cita `{p}`, inexistente"))
        for line in text.splitlines():
            m = _DONE_ROW.match(line)
            if not m:
                continue
            refs = [int(x) for x in re.findall(r"#(\d{2,4})\b", m.group(2))]
            if len(refs) == 1 and refs[0] in issues and issues[refs[0]]["state"] == "OPEN" and "SPEC_DONE_OPEN_ISSUE" not in skip:
                found.append(Finding(refs[0], "SPEC_DONE_OPEN_ISSUE", f"{name}: linha 'feita' aponta #{refs[0]} aberta: {line[:80]}"))
    return found


def main() -> int:
    raw = json.loads(_gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "1000", "--json", "number,state"))
    issues = {i["number"]: i for i in raw}
    texts = {n: (ROOT / "docs/specs" / n).read_text(encoding="utf-8") for n in SPECS if (ROOT / "docs/specs" / n).exists()}
    exc_path = ROOT / "docs/governance/backlog_exceptions.json"
    exceptions = json.loads(exc_path.read_text(encoding="utf-8")) if exc_path.exists() else {}
    findings = check(texts, issues, ROOT, exceptions)
    for f in findings:
        print(f)
    print(f"spec_integrity_gate: {len(findings)} divergencia(s) em {len(texts)} SPEC(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
