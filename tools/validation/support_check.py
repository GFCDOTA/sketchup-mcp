"""support_check.py — FP-056 contrato 2: apoio fisico declarado por peca, validado na proposta (caixas) antes do SketchUp.

Modos (spec): FLOOR, ON_SURFACE(<modulo>), WALL_MOUNTED, CEILING, SUSPENDED_INTENTIONAL. Esta fatia cobre FLOOR e
ON_SURFACE; os demais ficam `NOT_EVALUATED` (nao viram PASS). Cada tipo de peca (`kind`) declara o modo em `DECLARED`;
peca sem declaracao e sem folga conhecida e contada em `undeclared` e NAO e deduzida por proximidade.

ON_SURFACE: a face inferior apoiada na face superior do suporte (folga <= EPS_DEPTH) e a projecao dentro do topo do
suporte. Flutuando acima de EPS_DEPTH = FAIL (`gap_m`); abaixo do topo = penetracao, reportada pelo gate de objetos.
O limiar e o mesmo do validador do construido (`penetration.EPS_DEPTH`) — nenhum limiar muda aqui.

Nivel MODULO (P4b): `MODULE_SUPPORT` declara o modo de cada modulo (grupo do .skp). FLOOR: o ponto mais baixo do modulo
a no maximo EPS_DEPTH do piso. WALL_MOUNTED: a pegada do modulo toca a massa de parede (distancia <= EPS_DEPTH) — a folga
real aparece como `NOT_IN_CONTACT`. CEILING: o topo do modulo encosta no teto (`CEILING_Z_M`, a altura do shell: `WALL_HEIGHT_M` do build_plan_shell_skp.rb) a
no maximo EPS_DEPTH; senao `NOT_AT_CEILING` com a folga medida. SUSPENDED_INTENTIONAL: o modulo so e valido se alguma peca
dele (cabo/haste) chega ao teto: sem esse caminho ate o teto, `NOT_CONNECTED` (suspenso sem fixacao modelada).
Modulo sem declaracao vai para `undeclared` (BLOCKED na spec): nunca deduzido por proximidade.

Uso:  PT_TO_M=0.0259 python -m tools.validation.support_check   (relatorio da planta_74)
"""
from __future__ import annotations

import contextlib
import io
import json
import sys

from shapely.geometry import Polygon
from shapely.ops import unary_union

from tools.validation.penetration import EPS_DEPTH

IN2M = 0.0254
CEILING_Z_M = 2.70    # altura do shell (laje de teto): `WALL_HEIGHT_M` de tools/sketchup/shell/build_plan_shell_skp.rb (contrato testado)
# kind -> (modo, modulo do suporte). A declaracao e da peca: quem cria o kind declara em que ele se apoia.
DECLARED: dict[str, tuple[str, tuple[str, ...]]] = {
    "kb_bandeja": ("ON_SURFACE", ("Bancada",)),
    "kb_sabonete": ("ON_SURFACE", ("Enxoval:kb_bandeja", "Bancada")),   # sobre a bandeja, ou direto no tampo se nao houver
    "kb_copo": ("ON_SURFACE", ("Enxoval:kb_bandeja", "Bancada")),
}


FLOOR_MODULES = ("Armario de servico", "Cadeira jantar", "Cama", "Churrasqueira", "Escrivaninha", "Guarda-roupa", "Jardineira",
                 "Maquina de lavar", "Mesa de jantar", "Rack TV", "Sofa", "Tanque", "Tapete", "base_cabinet_01", "rug")
WALL_MODULES = ("Coifa", "hood", "upper_cabinet_01", "upper_cabinet_02", "Espelho", "Prateleira servico", "backsplash",
                "Painel cabeceira", "Painel TV")
CEILING_MODULES = ("PeleTeto", "Varal de teto")
SUSPENDED_MODULES = ("Pendente",)
MODULE_SUPPORT: dict[str, str] = {**{m: "FLOOR" for m in FLOOR_MODULES}, **{m: "WALL_MOUNTED" for m in WALL_MODULES},
                                  **{m: "CEILING" for m in CEILING_MODULES},
                                  **{m: "SUSPENDED_INTENTIONAL" for m in SUSPENDED_MODULES}}


def check_modules(boxes: list[dict], con: dict) -> dict:
    """Apoio por MODULO. {'findings': [...], 'evaluated': n, 'not_evaluated': [...], 'undeclared': [...]}."""
    from core.scale import PT_TO_IN, PT_TO_M
    from tools.rooms.shared.clearance import box_footprint_pt, wall_mass_pt
    walls = wall_mass_pt(con)
    mods: dict[tuple[str, str], list[dict]] = {}
    for b in boxes:
        if b.get("corners") and b.get("room") and b.get("module"):
            mods.setdefault((b["room"], b["module"]), []).append(b)
    findings, evaluated, not_eval, undeclared = [], 0, [], []
    for (room, name), parts in sorted(mods.items()):
        mode = MODULE_SUPPORT.get(name)
        if mode is None:
            undeclared.append(f"{room} · {name}")
            continue
        evaluated += 1
        if mode in ("CEILING", "SUSPENDED_INTENTIONAL"):
            top = max(_z(b)[1] for b in parts)
            gap = CEILING_Z_M - top
            if gap > EPS_DEPTH:
                code = "NOT_AT_CEILING" if mode == "CEILING" else "NOT_CONNECTED"
                what = "topo" if mode == "CEILING" else "ponto mais alto (cabo/haste)"
                findings.append({"check": "SUPPORT", "module": name, "room": room, "code": code, "gap_m": round(gap, 4),
                                 "detail": f"{what} a {gap * 100:.1f} cm do teto ({CEILING_Z_M:.2f} m)"})
            continue
        if mode == "FLOOR":
            gap = min(_z(b)[0] for b in parts)
            if gap > EPS_DEPTH:
                findings.append({"check": "SUPPORT", "module": name, "room": room, "code": "NOT_ON_FLOOR", "gap_m": round(gap, 4),
                                 "detail": f"ponto mais baixo {gap * 100:.1f} cm acima do piso"})
        else:  # WALL_MOUNTED: o hospedeiro e a parede ou a pele de parede (modulo `Pele`) do mesmo comodo
            skins = [box_footprint_pt(k, PT_TO_IN) for k in mods.get((room, "Pele"), [])]
            host = unary_union([walls, *[f for f in skins if f is not None]])
            dist = min(box_footprint_pt(b, PT_TO_IN).distance(host) for b in parts if box_footprint_pt(b, PT_TO_IN) is not None) * PT_TO_M
            if dist > EPS_DEPTH:
                findings.append({"check": "SUPPORT", "module": name, "room": room, "code": "NOT_IN_CONTACT", "gap_m": round(dist, 4),
                                 "detail": f"a {dist * 100:.1f} cm da parede"})
    return {"findings": findings, "evaluated": evaluated, "not_evaluated": not_eval, "undeclared": undeclared}


def _poly(b: dict) -> Polygon:
    return Polygon([(x * IN2M, y * IN2M) for x, y in b["corners"]])


def _z(b: dict) -> tuple[float, float]:
    z0 = float(b.get("z0_in") or 0.0) * IN2M
    return z0, z0 + float(b.get("h_in") or 0.0) * IN2M


def _supports(boxes: list[dict], room: str, spec: str) -> list[dict]:
    module, _, kind = spec.partition(":")
    return [s for s in boxes if s.get("room") == room and s.get("module") == module and (not kind or s.get("kind") == kind)]


def check_support(boxes: list[dict]) -> dict:
    """{'findings': [...], 'checked': n, 'undeclared': n}. Um achado por peca declarada que nao se apoia."""
    findings, checked = [], 0
    for b in boxes:
        decl = DECLARED.get(b.get("kind") or "")
        if not decl or not b.get("corners") or not b.get("room"):
            continue
        mode, spec = decl
        z0, _ = _z(b)
        checked += 1
        if mode != "ON_SURFACE":
            continue
        foot = _poly(b)
        under = [s for sp in spec for s in _supports(boxes, b["room"], sp) if s is not b and _poly(s).intersects(foot)]
        if not under:
            findings.append({"check": "SUPPORT", "module": f"{b['module']} {b['kind']}", "room": b["room"], "code": "NO_SUPPORT",
                             "gap_m": None, "detail": f"nenhum de {list(spec)} sob a pegada"})
            continue
        top = max(_z(s)[1] for s in under)
        gap = z0 - top
        covered = foot.difference(unary_union([_poly(s) for s in under])).area < 1e-6
        if gap > EPS_DEPTH:
            findings.append({"check": "SUPPORT", "module": f"{b['module']} {b['kind']}", "room": b["room"], "code": "FLOATING",
                             "gap_m": round(gap, 4), "detail": f"base {gap * 100:.1f} cm acima do suporte declarado"})
        elif not covered:
            findings.append({"check": "SUPPORT", "module": f"{b['module']} {b['kind']}", "room": b["room"], "code": "OVERHANG",
                             "gap_m": round(gap, 4), "detail": "projecao fora do topo do suporte"})
    kinds = {b.get("kind") for b in boxes if b.get("room")}
    return {"findings": findings, "checked": checked, "declared_kinds": sorted(kinds & set(DECLARED))}


def main() -> int:
    from tools.furnish_apartment import collect_boxes
    from tools.rooms.shared.project_paths import PLANTA_74_CONSENSUS
    con = json.loads(PLANTA_74_CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
    rep = check_support(boxes)
    rep["modules"] = check_modules(boxes, con)
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    return 1 if rep["findings"] or rep["modules"]["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
