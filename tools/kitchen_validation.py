"""kitchen_validation.py — GATE de FIDELIDADE da cozinha ao PDF (Felipe: KITCHEN_PDF_ANCHOR_FIX).

A pia da cozinha é um PONTO HIDRÁULICO FIXO do PDF: parede OESTE (esquerda), sobre a
bancada vertical. Este gate roda ANTES de renderizar e FALHA o build se a pia migrar de
parede (ou cair fora da cozinha / dentro da A.S.). Imprime o relatório KITCHEN_VALIDATION.

Uso: PT_TO_M=0.0259 python -m tools.kitchen_validation [room_id]
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

# Re-export dos contratos legados; a implementação canônica vive em rooms.kitchen.
from tools.rooms.kitchen.anchor_rules import TOUCH_TOL_IN, _modules, validate  # noqa: E402,F401

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("room", nargs="?", default="r004")
    a = ap.parse_args()
    con = json.loads((ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
                     .read_text("utf-8"))
    res = validate(con, a.room)
    print("\n".join(res["lines"]))
    print(f"\nkitchen_validation => {res['result']}")
    sys.exit(0 if res["result"] == "PASS" else 1)


if __name__ == "__main__":
    main()
