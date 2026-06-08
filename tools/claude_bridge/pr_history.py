"""Gera o snapshot pr_history.json (fonte das metricas da aba Marcos) via `gh pr list`.

O cockpit NAO chama gh por request (lento: additions/deletions e' 1 call por PR). Entao
este script materializa um snapshot regeneravel; o server computa as metricas DELE ao vivo
(marcos_metrics.compute_metrics). Refresh = rodar este script de novo.

Uso:  python -m tools.claude_bridge.pr_history            # escreve pr_history.json
      python -m tools.claude_bridge.pr_history --print    # so imprime contagem
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = "GFCDOTA/sketchup-mcp"
OUT = Path(__file__).with_name("pr_history.json")
FIELDS = "number,title,mergedAt,additions,deletions,state"


def _gh():
    for c in ("gh", "gh.cmd", r"C:\Program Files\GitHub CLI\gh.exe"):
        p = shutil.which(c) if not c.endswith(".exe") else (c if Path(c).is_file() else None)
        if p:
            return p
    return "gh"


def fetch():
    cmd = [_gh(), "pr", "list", "--repo", REPO, "--state", "all",
           "--limit", "500", "--json", FIELDS]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        raise RuntimeError(f"gh falhou: {p.stderr.strip()[:300]}")
    data = json.loads(p.stdout)
    # so o que as metricas usam; sem texto livre alem do title (sem segredo)
    return [{"number": x.get("number"), "title": x.get("title", ""),
             "mergedAt": x.get("mergedAt"), "state": x.get("state"),
             "additions": x.get("additions"), "deletions": x.get("deletions")}
            for x in data]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", dest="just_print")
    args = ap.parse_args()
    prs = fetch()
    snapshot = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "repo": REPO, "source": "gh pr list", "count": len(prs), "prs": prs}
    if args.just_print:
        merged = [p for p in prs if p.get("state") == "MERGED"]
        print(f"{len(prs)} PRs ({len(merged)} merged) ate #{max((p['number'] for p in prs), default=0)}")
        return
    OUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"escrito {OUT} ({len(prs)} PRs, {OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    sys.exit(main())
