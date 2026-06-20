"""interior_quality_scorecard.py — INTERIOR_QUALITY_SYSTEM.

Além de "não está errado" (geometry_sanity + furniture_overlap_gate), mede "está BOM" — a
camada de COMPOSIÇÃO que faltava. A sala provou: rack proxy + sem jantar passa nos gates
geométricos mas é pobre. Aqui ficam os gates novos + um scorecard por cômodo.

Regra: NÃO propagar linguagem (black_wood_gold) em cima de layout ruim. Ordem obrigatória:
layout/ancoragem/circulação -> mobiliário -> linguagem -> V-Ray.

Gates:
  furniture_wall_anchor_gate   — rack/guarda-roupa/torre flush em parede (peça de centro isenta)
  room_zone_gate               — o cômodo tem as zonas que o tipo exige (estar+jantar, cama+roupa)
  furniture_quality_gate       — módulo que deveria ser detalhado não pode ser cubo proxy (parts<MIN)
  planned_niche_candidate_gate — objeto solto/proxy que deveria virar sistema planejado
  golden_sample_style_gate     — paleta/material coerente com GOLDEN_SAMPLE_004 (placeholder p/ tema)

PASS = pronto pra seguir · WARN = bom, precisa polish · FAIL = não aplicar estética ainda.
Uso: PT_TO_M=0.0259 python -m tools.interior_quality_scorecard [room_id|all]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IN_PER_M = 39.3700787402

# tipos que PRECISAM encostar em parede (back contra parede)
ANCHOR_TYPES = ("rack", "tv", "guarda-roupa", "wardrobe", "dresser", "aparador", "buffet",
                "estante", "cama", "bed", "criado", "nightstand", "bancada", "geladeira",
                "torre", "fridge", "cabinet", "armario", "aereo")
# peças de CENTRO (isentas de ancoragem — devem ficar no meio)
CENTER_TYPES = ("mesa de centro", "coffee", "centro", "tapete", "rug", "ilha", "island",
                "mesa de jantar", "dining", "pendente", "lustre")
# módulos que deveriam ser DETALHADOS (parts >= DETAIL_MIN); proxy = cubo
DETAIL_REQUIRED = ("rack", "sofa", "cama", "bed", "guarda-roupa", "wardrobe", "mesa de jantar",
                   "dining", "aparador", "buffet", "estante")
DETAIL_MIN = 3
ANCHOR_FLUSH_CM = 8.0     # <=8cm = flush
ANCHOR_WARN_CM = 22.0     # <=22cm = aceitável; acima = flutuando

# zonas exigidas por tipo de cômodo (substrings de módulo)
ROOM_ZONES = {
    "LIVING": {"estar (sofá)": ("sofa",), "jantar (mesa)": ("mesa de jantar", "dining")},
    "BEDROOM": {"dormir (cama)": ("cama", "bed"), "guardar (roupa)": ("guarda-roupa", "wardrobe")},
    "KITCHEN": {"preparo (bancada)": ("bancada", "countertop", "base_cabinet"),
                "cocção (cooktop)": ("cooktop", "cook"), "lavar (pia)": ("pia", "sink", "cuba")},
    "BATHROOM": {"bancada": ("bancada", "pia", "cuba"), "vaso": ("vaso", "toilet")},
}


def _seg_in(w, k):
    s = w["start"] if not isinstance(w["start"], str) else json.loads(w["start"])
    e = w["end"] if not isinstance(w["end"], str) else json.loads(w["end"])
    return (s[0] * k, s[1] * k, e[0] * k, e[1] * k)


def _pt_seg(px, py, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _modules(boxes):
    mods = defaultdict(list)
    for b in boxes:
        if b.get("corners"):
            mods[str(b.get("module", b.get("kind", "movel")))].append(b)
    return mods


def _is(name, types):
    n = name.lower()
    return any(t in n for t in types)


def scorecard(con, room_id):
    os.environ.setdefault("PT_TO_M", "0.0259")
    k_in = float(os.environ["PT_TO_M"]) * IN_PER_M
    from tools.furnish_apartment import BRAINS
    from tools.room_type import classify_rooms
    r = {x["id"]: x for x in classify_rooms(con)}.get(room_id)
    if not r:
        return {"room": room_id, "overall": "FAIL", "error": "cômodo inexistente"}
    rtype = r["room_type"]
    brain = BRAINS.get(rtype)
    boxes, _ = brain(con, room_id) if brain else ([], {})
    mods = _modules(boxes)
    segs = [_seg_in(w, k_in) for w in (con.get("walls") or [])]

    dims = {}

    # --- ANCORAGEM (furniture_wall_anchor_gate) ---
    anchor_fails, anchor_warns = [], []
    for m, bs in mods.items():
        if _is(m, CENTER_TYPES) or not _is(m, ANCHOR_TYPES):
            continue
        pts = [c for b in bs for c in b["corners"]]
        d_cm = (min(min(_pt_seg(c[0], c[1], s) for s in segs) for c in pts) / IN_PER_M * 100) if segs and pts else 999
        if d_cm > ANCHOR_WARN_CM:
            anchor_fails.append(f"{m} FLUTUANDO ({d_cm:.0f}cm da parede)")
        elif d_cm > ANCHOR_FLUSH_CM:
            anchor_warns.append(f"{m} não-flush ({d_cm:.0f}cm)")
    dims["ancoragem"] = ("FAIL" if anchor_fails else "WARN" if anchor_warns else "PASS",
                         anchor_fails + anchor_warns)

    # --- ZONAS (room_zone_gate) ---
    zspec = ROOM_ZONES.get(rtype, {})
    zone_miss = [z for z, subs in zspec.items() if not any(_is(m, subs) for m in mods)]
    dims["layout_zonas"] = ("FAIL" if zone_miss else "PASS",
                            [f"zona AUSENTE: {z}" for z in zone_miss] or ["zonas presentes"])

    # --- QUALIDADE DE MOBILIÁRIO (furniture_quality_gate) ---
    proxy = [f"{m} = cubo proxy (parts={len(bs)})" for m, bs in mods.items()
             if _is(m, DETAIL_REQUIRED) and len(bs) < DETAIL_MIN]
    dims["qualidade_movel"] = ("FAIL" if len(proxy) >= 2 else "WARN" if proxy else "PASS", proxy or ["móveis detalhados"])

    # --- COMPONENTIZAÇÃO ---
    named = sum(1 for m in mods if m and m != "movel")
    dims["componentizacao"] = ("PASS" if named == len(mods) and mods else "WARN",
                               [f"{named}/{len(mods)} módulos nomeados/selecionáveis"])

    # --- PLANNED-NICHE CANDIDATES (planned_niche_candidate_gate) ---
    niche = []
    for m, bs in mods.items():
        if _is(m, ("rack", "tv", "aparador", "buffet", "estante")) and len(bs) < DETAIL_MIN:
            niche.append(f"{m} -> painel/sistema planejado na parede (hoje é proxy solto)")
    dims["planned_niche_candidatos"] = ("WARN" if niche else "PASS", niche or ["sem candidatos"])

    # --- LINGUAGEM / GOLDEN-SAMPLE (placeholder — tema ainda não aplicado no baseline) ---
    dims["linguagem_golden_sample"] = ("N/A", ["tema não aplicado (fase posterior); comparar vs GOLDEN_SAMPLE_004"])

    order = ["FAIL", "WARN", "PASS", "N/A"]
    grades = [g for g, _ in dims.values() if g != "N/A"]
    overall = "FAIL" if "FAIL" in grades else "WARN" if "WARN" in grades else "PASS"
    return {"room": room_id, "room_name": r["name"], "room_type": rtype,
            "overall": overall, "n_modules": len(mods), "dims": dims}


def _print(res):
    if res.get("error"):
        print(f"[{res['room']}] {res['error']}")
        return
    icon = {"PASS": "[OK  ]", "WARN": "[WARN]", "FAIL": "[FAIL]", "N/A": "[ -- ]"}
    print(f"\n=== {res['room_name']} ({res['room_type']}) -- OVERALL: {res['overall']} ({res['n_modules']} modulos) ===")
    for dim, (g, notes) in res["dims"].items():
        print(f"  {icon[g]} {dim:26} {g}")
        for n in notes:
            print(f"        - {n}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("room", nargs="?", default="all")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    from tools.furnish_apartment import CONSENSUS
    from tools.room_type import classify_rooms
    con = json.loads(CONSENSUS.read_text("utf-8"))
    rooms = [a.room] if a.room != "all" else [r["id"] for r in classify_rooms(con) if r.get("furnishable", True)]
    results = []
    for rid in rooms:
        try:
            results.append(scorecard(con, rid))
        except SystemExit as e:   # ex.: kitchen_validation aborta o build da cozinha
            results.append({"room": rid, "overall": "FAIL", "error": f"brain abortou: {e}"})
        except Exception as e:    # noqa: BLE001 — um cômodo não derruba o apê inteiro
            results.append({"room": rid, "overall": "FAIL", "error": f"erro: {e}"})
    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for res in results:
            _print(res)
    worst = "FAIL" if any(r["overall"] == "FAIL" for r in results) else \
            "WARN" if any(r["overall"] == "WARN" for r in results) else "PASS"
    print(f"\ninterior_quality_scorecard => {worst}")


if __name__ == "__main__":
    main()
