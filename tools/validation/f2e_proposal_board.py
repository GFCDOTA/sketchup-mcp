"""f2e_proposal_board.py — CLI da evidencia F2E (FP-054): proposta somente-leitura + overlays antes/depois por comodo.

    PT_TO_M=0.0259 python -m tools.validation.f2e_proposal_board artifacts/review/fp054/f2e

Fica em `tools/validation` (como o board da F1C) porque carrega a planta pelo orquestrador; o solver compartilhado nao importa
orquestracao.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path


def main(out_dir: Path) -> list[Path]:
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    from tools.rooms.shared.spatial_solver.proposal import build
    from tools.validation.functional_clearance import collect_interfaces
    con = json.loads(CONSENSUS.read_text("utf-8"))
    with contextlib.redirect_stdout(io.StringIO()):
        boxes, _ = collect_boxes(con)
        ifaces = collect_interfaces(con, boxes)
    return build(out_dir, con, boxes, ifaces)


if __name__ == "__main__":
    for path in main(Path(sys.argv[1])):
        print(path)
