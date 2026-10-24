"""known_gaps.py — lacunas CONHECIDAS e registradas (docs/governance/known_gaps.json), lidas pelos gates.

Uma lacuna so e "conhecida" se tem Issue de decisao/correcao e motivo. O que nao esta aqui reprova; o que esta aqui deixa de
ser silencio (o relatorio de auditoria a lista) mas NUNCA vira aprovacao. Chaves:
  program          perda de programa de mobiliario (`<room>|PROGRAM|<modulo>`)
  twin_borderline  achado do gemeo a ~0,1 mm do limiar que o construido nao acusa
  door_sweep       peca no giro real da folha (`<porta>|<modulo>`), baseline R5 (FP-056)
"""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "docs/governance/known_gaps.json"


def load(path: Path = PATH) -> dict:
    return json.loads(path.read_text("utf-8")) if path.exists() else {}
