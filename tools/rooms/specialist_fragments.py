"""Fragmentos de especialista: sub-topicos de um comodo tratados mais a fundo, como PONTEIROS validados.

Cada `tools/rooms/<comodo>/fragments/<id>.fragment.v1.json` (contrato `specialist_fragment.v1`) diz qual parte do comodo ele
responde — capacidades e bindings (inclusive lacunas), recipes, specs, codigo, testes, skills, alvos FP-052, golden e demos
FP-053 — sem copiar conteudo e sem conceder execucao (quem decide execucao continua sendo `specialists.plan`).

Gate (`verify`), fail-closed:
  - schema; nome do arquivo = id; `room` = pasta;
  - capacidade do fragmento pertence ao perfil do comodo; cada capacidade do perfil tem EXATAMENTE um fragmento dono;
  - binding existe, e do comodo, e cada binding do comodo tem exatamente um fragmento; a capacidade do binding esta no mesmo fragmento;
  - recipe pertence ao perfil do comodo; caminho citado (spec, codigo, teste, alvo, golden, demo) existe; skill existe.

    python -m tools.rooms.specialist_fragments                 # verifica todos
    python -m tools.rooms.specialist_fragments --for kitchen.cabinet.shaker-door
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from core.schemas import schema_path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "specialist_fragment.v1.schema.json"
PATH_FIELDS = ("specs", "code", "tests", "reference_targets", "golden_sources", "demos")


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fragment_paths(root: Path = ROOT, room: str | None = None) -> list[Path]:
    pattern = f"{room}/fragments/*.fragment.v1.json" if room else "*/fragments/*.fragment.v1.json"
    return sorted((root / "tools/rooms").glob(pattern))


def load_fragments(root: Path = ROOT, room: str | None = None) -> list[dict]:
    return [_read(p) for p in fragment_paths(root, room)]


def owner_of(capability_or_binding: str, root: Path = ROOT) -> list[dict]:
    """Fragmentos que respondem por uma capacidade ou binding (um por comodo que a usa)."""
    return [f for f in load_fragments(root)
            if capability_or_binding in f["capability_ids"] or capability_or_binding in f["binding_ids"]]


def verify(root: Path = ROOT, fragments: list[tuple[Path, dict]] | None = None) -> dict:
    from jsonschema import Draft202012Validator

    errors: dict[str, list[str]] = defaultdict(list)
    validator = Draft202012Validator(_read(schema_path(SCHEMA, root)))
    catalog = _read(root / "tools/rooms/capability_catalog.v1.json")
    bindings = {b["id"]: b for b in catalog["bindings"]}
    if fragments is None:
        fragments = [(p, _read(p)) for p in fragment_paths(root)]
    profiles: dict[str, dict] = {}
    cap_owner: dict[tuple[str, str], list[str]] = defaultdict(list)
    bind_owner: dict[tuple[str, str], list[str]] = defaultdict(list)
    rooms_seen = set()

    for path, frag in fragments:
        where = path.relative_to(root).as_posix() if path.is_absolute() else str(path)
        for err in validator.iter_errors(frag):
            errors["SCHEMA"].append(f"{where}: {'/'.join(map(str, err.path))}: {err.message[:100]}")
        if errors.get("SCHEMA") and any(e.startswith(where) for e in errors["SCHEMA"]):
            continue
        room, fid = frag["room"], frag["id"]
        rooms_seen.add(room)
        if path.name != f"{fid}.fragment.v1.json" or path.parent.parent.name != room:
            errors["FRAGMENT_PATH_MISMATCH"].append(f"{where}: id/room nao batem com o caminho")
        if room not in profiles:
            profiles[room] = _read(root / "tools/rooms" / room / "specialist.v1.json")
        profile = profiles[room]
        for cid in frag["capability_ids"]:
            if cid not in profile["capability_ids"]:
                errors["CAPABILITY_NOT_IN_PROFILE"].append(f"{room}/{fid}: {cid}")
            cap_owner[(room, cid)].append(fid)
        for bid in frag["binding_ids"]:
            b = bindings.get(bid)
            if b is None:
                errors["BINDING_NOT_FOUND"].append(f"{room}/{fid}: {bid}")
                continue
            if b["room"] != room:
                errors["BINDING_OF_OTHER_ROOM"].append(f"{room}/{fid}: {bid} e de {b['room']}")
            if b["capability_id"] and b["capability_id"] not in frag["capability_ids"]:
                errors["BINDING_CAPABILITY_ELSEWHERE"].append(f"{room}/{fid}: {bid} -> {b['capability_id']} fora do fragmento")
            bind_owner[(room, bid)].append(fid)
        for rid in frag["recipe_ids"]:
            if rid not in profile.get("recipe_ids", []):
                errors["RECIPE_NOT_IN_PROFILE"].append(f"{room}/{fid}: {rid}")
        for field in PATH_FIELDS:
            for ref in frag[field]:
                if not (root / ref).exists():
                    errors["PATH_MISSING"].append(f"{room}/{fid}: {field}: {ref}")
        for skill in frag["skills"]:
            if not (root / ".claude/skills" / skill / "SKILL.md").is_file():
                errors["SKILL_MISSING"].append(f"{room}/{fid}: {skill}")

    for room in sorted(rooms_seen):
        for cid in profiles[room]["capability_ids"]:
            owners = cap_owner.get((room, cid), [])
            if len(owners) != 1:
                errors["CAPABILITY_OWNERSHIP"].append(f"{room}: {cid} em {owners or 'nenhum fragmento'}")
        for bid, b in bindings.items():
            if b["room"] == room and len(bind_owner.get((room, bid), [])) != 1:
                errors["BINDING_OWNERSHIP"].append(f"{room}: {bid} em {bind_owner.get((room, bid)) or 'nenhum fragmento'}")
    return {"result": "FAIL" if errors else "PASS", "errors": dict(errors), "fragments": len(fragments),
            "rooms": sorted(rooms_seen), "proof": "PONTEIROS_VALIDOS_NAO_AUTORIZA_EXECUCAO"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--for", dest="target", help="capacidade ou binding: mostra o(s) fragmento(s) dono(s)")
    args = ap.parse_args(argv)
    if args.target:
        rows = [{"room": f["room"], "fragment": f["id"], "title": f["title"]} for f in owner_of(args.target)]
        print(json.dumps(rows, indent=1, ensure_ascii=False))
        return 0 if rows else 1
    res = verify()
    print(json.dumps(res, indent=1, ensure_ascii=False))
    return 0 if res["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
