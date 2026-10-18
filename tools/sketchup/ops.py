"""Schema das edições de modelo (`su_apply_edits`), validado ANTES do SketchUp.

Validar aqui custa milissegundos; descobrir o erro dentro do lote custa um
SketchUp subindo (~60 s). O Ruby revalida o que só ele sabe (quantas
entidades casam com o alvo, se a definição carregou).

Regras de domínio:
- **Medida é explícita.** `move` exige `by_m` com 3 números. Não existe
  "um pouco para a esquerda" com default — gate verde não valida medida
  inventada (lição do harness-app: "altere a cama" virou move de 10 cm).
- **Arquitetura é do PDF.** Grupos que o builder do shell cria
  (`PROTECTED_PREFIXES`) não aceitam operação GEOMÉTRICA (move/rotate/delete):
  mexer neles é inventar planta (Hard Rule #1). Nem `rename` — renomear tiraria
  o grupo da proteção e liberaria o move seguinte. Aparência (material, tag,
  visibilidade) é permitida.
- Unidade da API é METRO; o Ruby converte (`Numeric#m`). Cor é RGB 0–255.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.sketchup import paths

# Nomes de grupo que `build_plan_shell_skp.rb` cria a partir do consensus.
PROTECTED_PREFIXES = (
    "PlanShell_", "Floor_", "SoftBarrier_", "DoorLeaf_", "Window_",
    "WindowGlass_", "WindowSash_", "GlazedBalcony_", "PassageMarker_",
)
# A laje de teto do banho vem com o nome do cômodo NA FRENTE: o place_layout
# nomeia o grupo "<cômodo> · PeleTeto" (ex. "BANHO 01 · PeleTeto"). Um prefixo
# nunca casaria, então ela é protegida por substring.
PROTECTED_SUBSTRINGS = ("PeleTeto",)
# ops que a arquitetura protegida recusa (geometria + rename, que furaria a proteção)
GUARDED_OPS = frozenset({"move", "rotate", "delete", "rename"})
TARGET_OPS = frozenset({"set_material", "move", "rotate", "set_tag",
                        "set_hidden", "rename", "delete"})
ALL_OPS = TARGET_OPS | {"insert_component"}
MAX_OPS = 200


class OpsInvalid(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _vec3(v: Any) -> bool:
    return isinstance(v, (list, tuple)) and len(v) == 3 and all(_num(x) for x in v)


def is_protected(name: str) -> bool:
    return (any(name.startswith(p) for p in PROTECTED_PREFIXES)
            or any(s in name for s in PROTECTED_SUBSTRINGS))


def protection_params() -> dict[str, list[str]]:
    """O que os jobs Ruby precisam para aplicar a MESMA regra de is_protected."""
    return {"protected_prefixes": list(PROTECTED_PREFIXES),
            "protected_substrings": list(PROTECTED_SUBSTRINGS)}


def _repo_file(p: Any) -> Path | None:
    # Relativo é relativo ao REPO, como o skp_path principal (paths.resolve):
    # contra o CWD do servidor, o mesmo texto recusaria o arquivo certo ou
    # pegaria outro com o mesmo nome.
    return paths.resolve(p) if isinstance(p, str) and p.strip() else None


def _target(op: dict, where: str, errs: list[str]) -> dict | None:
    t = op.get("target")
    if not isinstance(t, dict):
        errs.append(f"{where}: falta target {{name|name_contains|persistent_id}}")
        return None
    keys = [k for k in ("name", "name_contains", "persistent_id") if k in t]
    if len(keys) != 1:
        errs.append(f"{where}: target precisa de exatamente um de name/name_contains/persistent_id")
        return None
    k = keys[0]
    v = t[k]
    if k == "persistent_id" and not (isinstance(v, int) and not isinstance(v, bool) and v > 0):
        errs.append(f"{where}: persistent_id precisa ser inteiro > 0")
        return None
    if k != "persistent_id" and not (isinstance(v, str) and v.strip()):
        errs.append(f"{where}: {k} precisa ser texto não vazio")
        return None
    expect = t.get("expect", "one")
    if expect not in ("one", "all"):
        errs.append(f"{where}: target.expect é 'one' ou 'all'")
        return None
    if op["op"] in GUARDED_OPS and k == "name" and is_protected(v):
        errs.append(f"{where}: '{v}' é arquitetura derivada do PDF — {op['op']} proibido "
                    "(Hard Rule #1); só material/tag/visibilidade")
        return None
    return {k: v, "expect": expect}


def validate(ops: Any, *, exists=lambda p: Path(p).exists()) -> list[dict[str, Any]]:
    """Normaliza a lista de ops ou levanta OpsInvalid com TODOS os erros."""
    if not isinstance(ops, list) or not ops:
        raise OpsInvalid(["ops precisa ser uma lista não vazia"])
    if len(ops) > MAX_OPS:
        raise OpsInvalid([f"no máximo {MAX_OPS} ops por chamada (veio {len(ops)})"])
    errs: list[str] = []
    out: list[dict[str, Any]] = []
    for i, op in enumerate(ops):
        where = f"ops[{i}]"
        if not isinstance(op, dict) or op.get("op") not in ALL_OPS:
            errs.append(f"{where}: op desconhecida {op.get('op') if isinstance(op, dict) else op!r} "
                        f"(válidas: {', '.join(sorted(ALL_OPS))})")
            continue
        kind = op["op"]
        norm: dict[str, Any] = {"op": kind}
        if kind in TARGET_OPS:
            t = _target(op, where, errs)
            if t is None:
                continue
            norm["target"] = t
        n0 = len(errs)
        if kind == "set_material":
            given = [k for k in ("color", "material", "texture") if k in op]
            if len(given) != 1:
                errs.append(f"{where}: set_material precisa de exatamente um de color/material/texture")
            elif given[0] == "color":
                c = op["color"]
                if not (isinstance(c, (list, tuple)) and len(c) == 3
                        and all(isinstance(x, int) and 0 <= x <= 255 for x in c)):
                    errs.append(f"{where}: color é [r,g,b] inteiros 0–255")
                else:
                    norm["color"] = list(c)
            elif given[0] == "material":
                if not (isinstance(op["material"], str) and op["material"].strip()):
                    errs.append(f"{where}: material é o nome de um material do modelo")
                else:
                    norm["material"] = op["material"]
            else:
                tex = _repo_file(op["texture"])
                if not (tex is not None and tex.suffix.lower() in (".png", ".jpg", ".jpeg")
                        and exists(tex)):
                    errs.append(f"{where}: texture precisa ser um .png/.jpg existente")
                else:
                    norm["texture"] = str(tex)
                    size = op.get("texture_size_m", 1.0)
                    if not (_num(size) and size > 0):
                        errs.append(f"{where}: texture_size_m > 0")
                    norm["texture_size_m"] = size
            if "material_name" in op:
                norm["material_name"] = str(op["material_name"])
        elif kind == "move":
            if not _vec3(op.get("by_m")):
                errs.append(f"{where}: move exige by_m [dx,dy,dz] em metros, explícito")
            else:
                norm["by_m"] = list(op["by_m"])
        elif kind == "rotate":
            if not _num(op.get("degrees")):
                errs.append(f"{where}: rotate exige degrees (em torno de Z, no centro do bbox)")
            else:
                norm["degrees"] = op["degrees"]
        elif kind == "set_tag":
            if not (isinstance(op.get("tag"), str) and op["tag"].strip()):
                errs.append(f"{where}: set_tag exige tag (criada se não existir)")
            else:
                norm["tag"] = op["tag"]
        elif kind == "set_hidden":
            if not isinstance(op.get("hidden"), bool):
                errs.append(f"{where}: set_hidden exige hidden true/false")
            else:
                norm["hidden"] = op["hidden"]
        elif kind == "rename":
            if not (isinstance(op.get("name"), str) and op["name"].strip()):
                errs.append(f"{where}: rename exige name")
            elif is_protected(op["name"]):
                errs.append(f"{where}: nome '{op['name']}' é reservado para arquitetura do PDF")
            else:
                norm["name"] = op["name"]
        elif kind == "insert_component":
            p = _repo_file(op.get("skp_path"))
            if not (p is not None and p.suffix.lower() == ".skp" and exists(p)):
                errs.append(f"{where}: insert_component exige skp_path de um .skp existente")
            elif is_protected(p.stem):
                # o SketchUp nomeia a definição pelo nome do arquivo: Window_x.skp
                # viraria "arquitetura do PDF" para a guarda e para o inspect.
                # O CONTEÚDO do arquivo só o Ruby vê (apply_edits.rb).
                errs.append(f"{where}: o arquivo '{p.name}' daria à definição um nome "
                            "reservado para arquitetura do PDF")
            else:
                norm["skp_path"] = str(p)
            if not _vec3(op.get("position_m")):
                errs.append(f"{where}: insert_component exige position_m [x,y,z] em metros")
            else:
                norm["position_m"] = list(op["position_m"])
            rot = op.get("rotation_deg", 0)
            if not _num(rot):
                errs.append(f"{where}: rotation_deg numérico")
            norm["rotation_deg"] = rot
            for k in ("name", "tag"):
                if k in op:
                    if k == "name" and is_protected(str(op[k])):
                        errs.append(f"{where}: nome '{op[k]}' é reservado para arquitetura do PDF")
                    norm[k] = str(op[k])
        if len(errs) == n0:
            out.append(norm)
    if errs:
        raise OpsInvalid(errs)
    return out
