"""Boundary de fidelidade da cozinha para o orquestrador.

Preserva o validador legado como implementação canônica durante FP-042.
Não altera tolerâncias, escala, fixture, nem a API pública.
"""
from __future__ import annotations


def validate_kitchen_anchor(con, room_id: str) -> dict:
    """Executa o gate existente, sem reimplementar regras hidráulicas."""
    from tools.kitchen_validation import validate
    return validate(con, room_id)


def require_kitchen_anchor(con, room_id: str) -> dict:
    """Fail closed antes de renderizar; preserva mensagens do pipeline legado."""
    report = validate_kitchen_anchor(con, room_id)
    print("\n".join(report["lines"]))
    print(f"kitchen_validation => {report['result']}\n")
    if report["result"] != "PASS":
        raise SystemExit(
            "[furnish-apt] BUILD ABORTADO: cozinha reprovou o anchor da pia "
            f"({report['checks'].get('sink_wall')})"
        )
    return report
