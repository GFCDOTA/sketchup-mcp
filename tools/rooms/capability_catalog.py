"""FP-043/P5: catalogo unico de capacidades e seu gate de integridade (sem importar builders, sem executar nada).

Liga `source -> recipe -> capability -> simbolo Python/Ruby -> fixture -> teste -> evidencia` com quatro dimensoes
de estado independentes (conhecimento, implementacao, validacao, visual). Registrar uma capacidade NAO autoriza
execucao. O gate reprova: duplicata, simbolo inexistente, source/recipe quebrada, evidencia velha (o codigo do
simbolo mudou depois da prova), ferramenta fora da allowlist do perfil e afirmacao de validacao sem lastro.

Uso: python -m tools.rooms.capability_catalog [--digest <ref> ...]   (sem args: verifica o catalogo)
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "tools/rooms/capability_catalog.v1.json"
SCHEMA_PATH = ROOT / "schemas/capability_catalog.v1.schema.json"
PROFILE_SCHEMA_PATH = ROOT / "schemas/specialist_profile.v1.schema.json"
ROOMS = ("living", "bedroom", "kitchen", "bathroom", "service", "balcony", "closet", "home_office", "circulation")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_catalog(path: Path = CATALOG_PATH) -> dict:
    return _read_json(path)


def _norm_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _module_file(dotted: str, root: Path) -> tuple[Path, list[str]] | None:
    """Maior prefixo do nome pontilhado que e arquivo/pacote; o resto e o caminho do simbolo."""
    parts = dotted.split(".")
    for cut in range(len(parts), 0, -1):
        base = root.joinpath(*parts[:cut])
        for candidate in (base.with_suffix(".py"), base / "__init__.py"):
            if candidate.is_file():
                return candidate, parts[cut:]
    return None


def _find_node(tree: ast.AST, path: list[str]):
    nodes = tree.body if hasattr(tree, "body") else []
    node = None
    for name in path:
        node = next((n for n in nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and n.name == name), None)
        if node is None:
            # constante de modulo (X = ...)
            for n in nodes:
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
                    return n
            return None
        nodes = node.body
    return node


def symbol_digest(symbol: dict, root: Path = ROOT) -> str | None:
    """sha256 do codigo do simbolo. Python: AST do no (ignora comentario/formatacao); Ruby: texto normalizado do arquivo.
    None = simbolo inexistente."""
    lang, ref = symbol["lang"], symbol["ref"]
    if lang == "ruby":
        path = root / ref
        if not path.is_file():
            return None
        return hashlib.sha256(_norm_text(path.read_text(encoding="utf-8")).encode("utf-8")).hexdigest()
    found = _module_file(ref, root)
    if found is None or not found[1]:
        return None
    file, rest = found
    node = _find_node(ast.parse(file.read_text(encoding="utf-8")), rest)
    if node is None:
        return None
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode("utf-8")).hexdigest()


def _tool_symbol(tool: str) -> dict | None:
    kind, _, ref = tool.partition(":")
    return {"lang": kind, "ref": ref} if kind in ("python", "ruby") else None


def verify(catalog: dict | None = None, profiles: dict[str, dict] | None = None, root: Path = ROOT) -> dict:
    """Gate de integridade. `profiles` = {room: perfil}; default: carrega os perfis do repo."""
    from jsonschema import Draft202012Validator

    errors: dict[str, list[str]] = {}

    def flag(code: str, what: str) -> None:
        errors.setdefault(code, []).append(what)

    catalog = catalog if catalog is not None else load_catalog(root / "tools/rooms/capability_catalog.v1.json")
    schema = _read_json(root / "schemas/capability_catalog.v1.schema.json")
    for err in sorted(Draft202012Validator(schema).iter_errors(catalog), key=lambda e: list(e.path)):
        flag("SCHEMA", f"{'/'.join(str(p) for p in err.path)}: {err.message[:120]}")
    if errors:
        return {"result": "FAIL", "errors": errors}

    # --- conhecimento: ids de recipe e source ---
    video = _read_json(root / catalog["knowledge_catalogs"]["video"])
    env = _read_json(root / catalog["knowledge_catalogs"]["environment"])
    recipe_ids = {r["id"] for r in video["recipes"]} | {r["id"] for r in env["recipes"]}
    source_ids = {s["id"] for s in video["sources"]} | {s["id"] for s in env["sources"]}

    caps = catalog["capabilities"]
    cap_ids = [c["id"] for c in caps]
    for dup in sorted({i for i in cap_ids if cap_ids.count(i) > 1}):
        flag("DUPLICATE_CAPABILITY_ID", dup)
    bind_ids = [b["id"] for b in catalog["bindings"]]
    for dup in sorted({i for i in bind_ids if bind_ids.count(i) > 1}):
        flag("DUPLICATE_BINDING_ID", dup)
    by_id = {c["id"]: c for c in caps}

    if profiles is None:
        profiles = {}
        for room in ROOMS:
            p = root / "tools/rooms" / room / "specialist.v1.json"
            if p.is_file():
                profiles[room] = _read_json(p)
    allowlists = {room: set(p.get("tool_allowlist", [])) for room, p in profiles.items()}

    for b in catalog["bindings"]:
        for rid in b["recipe_ids"]:
            if rid not in recipe_ids:
                flag("RECIPE_NOT_FOUND", f"{b['id']}: {rid}")
        for sid in b["source_ids"]:
            if sid not in source_ids:
                flag("SOURCE_NOT_FOUND", f"{b['id']}: {sid}")
        if b["capability_id"] is None:
            if not (b.get("gap") or "").strip():
                flag("ABSENT_CAPABILITY_WITHOUT_GAP", b["id"])
        elif b["capability_id"] not in by_id:
            flag("CAPABILITY_NOT_FOUND", f"{b['id']}: {b['capability_id']}")
        elif by_id[b["capability_id"]]["room"] != b["room"] and by_id[b["capability_id"]]["room"] != "shared":
            flag("BINDING_ROOM_MISMATCH", b["id"])

    for c in caps:
        cid, impl, val = c["id"], c["implementation"], c["validation"]
        # --- implementacao x simbolo ---
        if impl["state"] == "IMPLEMENTED" and not impl["symbols"]:
            flag("IMPLEMENTED_WITHOUT_SYMBOL", cid)
        for s in impl["symbols"]:
            if impl["state"] != "RETIRED" and symbol_digest(s, root) is None:
                flag("SYMBOL_MISSING", f"{cid}: {s['lang']}:{s['ref']}")
        if impl["state"] in ("PLANNED", "RETIRED") and val["state"] in ("L1_PASS", "L2_PASS"):
            flag("VALIDATION_CLAIM_WITHOUT_IMPLEMENTATION", cid)
        # --- validacao x lastro ---
        if val["state"] in ("L1_PASS", "L2_PASS"):
            if not val["tests"]:
                flag("VALIDATION_WITHOUT_TEST", cid)
            for ref in val["tests"] + val["fixtures"]:
                if not (root / ref).exists():
                    flag("FIXTURE_OR_TEST_MISSING", f"{cid}: {ref}")
        if val["state"] == "L2_PASS" and not val["evidence"]:
            flag("L2_WITHOUT_EVIDENCE", cid)
        for ev in val["evidence"]:
            if not (root / ev["ref"]).exists():
                flag("EVIDENCE_FILE_MISSING", f"{cid}: {ev['ref']}")
            declared = {(s["lang"], s["ref"]): s for s in impl["symbols"]}
            for key, digest in ev["symbol_digests"].items():
                lang, _, ref = key.partition(":")
                sym = {"lang": lang, "ref": ref}
                if (lang, ref) not in declared:
                    flag("EVIDENCE_FOR_UNDECLARED_SYMBOL", f"{cid}: {key}")
                    continue
                now = symbol_digest(sym, root)
                if now is not None and now != digest:
                    flag("EVIDENCE_STALE", f"{cid}: {key} mudou depois da prova")
        if val["state"] == "L2_PASS":
            proved = {k for ev in val["evidence"] for k in ev["symbol_digests"]}
            for s in impl["symbols"]:
                if f"{s['lang']}:{s['ref']}" not in proved:
                    flag("L2_SYMBOL_WITHOUT_PROOF", f"{cid}: {s['lang']}:{s['ref']}")
        # --- ferramenta x allowlist do perfil ---
        room_list = [c["room"]] if c["room"] != "shared" else list(allowlists)
        if c["room"] in allowlists or c["room"] == "shared":
            for t in c["tools"]:
                owners = [r for r in room_list if t in allowlists.get(r, set())]
                if not owners:
                    flag("TOOL_NOT_ALLOWLISTED", f"{cid}: {t}")
        else:
            flag("CAPABILITY_ROOM_WITHOUT_PROFILE", f"{cid}: {c['room']}")
    return {"result": "FAIL" if errors else "PASS", "errors": errors,
            "capabilities": len(caps), "bindings": len(catalog["bindings"]),
            "proof": "CATALOGO_INTEGRO_NAO_PROVA_GEOMETRIA_NEM_L2_NOVO"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gate do catalogo de capacidades FP-043/P5")
    ap.add_argument("--digest", nargs="*", metavar="LANG:REF", help="imprime o sha256 de simbolos (para registrar prova)")
    ns = ap.parse_args(argv)
    if ns.digest:
        for item in ns.digest:
            lang, _, ref = item.partition(":")
            print(item, symbol_digest({"lang": lang, "ref": ref}))
        return 0
    res = verify()
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0 if res["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
