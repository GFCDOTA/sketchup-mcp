"""Indice dos modulos de comodo: o que cada `tools/rooms/<comodo>/` tem, gerado das fontes reais (nunca escrito a mao).

Fontes: perfil do especialista (`specialist.v1.json`), catalogo de capacidades (estado de validacao/visual), bindings sem
capacidade (lacunas), fragmentos do especialista (`fragments/*.fragment.v1.json`, quando existirem) e os arquivos versionados.
Escreve dois lugares:
  - `README.md` da raiz, entre os marcadores `<!-- rooms-index:begin -->` / `<!-- rooms-index:end -->` (tabela curta);
  - `tools/rooms/README.md` (detalhe por comodo: escopo, capacidades, lacunas, arquivos por pasta).

    python -m tools.navigation.rooms_index --write     # regenera
    python -m tools.navigation.rooms_index --check     # exit 1 se o que esta commitado divergir (usado no teste)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEGIN, END = "<!-- rooms-index:begin -->", "<!-- rooms-index:end -->"
ORDER = ("kitchen", "living", "bedroom", "bathroom", "service", "closet", "home_office", "balcony", "circulation")
TITLE = {"kitchen": "Cozinha", "living": "Sala", "bedroom": "Quarto", "bathroom": "Banheiro", "service": "Serviço",
         "closet": "Closet", "home_office": "Home office", "balcony": "Varanda", "circulation": "Circulação"}
ROLE = {"planner": "planeja e constrói", "reuse": "reusa outro cômodo", "advisory": "só consultivo",
        "validation_only": "só valida"}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def collect(root: Path = ROOT) -> dict:
    files = subprocess.check_output(["git", "-C", str(root), "ls-files", "tools/rooms"], text=True).splitlines()
    catalog = _json(root / "tools/rooms/capability_catalog.v1.json")
    caps = {c["id"]: c for c in catalog["capabilities"]}
    rooms = {}
    for room in ORDER:
        profile = _json(root / "tools/rooms" / room / "specialist.v1.json")
        own = [f for f in files if f.startswith(f"tools/rooms/{room}/")]
        folders = defaultdict(list)
        for f in own:
            rel = f[len(f"tools/rooms/{room}/"):]
            folders[rel.split("/")[0] if "/" in rel else "."].append(rel)
        cap_rows = []
        for cid in profile.get("capability_ids", []):
            c = caps.get(cid)
            if c:
                cap_rows.append({"id": cid, "validation": c["validation"]["state"], "visual": c["visual"]["state"],
                                 "shared": c["room"] == "shared"})
        gaps = [{"binding": b["id"], "gap": b.get("gap") or ""} for b in catalog["bindings"]
                if b["room"] == room and b["capability_id"] is None]
        fragments = sorted(p.name.split(".")[0] for p in (root / "tools/rooms" / room / "fragments").glob("*.fragment.v1.json"))
        rooms[room] = {"title": TITLE[room], "role": profile.get("role"), "state": profile.get("state"),
                       "reuse_of": profile.get("reuse_of"), "scope": profile.get("scope", ""), "files": len(own),
                       "python": len([f for f in own if f.endswith(".py")]), "ruby": len([f for f in own if f.endswith(".rb")]),
                       "folders": {k: sorted(v) for k, v in sorted(folders.items())}, "capabilities": cap_rows,
                       "gaps": gaps, "fragments": fragments}
    shared = [f for f in files if f.startswith("tools/rooms/shared/")]
    return {"rooms": rooms, "shared_files": len(shared),
            "shared_capabilities": [c["id"] for c in catalog["capabilities"] if c["room"] == "shared"]}


def _caps_cell(rows: list[dict]) -> str:
    l2 = sum(1 for r in rows if r["validation"] == "L2_PASS")
    l1 = sum(1 for r in rows if r["validation"] == "L1_PASS")
    other = len(rows) - l2 - l1
    parts = [f"{l2} L2"] if l2 else []
    parts += [f"{l1} L1"] if l1 else []
    parts += [f"{other} sem prova"] if other else []
    return ", ".join(parts) or "—"


def render_root(data: dict) -> str:
    lines = [BEGIN, "",
             "> Gerado por `python -m tools.navigation.rooms_index --write` (não editar à mão; o teste acusa divergência).",
             "> Detalhe por cômodo: [`tools/rooms/README.md`](tools/rooms/README.md) · handoff por arquivo: "
             "[`docs/reports/file_audit/`](docs/reports/file_audit/README.md).", "",
             "| Cômodo | Pasta | Papel | Capacidades (prova) | Lacunas | Fragmentos | Arquivos (py/rb) |",
             "|---|---|---|---|---|---|---|"]
    for room, r in data["rooms"].items():
        role = ROLE.get(r["role"], r["role"]) + (f" ({r['reuse_of']})" if r["reuse_of"] else "")
        lines.append(f"| {r['title']} | [`tools/rooms/{room}/`](tools/rooms/{room}/) | {role} | {_caps_cell(r['capabilities'])} | "
                     f"{len(r['gaps']) or '—'} | {len(r['fragments']) or '—'} | {r['files']} ({r['python']}/{r['ruby']}) |")
    lines += [f"| Compartilhado | [`tools/rooms/shared/`](tools/rooms/shared/) | peças usadas por ≥ 2 cômodos | "
              f"{len(data['shared_capabilities'])} capacidades | — | — | {data['shared_files']} |", "", END]
    return "\n".join(lines)


def render_detail(data: dict) -> str:
    out = ["# Módulos de cômodo", "",
           "> Gerado por `python -m tools.navigation.rooms_index --write` a partir dos perfis de especialista, do catálogo de",
           "> capacidades e dos arquivos versionados. Não editar à mão.", "",
           "Regras: um dono por comportamento; cômodo não importa outro cômodo; o que dois cômodos usam vai para `shared/`;",
           "capacidade só existe com símbolo + teste (+ prova L2 para `L2_PASS`). Ver `.claude/rules/rooms-and-capabilities.md`.", ""]
    for room, r in data["rooms"].items():
        out += [f"## {r['title']} — `tools/rooms/{room}/`", "",
                f"- **Papel:** {ROLE.get(r['role'], r['role'])}" + (f" — reusa `{r['reuse_of']}`" if r["reuse_of"] else "")
                + f" · estado do perfil `{r['state']}`",
                f"- **Escopo:** {r['scope']}"]
        if r["capabilities"]:
            out.append("- **Capacidades:** " + "; ".join(
                f"`{c['id']}` ({c['validation']}{', shared' if c['shared'] else ''})" for c in r["capabilities"]))
        else:
            out.append("- **Capacidades:** nenhuma própria (não se inventa brain sem capacidade provada)")
        if r["gaps"]:
            out.append("- **Lacunas:** " + "; ".join(f"`{g['binding']}` — {g['gap'][:110]}" for g in r["gaps"]))
        if r["fragments"]:
            out.append("- **Fragmentos do especialista:** " + ", ".join(f"`{f}`" for f in r["fragments"]))
        out.append(f"- **Arquivos ({r['files']}):**")
        for folder, items in r["folders"].items():
            label = "raiz do módulo" if folder == "." else f"`{folder}/`"
            shown = ", ".join(f"`{i.split('/', 1)[1] if folder != '.' else i}`" for i in items)
            out.append(f"  - {label}: {shown}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def splice(readme: str, block: str) -> str:
    if BEGIN in readme and END in readme:
        head, _, rest = readme.partition(BEGIN)
        _, _, tail = rest.partition(END)
        return head + block + tail
    anchor = "## Rodar"
    if anchor not in readme:
        raise ValueError("README sem os marcadores nem a secao '## Rodar' para ancorar o indice")
    return readme.replace(anchor, "## Módulos de cômodo\n\n" + block + "\n\n---\n\n" + anchor, 1)


LAYOUT_BEGIN, LAYOUT_END = "<!-- root-layout:begin -->", "<!-- root-layout:end -->"
# papel de cada entrada versionada da raiz; entrada nova sem linha aqui faz o teste falhar (complementa o guard da FP-044)
ROOT_ROLES = {
    "tools": "código: um módulo por cômodo em `tools/rooms/`, executor SketchUp, gates, navegação, MCP",
    "core": "domínio sem framework: escala, semântica espacial, schemas (`core/schemas/`), observabilidade",
    "interior": "pacote do estúdio de interiores (planners, renderers, validators, class specs) — importado por várias ferramentas",
    "tests": "suíte de regressão (marker `planta74_scale` separa a escala)",
    "docs": "specs SDD (`docs/specs/`), mapa e guias (`docs/architecture/`), relatórios e handoffs datados, arquivo morto",
    "artifacts": "entregáveis canônicos (`artifacts/<planta>/`) e evidência (`artifacts/review/`) — protegidos por hash",
    "fixtures": "entradas canônicas e sintéticas dos testes — protegidas",
    "references": "fontes e recipes de conhecimento (aulas SketchUp, referências de design)",
    "assets": "texturas e recursos reutilizáveis",
    "projects": "fonte de cada projeto (`projects/planta_74/source/planta_74.pdf`)",
    "ops": "painel do estúdio (`ops/estudio-front/`, :8788) — o Harness App aponta para ele; mover exige repontar (D-009)",
    ".claude": "instruções do agente: CLAUDE.md, rules por caminho, skills, agentes, memória",
    ".ai_bridge": "fio entre sessões (`HANDOFF.md`) e logs históricos de revisão/fidelidade",
    ".github": "CI (4 checks obrigatórios)",
    ".impeccable": "config que mantém DESLIGADO o hook de design do plugin impeccable neste projeto (D-008)",
    "README.md": "este arquivo", "CLAUDE.md": "ponteiro para `.claude/CLAUDE.md`",
    "pyproject.toml": "pacote, dependências (`[dev]` inclui ruff/pytest) e config de lint/teste", "uv.lock": "lock das dependências",
    "docker-compose.rag.yml": "Qdrant opcional do RAG (degrada para busca facetada se estiver desligado)",
    ".gitignore": "o que não versiona (`runs/`, scratch, caches)", ".gitattributes": "normalização de fim de linha",
    ".dockerignore": "contexto do build do compose do RAG",
}


def render_layout(root: Path = ROOT) -> str:
    files = subprocess.check_output(["git", "-C", str(root), "ls-files"], text=True).splitlines()
    counts = defaultdict(int)
    for f in files:
        counts[f.split("/")[0]] += 1
    lines = [LAYOUT_BEGIN, "", "> Gerado por `python -m tools.navigation.rooms_index --write`; toda entrada versionada da raiz precisa de papel aqui.",
             "", "| Entrada | Arquivos | Papel |", "|---|---|---|"]
    for entry in sorted(counts, key=lambda e: (not (root / e).is_dir(), e.lower())):
        role = ROOT_ROLES.get(entry, "**SEM PAPEL DEFINIDO** — decidir antes de manter na raiz")
        label = f"`{entry}/`" if (root / entry).is_dir() else f"`{entry}`"
        lines.append(f"| {label} | {counts[entry]} | {role} |")
    lines += ["", "`runs/` existe só localmente (scratch ignorado pelo git).", "", LAYOUT_END]
    return "\n".join(lines)


def splice_layout(readme: str, block: str) -> str:
    if LAYOUT_BEGIN in readme and LAYOUT_END in readme:
        head, _, rest = readme.partition(LAYOUT_BEGIN)
        _, _, tail = rest.partition(LAYOUT_END)
        return head + block + tail
    anchor = "## Módulos de cômodo"
    if anchor not in readme:
        raise ValueError("README sem a secao '## Módulos de cômodo' para ancorar o mapa da raiz")
    return readme.replace(anchor, "## O que mora na raiz\n\n" + block + "\n\n---\n\n" + anchor, 1)


def targets(root: Path = ROOT) -> dict[Path, str]:
    data = collect(root)
    readme = root / "README.md"
    raw = readme.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    new_readme = splice_layout(splice(raw.replace("\r\n", "\n"), render_root(data)), render_layout(root)).replace("\n", nl)
    detail = root / "tools/rooms/README.md"
    return {readme: new_readme, detail: render_detail(data)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    drift = []
    for path, text in targets().items():
        current = path.read_bytes().decode("utf-8") if path.is_file() else None
        if args.write and current != text:
            path.write_bytes(text.encode("utf-8"))
        elif current != text:
            drift.append(str(path.relative_to(ROOT)))
    if drift:
        print("indice de comodos desatualizado: " + ", ".join(drift) + " (rodar --write)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
