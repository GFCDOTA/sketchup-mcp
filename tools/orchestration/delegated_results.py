"""Coletor da evidencia dos testes DELEGADOS ao CI (FP-060 MT-03). Roda no workflow `delegated-tests` (definicao e este arquivo vem da BASE, nao do PR).

Executa EXATAMENTE os node ids da politica da base contra a arvore do PR e escreve `results.json` com o resultado individual de cada um, ligado a repositorio, HEAD, execucao,
tentativa, workflow e commit da politica. Falha (exit != 0) se qualquer teste nao passou: sem artefato de sucesso nao ha evidencia.

Uso: python delegated_results.py --policy <politica da base> --tree <arvore do PR> --out results.json
Ambiente: GITHUB_REPOSITORY, DELEGATED_HEAD_SHA, GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT, DELEGATED_POLICY_BASE_SHA
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.orchestration import delegated_tests as dt  # noqa: E402


def outcome_of(case: ET.Element) -> str:
    """passed | failed | error | skipped (xfail e skip contam como skipped: nunca passam)."""
    for child in case:
        tag = child.tag
        if tag == "failure":
            return "failed"
        if tag == "error":
            return "error"
        if tag == "skipped":
            return "skipped"
    return "passed"


def junit_key(node_id: str) -> tuple[str, str]:
    """(classname, name) que o pytest grava no JUnit para um node id EXATO da politica: `tests/a/b.py::T::m[p]` -> (`tests.a.b.T`, `m[p]`).
    O caminho inverso (classname -> arquivo) e ambiguo (`tests.a.b` pode ser `tests/a/b.py` ou a classe `b` de `tests/a.py`); por isso so se mapeia da politica para o JUnit."""
    path, _, rest = node_id.partition("::")
    parts = rest.split("::")
    module = path[:-3].replace("/", ".")
    return ".".join([module, *parts[:-1]]), parts[-1]


def collect(junit: Path, ids: list[str] | tuple[str, ...]) -> dict[str, str]:
    """Resultado de CADA node id da politica: passed | failed | error | skipped | duplicate | ambiguous; ausente = nao executado."""
    keys: dict[tuple[str, str], list[str]] = {}
    for nid in ids:
        keys.setdefault(junit_key(nid), []).append(nid)
    seen: dict[str, str] = {}
    for key, owners in keys.items():
        if len(owners) > 1:                                          # dois ids da politica com o mesmo registro no JUnit: nenhum pode ser afirmado
            seen.update({nid: "ambiguous" for nid in owners})
    for case in ET.parse(junit).getroot().iter("testcase"):
        owners = keys.get((case.get("classname", ""), case.get("name", "")))
        if not owners or len(owners) > 1:
            continue
        nid = owners[0]
        seen[nid] = "duplicate" if nid in seen else outcome_of(case)  # o mesmo teste duas vezes no relatorio: ambiguo => nunca "passed"
    return seen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--tree", help="roda o pytest nesta arvore (uso local); no CI o job confiavel usa --junit e NUNCA executa codigo do PR")
    ap.add_argument("--junit", help="JUnit ja produzido pelo job nao confiavel: so e LIDO (ausente/ilegivel = todo id `missing`)")
    ap.add_argument("--pytest-exit-code", type=int, default=None, help="codigo de saida do pytest no job nao confiavel (com --junit)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if bool(a.tree) == bool(a.junit):
        ap.error("informe exatamente um entre --tree e --junit")
    env = os.environ
    base_sha = env["DELEGATED_POLICY_BASE_SHA"].lower()
    policy = dt.validate_policy(json.loads(Path(a.policy).read_text(encoding="utf-8")), base_sha)
    if a.junit:
        junit = Path(a.junit)
        try:
            seen = collect(junit, policy.ids) if junit.is_file() else {}
        except ET.ParseError:
            seen = {}                                                    # JUnit ilegivel: nenhum teste pode ser afirmado
        exit_code = a.pytest_exit_code if a.pytest_exit_code is not None else 1
    else:
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / "junit.xml"
            proc = subprocess.run([sys.executable, "-m", "pytest", *policy.ids, "-p", "no:cacheprovider", "-q", f"--junitxml={junit}", "-o", "junit_family=xunit1"],
                                  cwd=a.tree, env={**env, "PYTHONDONTWRITEBYTECODE": "1"})
            seen = collect(junit, policy.ids) if junit.exists() else {}
            exit_code = proc.returncode
    results = [{"node_id": nid, "outcome": seen.get(nid, "missing")} for nid in policy.ids]
    report = {"schema": dt.SCHEMA, "repository": env["GITHUB_REPOSITORY"], "head_sha": env["DELEGATED_HEAD_SHA"].lower(), "run_id": int(env["GITHUB_RUN_ID"]),
              "run_attempt": int(env.get("GITHUB_RUN_ATTEMPT", "1")), "workflow_path": dt.WORKFLOW_PATH, "policy_base_sha": base_sha, "pytest_exit_code": exit_code,
              "results": results}
    Path(a.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    bad = [r for r in results if r["outcome"] != "passed"]
    print(f"delegated: {len(results) - len(bad)}/{len(results)} passed", flush=True)
    return 0 if not bad and exit_code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
