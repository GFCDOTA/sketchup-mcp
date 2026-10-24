"""support_check.py — FP-056 contrato 2: apoio fisico declarado por peca, validado na proposta (caixas) antes do SketchUp.

Modos (spec): FLOOR, ON_SURFACE(<modulo>), WALL_MOUNTED, CEILING, SUSPENDED_INTENTIONAL. Esta fatia cobre FLOOR e
ON_SURFACE; os demais ficam `NOT_EVALUATED` (nao viram PASS). Cada tipo de peca (`kind`) declara o modo em `DECLARED`;
peca sem declaracao e sem folga conhecida e contada em `undeclared` e NAO e deduzida por proximidade.

ON_SURFACE: a face inferior apoiada na face superior do suporte (folga <= EPS_DEPTH) e a projecao dentro do topo do
suporte. Flutuando acima de EPS_DEPTH = FAIL (`gap_m`); abaixo do topo = penetracao, reportada pelo gate de objetos.
O limiar e o mesmo do validador do construido (`penetration.EPS_DEPTH`) — nenhum limiar muda aqui.

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
# kind -> (modo, modulo do suporte). A declaracao e da peca: quem cria o kind declara em que ele se apoia.
DECLARED: dict[str, tuple[str, tuple[str, ...]]] = {
    "kb_bandeja": ("ON_SURFACE", ("Bancada",)),
    "kb_sabonete": ("ON_SURFACE", ("Enxoval:kb_bandeja", "Bancada")),   # sobre a bandeja, ou direto no tampo se nao houver
    "kb_copo": ("ON_SURFACE", ("Enxoval:kb_bandeja", "Bancada")),
}


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
    print(json.dumps(rep, indent=1, ensure_ascii=False))
    return 1 if rep["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
