"""output_policy.py — onde um entrypoint LEGADO pode escrever (FP-055 P1/P3, #423).

`artifacts/` e `fixtures/` guardam os canonicos (regra do repo): so se escreve la com `allow_official_write` explicito, e
quem chama ainda precisa dos gates verdes e da aprovacao humana (`core.pipeline_contracts.GenerationRequest`, a mesma regra).
Por padrao a saida vai para `runs/` (scratch ignorado pelo git). Nenhum caminho "quase oficial" passa em silencio.
"""
from __future__ import annotations

from pathlib import Path

OFFICIAL_ROOTS = ("artifacts", "fixtures")


class OfficialWriteBlocked(RuntimeError):
    """Saida em pasta oficial sem `allow_official_write`."""


def is_official(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return bool(rel.parts) and rel.parts[0] in OFFICIAL_ROOTS


def resolve_output_dir(root: Path, requested: str | Path | None, default: Path, *, allow_official_write: bool = False) -> Path:
    """Pasta de saida: `requested` (ou `default`, sempre fora de artifacts/) ja resolvida. Pasta oficial sem a flag = erro."""
    out = Path(requested) if requested else default
    out = out if out.is_absolute() else root / out
    if is_official(out, root) and not allow_official_write:
        raise OfficialWriteBlocked(
            f"saida em pasta oficial ({out}) exige allow_official_write (gates verdes + aprovacao humana); "
            f"padrao seguro: {default}")
    return out.resolve()
