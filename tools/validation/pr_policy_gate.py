"""pr_policy_gate.py — politica de PR do Quality Guardian: vinculo com a Issue, prova SketchUp, testes e fechamento so com evidencia.

Regras (codigo estavel; o motivo e publicado no PR e o merge fica bloqueado enquanto o check reprova):

- PR_NO_ISSUE_LINK         corpo sem `Refs #N` para Issue existente (ou `Issue: N/A — <motivo>`).
- PR_CLOSING_KEYWORD       `Closes|Fixes|Resolves #N`: o GitHub fecharia a Issue no merge, sem evidencia. Use `Refs #N`; quem
                           fecha e o comentario `**Evidência`, conferido pelo `backlog_gate`.
- PR_REFS_HUMAN_BLOCKED    `Refs` a Issue de decisao humana pendente SEM o corpo declarar que nao aplica a decisao
                           (`Decisão: não aplicada`). Mudanca visual/de escopo nao entra sem autorizacao.
- PR_NO_SKP_PROOF_DECLARATION  corpo sem `SKP-proof:`.
- PR_SKP_AFFECTING_WITHOUT_PROOF  caminho que afeta o `.skp` (constituicao #8) tocado e prova ausente: precisa de
                           `.skp` em `artifacts/review/**/final/` no diff; `SKP-proof: N/A` nao vale para esses caminhos.
- PR_CODE_WITHOUT_TESTS    `tools/**`, `core/**` ou `interior/**` (.py/.rb) alterados sem tocar `tests/**` e sem `Tests: N/A — <motivo>`.
- PR_CRITICAL_WITHOUT_REVIEW_LABEL  o PR toca `critical_paths` (docs/governance/review_policy.json) e uma Issue citada nao tem a label
                           `gpt-review-required`: a revisao independente seria dispensada por omissao (FP-057 §9).
- PR_BASELINE_WEAKENED     o PR altera `artifacts/review/fp055/p4/defect_baseline.json` e o novo registro ACEITA defeito (chave nova ou medida
                           pior que a da base): o baseline so muda por correcao comprovada (FP-056), nunca para passar o gate.
- PR_APPROVAL_WITHOUT_PROOF  o corpo declara aparencia/funcional "aprovada" sem `PENDING_HUMAN` ou evidencia: aparencia e do Felipe.

Uso:  python -m tools.validation.pr_policy_gate --pr <N>      (le corpo e arquivos com `gh`; exit 1 se reprovar)
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from tools.validation.backlog_gate import REPO, Finding, _gh

SKP_AFFECTING = (
    re.compile(r"^tools/sketchup/shell/build_plan_shell_skp\.(py|rb)$"),
    re.compile(r"^tools/sketchup/furnish/place_layout_.*\.(py|rb)$"),
    re.compile(r"^tools/quadrado/render_view\.(py|rb)$"),
    re.compile(r"^tools/sketchup/runner_safety\.py$"),
    re.compile(r"^fixtures/[^/]+/.*\.json$"),
    re.compile(r"^artifacts/[^/]+/[^/]+\.skp$"),
    re.compile(r"^tools/(build|render)_[^/]*\.(py|rb)$"),
)
CODE = re.compile(r"^(tools|core|interior)/.*\.(py|rb)$")
_CLOSING = re.compile(r"\b(close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
_REFS = re.compile(r"\b(?:refs?|relates to|issue)\s*:?\s*#(\d+)", re.IGNORECASE)
_APPROVED = re.compile(r"(visual|apar[eê]ncia|funcional)\w*\s+(?:est[aá]\s+)?(aprovad[ao]|approved)", re.IGNORECASE)


BASELINE_PATH = "artifacts/review/fp055/p4/defect_baseline.json"


def check(body: str, files: list[str], issues: dict[int, dict], critical_paths: list[str] | tuple[str, ...] = (),
          baseline: tuple[list[dict], list[dict]] | None = None) -> list[Finding]:
    """`baseline`: (defeitos na base, defeitos no PR) quando o PR altera o registro; None = nao alterado ou nao verificavel."""
    found: list[Finding] = []
    if BASELINE_PATH in files and baseline is not None:
        from tools.validation import defect_baseline as db
        for why in db.weakened(*baseline):
            found.append(Finding(0, "PR_BASELINE_WEAKENED", why))
    body = body or ""
    for _kw, n in _CLOSING.findall(body):
        found.append(Finding(int(n), "PR_CLOSING_KEYWORD", f"use 'Refs #{n}': a Issue so fecha com comentario de evidencia"))
    refs = sorted({int(n) for n in _REFS.findall(body)})
    na = re.search(r"Issue:\s*N/A\s*[—-]\s*\S+", body, re.IGNORECASE)
    if not na and not any(n in issues for n in refs):
        found.append(Finding(0, "PR_NO_ISSUE_LINK", "corpo sem 'Refs #N' para uma Issue existente (ou 'Issue: N/A — motivo')"))
    for n in refs:
        lab = {x["name"] for x in issues.get(n, {}).get("labels", [])}
        if "bloqueio:human-decision" in lab and issues[n].get("state") == "OPEN" and not re.search(r"decis[ãa]o:\s*n[ãa]o aplicada", body, re.I):
            found.append(Finding(n, "PR_REFS_HUMAN_BLOCKED", f"#{n} e decisao humana pendente; declare 'Decisão: não aplicada'"))
    if not re.search(r"SKP-proof\s*:", body, re.IGNORECASE):
        found.append(Finding(0, "PR_NO_SKP_PROOF_DECLARATION", "corpo sem 'SKP-proof: ...'"))
    touched = [f for f in files if any(p.match(f) for p in SKP_AFFECTING)]
    has_skp = any(re.match(r"^artifacts/review/.+/final/.+\.skp$", f) for f in files)
    if touched and not has_skp:
        found.append(Finding(0, "PR_SKP_AFFECTING_WITHOUT_PROOF", f"afeta o .skp ({touched[:3]}) sem .skp em artifacts/review/**/final/"))
    if any(CODE.match(f) for f in files) and not any(f.startswith("tests/") for f in files) \
            and not re.search(r"Tests:\s*N/A\s*[—-]\s*\S+", body, re.IGNORECASE):
        found.append(Finding(0, "PR_CODE_WITHOUT_TESTS", "codigo alterado sem teste (ou 'Tests: N/A — motivo')"))
    crit = [f for f in files if any(f == c or (c.endswith("/") and f.startswith(c)) for c in critical_paths)]
    if crit:
        for n in refs:
            lab = {x["name"] for x in issues.get(n, {}).get("labels", [])}
            if n in issues and "gpt-review-required" not in lab:
                found.append(Finding(n, "PR_CRITICAL_WITHOUT_REVIEW_LABEL", f"toca caminho critico ({crit[:2]}): #{n} precisa da label gpt-review-required"))
    if _APPROVED.search(body) and "PENDING_HUMAN" not in body:
        found.append(Finding(0, "PR_APPROVAL_WITHOUT_PROOF", "declara aparencia/funcional aprovada; aparencia e do Felipe (PENDING_HUMAN)"))
    return found


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", type=int, required=True)
    args = ap.parse_args(argv)
    pr = json.loads(_gh("pr", "view", str(args.pr), "--repo", REPO, "--json", "body,files"))
    files = [f["path"] for f in pr["files"]]
    raw = json.loads(_gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "1000", "--json", "number,state,labels"))
    from tools.validation.backlog_gate import ROOT
    pol_path = ROOT / "docs/governance/review_policy.json"
    crit = json.loads(pol_path.read_text(encoding="utf-8")).get("critical_paths", []) if pol_path.exists() else []
    baseline = None
    if BASELINE_PATH in files:
        base = json.loads(_gh("pr", "view", str(args.pr), "--repo", REPO, "--json", "baseRefName"))["baseRefName"]
        old = json.loads(_gh("api", "-H", "Accept: application/vnd.github.raw", f"repos/{REPO}/contents/{BASELINE_PATH}?ref={base}"))["defects"]
        new = json.loads((ROOT / BASELINE_PATH).read_text(encoding="utf-8"))["defects"]
        baseline = (old, new)
    findings = check(pr["body"], files, {i["number"]: i for i in raw}, crit, baseline)
    for f in findings:
        print(f)
    print(f"pr_policy_gate: {len(findings)} divergencia(s) no PR #{args.pr}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
