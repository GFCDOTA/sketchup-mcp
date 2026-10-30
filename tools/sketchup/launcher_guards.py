"""launcher_guards.py — recusas tipadas dos launchers legados (FP-043 P3b, #457).

Capacidade/entrada que nao existe RECUSA com o motivo (regra do repo), em vez de traceback cru ou de um "OK" que nao fez nada:
  - `require_known_room`: sala/quarto fora do consensus -> mensagem com os ids validos e exit 2, antes de montar caixas ou subir o SketchUp.
  - `verify_bake_log`: o log do recolor so vale se recolriu >= 1 peca E salvou; senao o launcher nao reporta sucesso.
"""
from __future__ import annotations

import re

_RECOLORED = re.compile(r"recolored=(\d+)")


def room_ids(con: dict) -> list[str]:
    """Ids de comodo do consenso, na ordem em que aparecem."""
    return [str(r["id"]) for r in con.get("rooms", []) if r.get("id") is not None]


def require_known_room(con: dict, room_id: str, prog: str) -> None:
    """Sai com codigo 2 e o motivo se `room_id` nao e um comodo do consenso. Nao devolve nada quando vale."""
    ids = room_ids(con)
    if room_id in ids:
        return
    print(f"[{prog}] REFUSED: comodo {room_id!r} inexistente no consenso; validos: {', '.join(ids) or '(nenhum)'} — nada a materializar")
    raise SystemExit(2)


def verify_bake_log(log_text: str) -> tuple[bool, str]:
    """(ok, motivo). O recolor so conta como feito com `recolored>=1` e `saved=true`; log vazio/ausente nao e sucesso."""
    text = (log_text or "").strip()
    if not text or text == "(no log)":
        return False, "sem log do recolor (o SketchUp nao terminou ou nao rodou o script)"
    m = _RECOLORED.search(text)
    if not m:
        return False, "log sem 'recolored=N' (formato inesperado)"
    n = int(m.group(1))
    if n == 0:
        return False, "recolored=0: o tema nao casou com nenhuma peca (tema inexistente?)"
    if "saved=true" not in text:
        return False, "saved=false: o .skp tematizado nao foi salvo"
    return True, f"recolored={n}"
