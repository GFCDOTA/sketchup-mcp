"""audit_report.py — relatorio de auditoria versionado para revisao independente (ChatGPT conectado ao GitHub, sem API paga).

    python -m tools.validation.audit_report --out docs/reports/audit/audit_2026-10-25.md [--since 2026-10-18] [--with-geometry]

Conteudo (so fatos medidos; nada e aprovado por este relatorio):
1. PRs mergeados desde `--since` e PRs abertos;
2. Issues bloqueadas por causa (technical | dependency | evidence | human-decision) e as que realmente dependem do proprietario;
3. Defeitos: ultima execucao real no SketchUp (artifacts/review/fp056/p6) e, com `--with-geometry`, o veredito do gemeo em caixas
   (novos, piores, resolvidos, perda de programa registrada);
4. Capacidades: implementadas x invocadas x consumidas pela geracao (retrato `docs/governance/consumption_baseline.v1.json`);
5. Provas reais disponiveis (`artifacts/review/**/summary.json`: commit, casos, PIDs) com o que cada uma NAO prova.
Deterministico: a data vem de `--date` (padrao: hoje) e nenhuma ordem depende do relogio alem dela.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from tools.validation.backlog_gate import REPO, _gh

ROOT = Path(__file__).resolve().parent.parent.parent
CAUSES = ("technical", "dependency", "evidence", "human-decision")


def blocked_by_cause(issues: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {c: [] for c in CAUSES}
    out["sem causa"] = []
    for i in sorted(issues, key=lambda x: x["number"]):
        names = {lab["name"] for lab in i["labels"]}
        if i["state"] != "OPEN" or "blocked" not in names:
            continue
        cause = next((n.split(":", 1)[1] for n in sorted(names) if n.startswith("bloqueio:")), "sem causa")
        out.setdefault(cause, []).append(i)
    return out


def proofs(root: Path = ROOT) -> list[dict]:
    rows = []
    for p in sorted((root / "artifacts/review").glob("**/summary.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cases = d.get("cases")
        if isinstance(cases, list) and cases and isinstance(cases[0], dict) and "ok" in cases[0]:
            rows.append({"path": p.relative_to(root).as_posix(), "commit": str(d.get("commit", "?"))[:8], "dirty": d.get("dirty"),
                         "cases_ok": sum(bool(c["ok"]) for c in cases), "cases": len(cases), "pids": d.get("pids", []),
                         "failed": [c["case"] for c in cases if not c["ok"]]})
    return rows


def capabilities(root: Path = ROOT) -> dict:
    base = json.loads((root / "docs/governance/consumption_baseline.v1.json").read_text(encoding="utf-8"))
    cat = json.loads((root / "tools/rooms/capability_catalog.v1.json").read_text(encoding="utf-8"))
    states = {c["id"]: (c["implementation"]["state"], c["validation"]["state"]) for c in cat["capabilities"]}
    return {"base": base, "catalog": states}


def render(data: dict) -> str:
    L: list[str] = [f"# Auditoria periodica — {data['date']}", "",
                    f"Commit `{data['commit']}` · repositorio `{REPO}` · Project <https://github.com/orgs/GFCDOTA/projects/1>", "",
                    "> Relatorio de **fatos medidos** para revisao independente. Nao aprova geometria, funcao nem aparencia "
                    "(aparencia: `PENDING_HUMAN`).", ""]
    L += ["## 1. PRs", "", f"Mergeados desde {data['since']}: **{len(data['merged'])}**", ""]
    L += [f"- [#{p['number']}]({p['url']}) {p['title']} (`{(p.get('mergeCommit') or {}).get('oid', '')[:7]}`)" for p in data["merged"]]
    L += ["", f"Abertos: **{len(data['open_prs'])}**", ""]
    L += [f"- [#{p['number']}]({p['url']}) {p['title']}" for p in data["open_prs"]]
    L += ["", "## 2. Issues bloqueadas por causa", ""]
    for cause, rows in data["blocked"].items():
        if rows:
            L.append(f"**{cause}** ({len(rows)}): " + ", ".join(f"#{r['number']}" for r in rows))
    L.append("")
    owner = data["blocked"].get("human-decision", [])
    L += [f"### Decisoes que realmente dependem do proprietario ({len(owner)})", ""]
    L += [f"- #{r['number']} {r['title']}" for r in owner]
    L += ["", "## 3. Defeitos e regressoes", ""]
    g = data.get("geometry")
    if g:
        L += [f"Gemeo em caixas: **{g['verdict']}** — novos {len(g['new'])}, piores {len(g['worse'])}, resolvidos {len(g['resolved'])}, "
              f"persistentes do baseline {g['persisting_baseline_defects']}, perda de programa registrada {list(g['known_program_gaps'])}, "
              f"pre-voo {g['preflight']}. `geometric_approved={g['geometric_approved']}`, `functional_approved={g['functional_approved']}`.", ""]
    else:
        L += ["Gemeo em caixas: nao executado neste relatorio (`--with-geometry`).", ""]
    L += ["## 4. Capacidades: implementadas x invocadas x consumidas", "",
          "| Capacidade | Implementacao | Validacao | Invocada | Consumida |", "|---|---|---|---|---|"]
    caps = data["capabilities"]
    for cid, st in sorted(caps["base"]["capabilities"].items()):
        impl, val = caps["catalog"].get(cid, ("?", "?"))
        L.append(f"| `{cid}` | {impl} | {val} | {st['INVOKED']} | {st['CONSUMED']} |")
    b = caps["base"]
    L += ["", f"Especialistas invocados {b['specialists_invoked']}/{b['specialists_total']}; receitas consumidas "
              f"{b['recipes_consumed']}/{b['recipes_total']}; modulos vigiados executados: "
              f"{sum(b['watched_executed'].values())}/{len(b['watched_executed'])}.", "",
          "## 5. Provas reais disponiveis (SketchUp)", "",
          "| Evidencia | Commit | Casos ok | Falhas | PIDs |", "|---|---|---|---|---|"]
    for p in data["proofs"]:
        L.append(f"| `{p['path']}` | `{p['commit']}`{' (dirty)' if p['dirty'] else ''} | {p['cases_ok']}/{p['cases']} | "
                 f"{', '.join(p['failed']) or '—'} | {len(p['pids'])} |")
    L += ["", "Cada prova vale para o commit indicado; teste verde ou `.skp` salvo nao aprovam funcao nem aparencia.", ""]
    return "\n".join(L)


def collect(since: str, date: str, with_geometry: bool) -> dict:
    merged = json.loads(_gh("pr", "list", "--repo", REPO, "--state", "merged", "--limit", "200", "--search", f"merged:>={since}",
                            "--json", "number,title,url,mergeCommit"))
    open_prs = json.loads(_gh("pr", "list", "--repo", REPO, "--state", "open", "--json", "number,title,url"))
    issues = json.loads(_gh("issue", "list", "--repo", REPO, "--state", "all", "--limit", "1000", "--json", "number,title,state,labels"))
    commit = Path(ROOT / ".git").exists() and __import__("subprocess").run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                                                           capture_output=True, text=True).stdout.strip()
    data = {"date": date, "since": since, "commit": commit or "?", "merged": sorted(merged, key=lambda p: p["number"]),
            "open_prs": sorted(open_prs, key=lambda p: p["number"]), "blocked": blocked_by_cause(issues),
            "capabilities": capabilities(), "proofs": proofs()}
    if with_geometry:
        from tools.validation import quality_geometry_gate as gg
        data["geometry"] = gg.evaluate()
    return data


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--since", default=(dt.date.today() - dt.timedelta(days=7)).isoformat())
    ap.add_argument("--with-geometry", action="store_true")
    a = ap.parse_args(argv)
    data = collect(a.since, a.date, a.with_geometry)
    out = ROOT / a.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data) + "\n", encoding="utf-8", newline="\n")
    out.with_suffix(".json").write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str) + "\n", encoding="utf-8", newline="\n")
    print(f"relatorio: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
