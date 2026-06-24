"""build_kgraph.py — gera tools/kgraph.json a partir de um vault de notas markdown.

Lê um diretório de .md (com frontmatter + [[wikilinks]]), extrai nós (notas) e
arestas (links), e escreve um grafo JSON que o studio_dashboard (:8782 /grafo)
renderiza. stdlib only. Determinístico/idempotente: rodar 2x = mesmo output.

Uso:  python tools/build_kgraph.py [--vault PATH] [--out PATH]
Default vault: E:\\sketchup-mcp-vault   default out: tools/kgraph.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LINK_RE = re.compile(r"\[\[([^\]\|#]+)")
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# domain (frontmatter) -> rótulo de área legível (vira a cor/grupo no grafo)
AREA = {
    "pipeline": "Pipeline (PDF→.skp)",
    "furniture": "Móveis",
    "interior-render": "Interiores & Render",
    "cockpit-ops": "Cockpit & Ops",
    "process-meta": "Processo & Meta",
}
CORE_AREA = "Núcleo / Mapas"


def _fm_value(fm: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+)$", fm, re.MULTILINE)
    return m.group(1).strip().strip('"').strip("'") if m else ""


def build(vault: Path) -> dict:
    files = sorted(vault.rglob("*.md"))
    by_id: dict[str, dict] = {}
    nodes: list[dict] = []
    for f in files:
        txt = f.read_text("utf-8", "ignore")
        mfm = FM_RE.match(txt)
        fm = mfm.group(1) if mfm else ""
        body = txt[mfm.end():] if mfm else txt
        stem = f.stem
        nid = stem.lower()
        domain = _fm_value(fm, "domain")
        node = {
            "id": nid,
            "stem": stem,
            "title": _fm_value(fm, "title") or stem,
            "type": _fm_value(fm, "type") or "note",
            "domain": domain,
            "folder": f.parent.name if f.parent != vault else "",
            "area": AREA.get(domain, CORE_AREA),
            "deg": 0,
            "_body": body,
        }
        by_id[nid] = node
        nodes.append(node)

    links: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for n in nodes:
        for m in LINK_RE.finditer(n.pop("_body")):
            tgt = m.group(1).strip().lower()
            if tgt in by_id and tgt != n["id"] and (n["id"], tgt) not in seen:
                seen.add((n["id"], tgt))
                links.append({"source": n["id"], "target": tgt})
                by_id[n["id"]]["deg"] += 1
                by_id[tgt]["deg"] += 1

    areas: dict[str, int] = {}
    for n in nodes:
        areas[n["area"]] = areas.get(n["area"], 0) + 1
    return {
        "nodes": nodes,
        "links": links,
        "areas": [{"name": k, "count": v} for k, v in sorted(areas.items(), key=lambda kv: -kv[1])],
        "stats": {"nodes": len(nodes), "links": len(links)},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=r"E:\sketchup-mcp-vault")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "kgraph.json"))
    a = ap.parse_args(argv)
    vault = Path(a.vault)
    if not vault.is_dir():
        print(f"vault não encontrado: {vault}")
        return 2
    g = build(vault)
    out = Path(a.out).resolve()
    out.write_text(json.dumps(g, ensure_ascii=False, indent=1), "utf-8")
    print(f"kgraph: {g['stats']['nodes']} nós, {g['stats']['links']} arestas -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
