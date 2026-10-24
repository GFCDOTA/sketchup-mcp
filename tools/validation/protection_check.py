"""protection_check.py — a protecao de branch esta REALMENTE ativa? (FP-057 P4)

    python -m tools.validation.protection_check [--branches develop main]

Le `GET branches/<b>/protection` e reprova se faltar contexto obrigatorio, `enforce_admins`, ou se force-push/delecao estiverem
liberados. Sem permissao de admin (404/403) o resultado e `NOT_VERIFIED` (exit 2), nunca PASS por ausencia de dado.
"""
from __future__ import annotations

import json
import sys

from tools.validation.backlog_gate import REPO, _gh

REQUIRED_CONTEXTS = ("uv lock is current", "pytest (py3.11)", "pytest (py3.12)", "deterministic fidelity gates",
                     "mcp server (smoke + stdio handshake)", "qg: backlog, issues and specs", "qg: PR policy",
                     "qg: geometry, program and integration")


def evaluate(protection: dict | None, required: tuple[str, ...] = REQUIRED_CONTEXTS) -> tuple[str, list[str]]:
    """('PASS'|'FAIL'|'NOT_VERIFIED', razoes) a partir do JSON da API (ou None se indisponivel)."""
    if protection is None:
        return "NOT_VERIFIED", ["protecao ilegivel (sem permissao de admin ou branch sem protecao)"]
    why = []
    have = set((protection.get("required_status_checks") or {}).get("contexts") or [])
    missing = sorted(set(required) - have)
    if missing:
        why.append(f"checks obrigatorios ausentes: {missing}")
    if not (protection.get("enforce_admins") or {}).get("enabled"):
        why.append("enforce_admins desligado: administrador contorna os checks")
    if (protection.get("allow_force_pushes") or {}).get("enabled"):
        why.append("force-push permitido")
    if (protection.get("allow_deletions") or {}).get("enabled"):
        why.append("delecao da branch permitida")
    return ("FAIL", why) if why else ("PASS", [])


def main(argv: list[str]) -> int:
    branches = argv[argv.index("--branches") + 1:] if "--branches" in argv else ["develop", "main"]
    worst = 0
    for b in branches:
        try:
            prot = json.loads(_gh("api", f"repos/{REPO}/branches/{b}/protection"))
        except (RuntimeError, ValueError):
            prot = None
        status, why = evaluate(prot)
        print(f"{b}: {status}" + ("" if not why else " — " + "; ".join(why)))
        worst = max(worst, {"PASS": 0, "FAIL": 1, "NOT_VERIFIED": 2}[status])
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
