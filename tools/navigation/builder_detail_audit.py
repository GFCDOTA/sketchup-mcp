"""Mede quanto da geometria de cada builder de movel NAO vem do pedido: literais float embutidos nas funcoes do builder.

Definicao (estavel, para a trava regressiva): conta `ast.Constant` float dentro de qualquer funcao do modulo, exceto
0.0, 0.5, 1.0 e 2.0 (metade/inteiro/dobro sao aritmetica, nao medida). Inclui proporcoes de classe legitimas e folgas
embutidas — o numero e um termometro, nao um veredito: o contrato novo (`shared.cabinet`) chega a 0 porque toda medida
entra como `{value, unit, origin}`.

    python -m tools.navigation.builder_detail_audit                  # tabela
    python -m tools.navigation.builder_detail_audit --json           # para o baseline
O baseline versionado (`docs/reports/construction_core/builder_detail_baseline.v1.json`) so pode DIMINUIR
(`tests/test_builder_detail_audit.py`): microfase que migra um builder atualiza o baseline no mesmo PR.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARITHMETIC = {0.0, 0.5, 1.0, 2.0}
# contrato novo: medidas do pedido, pecas por papel, prova L2 (FP-043 P6, FP-046)
GEN2 = ("tools/rooms/shared/cabinet/assembly.py", "tools/rooms/shared/cabinet/plan.py",
        "tools/rooms/shared/cabinet/shaker/plan.py", "tools/rooms/shared/cabinet/shaker/model.py")
# builders de classe do programa de jun/2026 (gate L1, constantes no codigo)
GEN1 = ("tools/rooms/shared/wardrobe.py", "tools/rooms/shared/bed.py", "tools/rooms/shared/nightstand.py",
        "tools/rooms/shared/sofa.py", "tools/rooms/shared/armchair_builder.py", "tools/rooms/shared/decor_builders.py",
        "tools/rooms/living/rack_class.py", "tools/rooms/living/coffee_table_class.py",
        "tools/rooms/living/dining_table_class.py", "tools/rooms/living/armchair_class.py", "tools/rooms/living/sofa_class.py")


def _floats(nodes) -> list[float]:
    seen: set[int] = set()
    out: list[float] = []
    for root in nodes:
        for node in ast.walk(root):
            if (isinstance(node, ast.Constant) and type(node.value) is float and node.value not in ARITHMETIC
                    and id(node) not in seen):                     # funcao aninhada nao conta duas vezes
                seen.add(id(node))
                out.append(node.value)
    return out


def embedded_floats(source: str) -> list[float]:
    """Literais dentro de funcoes: medida escondida no meio do algoritmo."""
    tree = ast.parse(source)
    return _floats(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))


def module_constants(source: str) -> list[float]:
    """Literais em atribuicoes de topo (`MARGIN = 0.03`): medida com nome, mas ainda fixa no codigo."""
    tree = ast.parse(source)
    return _floats(n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign)))


def audit(root: Path = ROOT) -> dict:
    rows = {}
    for gen, paths in (("gen2_request_driven", GEN2), ("gen1_class_builder", GEN1)):
        for rel in paths:
            source = (root / rel).read_text(encoding="utf-8")
            lits = embedded_floats(source)
            rows[rel] = {"generation": gen, "embedded_float_literals": len(lits), "distinct": len(set(lits)),
                         "module_float_constants": len(module_constants(source))}
    return {"schema_version": "builder_detail_audit.v1", "definition": "float literal != 0/0.5/1/2 inside functions",
            "builders": rows, "total_gen1": sum(r["embedded_float_literals"] for r in rows.values()
                                                 if r["generation"] == "gen1_class_builder")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    report = audit()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    for rel, row in report["builders"].items():
        print(f"{row['generation']:<20} {row['embedded_float_literals']:>4} ({row['distinct']:>3} distintos)"
              f"  +{row['module_float_constants']:>3} de topo  {rel}")
    print(f"total gen1: {report['total_gen1']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
