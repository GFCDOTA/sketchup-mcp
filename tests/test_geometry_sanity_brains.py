"""Regressao do geometry_sanity: o placement dos brains deve ser geometricamente SÃO — nenhum comodo
pode dar FAIL (movel fora/atravessando parede/bloqueando porta). WARN e permitido (sinal leve).
Guarda contra (a) o gate regredir p/ falso-FAIL e (b) o placement regredir p/ caos real."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.furnish_apartment import BRAINS, CONSENSUS, classify_rooms  # noqa: E402
from tools.geometry_sanity import sanity_room  # noqa: E402


def main():
    con = json.loads(CONSENSUS.read_text("utf-8"))
    rooms = [r["id"] for r in classify_rooms(con) if r["room_type"] in BRAINS]
    bad = []
    for rid in rooms:
        res = sanity_room(con, rid)
        print(f"[{res['status']}] {rid} ({res['type']}) fails={len(res['fails'])} warns={len(res['warns'])}")
        if res["status"] == "FAIL":
            bad.append((rid, res["fails"]))
    assert not bad, f"geometry_sanity FAIL inesperado (placement do brain deveria ser sao): {bad}"
    print("\nTEST geometry_sanity OK: nenhum comodo FAIL (placement geometricamente sao; gate sem falso-FAIL).")


if __name__ == "__main__":
    main()
