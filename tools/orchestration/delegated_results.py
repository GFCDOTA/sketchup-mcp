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


def node_id_of(case: ET.Element) -> str:
    cls = case.get("classname", "")
    return cls.replace(".", "/") + ".py::" + case.get("name", "")


def collect(junit: Path) -> dict[str, str]:
    seen: dict[str, str] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        nid = node_id_of(case)
        if nid in seen:                                              # ids duplicados no relatorio: ambiguo => nunca "passed"
            seen[nid] = "duplicate"
        else:
            seen[nid] = outcome_of(case)
    return seen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    env = os.environ
    base_sha = env["DELEGATED_POLICY_BASE_SHA"].lower()
    policy = dt.validate_policy(json.loads(Path(a.policy).read_text(encoding="utf-8")), base_sha)
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        proc = subprocess.run([sys.executable, "-m", "pytest", *policy.ids, "-p", "no:cacheprovider", "-q", f"--junitxml={junit}", "-o", "junit_family=xunit1"],
                              cwd=a.tree, env={**env, "PYTHONDONTWRITEBYTECODE": "1"})
        seen = collect(junit) if junit.exists() else {}
    results = [{"node_id": nid, "outcome": seen.get(nid, "missing")} for nid in policy.ids]
    report = {"schema": dt.SCHEMA, "repository": env["GITHUB_REPOSITORY"], "head_sha": env["DELEGATED_HEAD_SHA"].lower(), "run_id": int(env["GITHUB_RUN_ID"]),
              "run_attempt": int(env.get("GITHUB_RUN_ATTEMPT", "1")), "workflow_path": dt.WORKFLOW_PATH, "policy_base_sha": base_sha, "pytest_exit_code": proc.returncode,
              "results": results}
    Path(a.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    bad = [r for r in results if r["outcome"] != "passed"]
    print(f"delegated: {len(results) - len(bad)}/{len(results)} passed", flush=True)
    return 0 if not bad and proc.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
