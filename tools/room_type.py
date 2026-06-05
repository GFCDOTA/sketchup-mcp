"""room_type.py — classifica o TIPO de cada comodo a partir do NOME do consensus.

O consensus rotula cada `room` com um `name` textual extraido do PDF (dado real,
ex. "SUITE 01", "SALA DE JANTAR | SALA DE ESTAR", "COZINHA", "A.S. | TERRACO ..").
Pra mobiliar SO o que sabemos (sem inventar tipo de comodo), mapeamos esse nome
-> tipo canonico via regex AUDITAVEL. Nome ausente / nao-mapeado -> UNKNOWN, e
UNKNOWN NAO e mobiliado (degrada honesto; Hard Rule #1: nao inventar).

`room_type_source` fica sempre "name_regex" no output: deixa explicito que o tipo
veio de METADADO textual do consensus, nao de visao/IA nem heuristica escondida.

Spec (mapa + degradacao UNKNOWN + room_type_source) validada com ChatGPT no
consult "Prioridade Quartos e Layout" (2026-06-05; registro local em
.ai_bridge/responses/, gitignored).
Felipe 2026-06-05. NAO usa shapely / 3D Warehouse / SKP.

Uso:
    from tools.room_type import classify_room_type, classify_rooms
    classify_room_type("SUITE 01")  -> "BEDROOM"
    classify_rooms(consensus)       -> [{id, name, room_type, room_type_source,
                                         furnishable, [reason]}, ...]
    python -m tools.room_type        # imprime a classificacao da planta_74
"""
from __future__ import annotations

import re
import unicodedata

# ---- tipos canonicos ----
BEDROOM = "BEDROOM"
LIVING = "LIVING"
KITCHEN = "KITCHEN"
BATHROOM = "BATHROOM"
SERVICE = "SERVICE"
BALCONY = "BALCONY"
UNKNOWN = "UNKNOWN"

ALL_TYPES = (BEDROOM, LIVING, KITCHEN, BATHROOM, SERVICE, BALCONY, UNKNOWN)

# comodos que o auto-mobiliado v1 sabe mobiliar POR ESTE pipeline. LIVING ja tem
# o cerebro legado (tools/layout_candidates.py); cozinha/banho ainda nao entram.
FURNISHABLE_V1 = frozenset({BEDROOM})

ROOM_TYPE_SOURCE = "name_regex"

# A ordem IMPORTA: 1o match vence. Comodos "molhados"/especificos (BANHO,
# COZINHA) vem ANTES de BEDROOM pra um nome combinado tipo "BANHO DA SUITE" cair
# em BATHROOM, nao BEDROOM. SERVICE (A.S.) antes de LIVING/BALCONY; LIVING antes
# de BALCONY ("SALA ... TERRACO" -> LIVING). Padroes ja SEM acento (o nome e
# normalizado por _norm antes do match) e em MAIUSCULAS.
_RULES = (
    (BATHROOM, (r"BANHEIRO", r"BANHO", r"LAVABO", r"\bWC\b")),
    (KITCHEN,  (r"COZINHA", r"KITCHEN", r"COPA")),
    (BEDROOM,  (r"SUITE", r"QUARTO", r"DORMITORIO", r"\bDORM\b")),
    (SERVICE,  (r"\bA\.?\s*S\b", r"AREA\s+DE\s+SERVICO", r"AREA\s+SERVICO",
                r"LAVANDERIA", r"SERVICO")),
    (LIVING,   (r"SALA", r"\bESTAR\b", r"JANTAR", r"LIVING")),
    (BALCONY,  (r"TERRACO", r"VARANDA", r"SACADA", r"BALCONY")),
)


def _norm(name: str | None) -> str:
    """Maiuscula + sem acento (NFKD), pra casar SUITE/SUITE, TERRACO/TERRACO."""
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.upper()


def classify_room_type(name: str | None) -> str:
    """Nome textual do comodo -> tipo canonico. Vazio/nao-mapeado -> UNKNOWN."""
    norm = _norm(name)
    if not norm.strip():
        return UNKNOWN
    for rtype, pats in _RULES:
        for p in pats:
            if re.search(p, norm):
                return rtype
    return UNKNOWN


def is_furnishable(room_type: str) -> bool:
    """O auto-mobiliado v1 sabe mobiliar este tipo de comodo?"""
    return room_type in FURNISHABLE_V1


def classify_rooms(consensus: dict) -> list[dict]:
    """Classifica todos os rooms do consensus. UNKNOWN degrada honesto: nao
    mobiliavel + reason auditavel (Hard Rule #1: nao inventar comodo)."""
    out = []
    for r in consensus.get("rooms", []):
        name = r.get("name")
        rtype = classify_room_type(name)
        rec = {
            "id": r.get("id"),
            "name": name,
            "room_type": rtype,
            "room_type_source": ROOM_TYPE_SOURCE,
            "furnishable": is_furnishable(rtype),
        }
        if rtype == UNKNOWN:
            rec["reason"] = "room_type_unknown_missing_or_unmapped_name"
        out.append(rec)
    return out


def main():
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(
        description="Classifica comodos por nome (regex auditavel, sem IA).")
    ap.add_argument(
        "--consensus",
        default="fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json")
    args = ap.parse_args()
    con = json.loads(Path(args.consensus).read_text("utf-8"))
    rows = classify_rooms(con)
    w = max((len(str(r["name"])) for r in rows), default=4)
    for r in rows:
        flag = ("MOBILIAR" if r["furnishable"]
                else ("UNKNOWN!" if r["room_type"] == UNKNOWN else "-"))
        print(f"  {str(r['id']):6} {str(r['name']):{w}}  -> {r['room_type']:9} [{flag}]")
    n_furn = sum(1 for r in rows if r["furnishable"])
    print(f"=> {len(rows)} comodos, {n_furn} mobiliaveis "
          f"(v1: {sorted(FURNISHABLE_V1)}), source={ROOM_TYPE_SOURCE}")


if __name__ == "__main__":
    main()
