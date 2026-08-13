"""furniture_overlap_gate.py — gate DETERMINISTICO de COLISAO: pega "móvel em cima de
móvel" (sobreposição real), o defeito que o Felipe nomeou. O geometry_sanity só cuida
de fora-do-cômodo/bloqueia-porta; ESTE cuida de dois móveis ocupando o mesmo espaço.

Critério: dois MÓDULOS diferentes colidem se a footprint (planta) se cruza E as faixas
de ALTURA se cruzam. Considera Z -> prateleira (z alto) sobre o rack (z baixo) NÃO é
colisão; sofá e mesa no mesmo nível com footprint sobreposta É. Tapete (forro) e parede
ficam de fora (tudo pousa sobre tapete; parede é parede).

Uso: PT_TO_M=0.0259 [FURNISH_STYLE=industrial] python -m tools.furniture_overlap_gate [room_id|all]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

M2IN = 39.3700787402
Z_EPS_IN = 2.0 / 2.54 * 1.0          # ~2cm de folga vertical p/ considerar "mesmo nível"
AREA_MIN_M2 = 0.04                   # cruzamento menor que isso = roçar, ignora
FRAC_MIN = 0.12                      # E >=12% da área do menor módulo
FRAC_FAIL = 0.30                     # >=30% do menor módulo = FAIL (abaixo, WARN)
# módulos que legitimamente se sobrepõem a tudo (não são "móvel sobre móvel")
# "pele"/"peleteto" (bathroom_layout.py): revestimento fino de parede/piso/teto —
# mesma categoria de "parede"/"piso", achado 2026-08-12 (faltava aqui e gerava
# FAIL sistemático em todo banheiro: bancada/box/enxoval/vaso "colidindo" com o
# próprio revestimento da parede que encostam, não com outro móvel de verdade).
EXCLUDE = ("tapete", "rug", "parede", "piso", "floor", "pele")
# embutidos LEGÍTIMOS na cozinha: eletro/cuba (cooktop/pia/cuba) DENTRO da bancada
# (base_cabinet + countertop). Counter sobre cabinet idem (mesma unidade física).
_FIX = ("cooktop", "sink", "pia", "cuba")
_HOST = ("bancada", "countertop", "base_cabinet")


# trim de acabamento: filler/coifa-slim legitimamente encostam em módulos vizinhos
_TRIM = ("filler", "hood", "coifa", "decor", "led", "ralo")


def _is_embedded(a, b):
    a, b = a.lower(), b.lower()
    if any(t in a for t in _TRIM) or any(t in b for t in _TRIM):
        return True
    fa, fb = any(f in a for f in _FIX), any(f in b for f in _FIX)
    ha, hb = any(h in a for h in _HOST), any(h in b for h in _HOST)
    return (fa and hb) or (fb and ha) or (ha and hb)


def _module_geom(boxes):
    """module -> (footprint Polygon unida, z0_in, z1_in, host_kinds set).

    achado 2026-08-12 (consulta GPT-Docker): EXCLUDE/_FIX/_HOST/_TRIM eram
    substring matching de module/kind, cada gate reinventando a mesma
    pergunta. Migração ADITIVA (não substitui, soma): interaction_policy.
    furniture_overlap (core/spatial_semantics.py) e' o sinal NOVO — qualquer
    box com furniture_overlap!='EXCLUSIVE' já não entra na footprint do
    módulo (nem pisável tipo tapete, nem decorativo, nem HOSTED tipo cuba
    embutida). O substring antigo continua rodando em paralelo em
    pairwise_overlap (não removido ainda — retirar só depois que todo
    builder declarar geometry_intent explícito, ver semantic_geometry_
    contract_gate)."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from core.spatial_semantics import annotate
    polys = defaultdict(list)
    zr = defaultdict(lambda: [9e9, -9e9])
    host_kinds = defaultdict(set)
    for b in boxes:
        if not b.get("corners"):
            continue
        annotate(b)
        pol = (b.get("interaction_policy") or {}).get("furniture_overlap", "EXCLUSIVE")
        if pol != "EXCLUSIVE":
            continue
        # tapete/piso pisável NÃO conta pra colisão mesmo dentro de um módulo
        # maior (achado 2026-08-12: "kb_tapete" agrupado sob module="Enxoval"
        # inflava a footprint do módulo inteiro com área de tapete, gerando
        # "Enxoval × Vaso" FAIL falso — legado, mantido em paralelo ao check
        # de interaction_policy acima).
        if any(e in str(b.get("kind", "")).lower() for e in ("tapete", "rug")):
            continue
        mod = str(b.get("module", b.get("kind", "movel")))
        try:
            polys[mod].append(Polygon([(c[0], c[1]) for c in b["corners"]]).buffer(0))
        except Exception:  # noqa: BLE001
            continue
        z0 = float(b.get("z0_in", 0.0))
        zr[mod][0] = min(zr[mod][0], z0)
        zr[mod][1] = max(zr[mod][1], z0 + float(b.get("h_in", 0.0)))
        host = b.get("host") or {}
        if host.get("relationship", "NONE") != "NONE" and host.get("host_kind_hint"):
            host_kinds[mod].add(host["host_kind_hint"])
    out = {}
    for mod, ps in polys.items():
        out[mod] = (unary_union(ps), zr[mod][0], zr[mod][1], host_kinds.get(mod, set()))
    return out


def iter_overlap_pairs(geoms):
    """Núcleo CANÔNICO ÚNICO do pairwise loop — geoms: module -> (footprint,
    z0_in, z1_in, host_kinds) (saída de _module_geom). Aplica EXCLUDE,
    _is_embedded/host relationship e os thresholds Z_EPS_IN/AREA_MIN_M2/FRAC_MIN
    — quem quiser resultado por par (correction_fixes.py, nudge) OU só o
    veredito PASS/WARN/FAIL (pairwise_overlap, abaixo) consome ISTO, nunca
    reimplementa o loop (achado 2026-08-12: correction_fixes.py tinha cópia
    própria do MESMO loop, quebrou silenciosamente quando _module_geom mudou
    de forma — exatamente o anti-padrão "duplicated policy" que motivou o
    optimizer_consistency_gate). Yields (mod_a, mod_b, inter_m2, frac)."""
    geoms = {m: g for m, g in geoms.items()
             if not any(e in m.lower() for e in EXCLUDE)}
    mods = sorted(geoms)
    for i in range(len(mods)):
        for j in range(i + 1, len(mods)):
            if _is_embedded(mods[i], mods[j]):   # eletro/cuba embutido na bancada+tampo: legítimo
                continue
            pa, za0, za1, hosts_a = geoms[mods[i]]
            pb, zb0, zb1, hosts_b = geoms[mods[j]]
            # host relationship declarado (core/spatial_semantics.py) — mesmo
            # espírito de _is_embedded, mas via contrato explícito em vez de
            # substring; roda em PARALELO (OR), não substitui ainda.
            if (any(h in mods[j].lower() for h in hosts_a)
                    or any(h in mods[i].lower() for h in hosts_b)):
                continue
            z_ov = min(za1, zb1) - max(za0, zb0)
            if z_ov <= Z_EPS_IN:                       # alturas não se cruzam -> ok (empilhado)
                continue
            inter = pa.intersection(pb).area / (M2IN * M2IN)   # m²
            if inter < AREA_MIN_M2:
                continue
            amin = min(pa.area, pb.area) / (M2IN * M2IN)
            frac = inter / amin if amin else 0.0
            if frac >= FRAC_MIN:
                yield mods[i], mods[j], inter, frac


def pairwise_overlap(geoms):
    """Loop pairwise CANÔNICO de colisão — ver iter_overlap_pairs(). Devolve
    (fails, warns, n_modules): fails/warns são a mesma checagem, só formatada
    como PASS/WARN/FAIL (frac >= FRAC_FAIL = FAIL, senão WARN)."""
    fails, warns = [], []
    n_modules = len({m for m, g in geoms.items() if not any(e in m.lower() for e in EXCLUDE)})
    for mod_a, mod_b, inter, frac in iter_overlap_pairs(geoms):
        msg = f"{mod_a} × {mod_b}: {inter*10000:.0f} cm² sobrepostos ({frac:.0%} do menor)"
        (fails if frac >= FRAC_FAIL else warns).append(msg)
    return fails, warns, n_modules


def overlap_gate(con, room_id):
    os.environ.setdefault("PT_TO_M", "0.0259")
    from tools.furnish_apartment import BRAINS
    from tools.room_type import classify_rooms
    r = {x["id"]: x for x in classify_rooms(con)}.get(room_id)
    if not r:
        return {"result": "FAIL", "room": room_id, "fails": ["cômodo inexistente"], "warns": []}
    brain = BRAINS.get(r["room_type"])
    boxes, _ = brain(con, room_id) if brain else ([], {})
    fails, warns, n_modules = pairwise_overlap(_module_geom(boxes or {}))
    result = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"result": result, "room": room_id, "room_name": r["name"],
            "n_modules": n_modules, "fails": fails, "warns": warns}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("room", nargs="?", default="all")
    a = ap.parse_args()
    from tools.furnish_apartment import CONSENSUS
    from tools.room_type import classify_rooms
    con = json.loads(CONSENSUS.read_text("utf-8"))
    rooms = ([a.room] if a.room != "all"
             else [r["id"] for r in classify_rooms(con)])
    worst = "PASS"
    for rid in rooms:
        res = overlap_gate(con, rid)
        if res["result"] == "FAIL":
            worst = "FAIL"
        elif res["result"] == "WARN" and worst != "FAIL":
            worst = "WARN"
        tag = {"PASS": "ok", "WARN": "warn", "FAIL": "FAIL"}[res["result"]]
        print(f"[{tag:4}] {res.get('room_name', rid)} ({res['n_modules']} móveis)")
        for m in res["fails"] + res["warns"]:
            print(f"        {m}")
    print(f"\noverlap_gate => {worst}")
    sys.exit(1 if worst == "FAIL" else 0)


if __name__ == "__main__":
    main()
