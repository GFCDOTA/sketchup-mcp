"""Para onde um job de SketchUp pode escrever — e para onde NUNCA.

Regras (CLAUDE.md, Hard Rule #3 + artifact_policy):

- `fixtures/` é entrada pinada pela smoke suite: nenhum job escreve lá.
- `artifacts/` é o entregável: só `promote_canonical` escreve lá, depois de
  gates verdes. Um job automático que salvasse direto no `.skp` canônico
  pularia o gate — por isso o caminho inteiro é proibido como destino.
- O `.skp` de entrada nunca é sobrescrito: edição sempre sai em arquivo novo.
- Caminho relativo é resolvido contra o repo e `.resolve()`-ado: o SketchUp
  salva relativo ao CWD DELE e produz um "saved" falso (lição do cycle 002).

O default é `runs/<plant>/mcp/<job>_<stamp>/` — scratch, gitignored.
"""
from __future__ import annotations

import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Raízes onde job automático nunca escreve.
FORBIDDEN_ROOTS = ("fixtures", "artifacts")


class OutputPathRefused(ValueError):
    """Destino proibido. A mensagem diz qual regra barrou."""


def _repo(repo: Path | None) -> Path:
    # lido NA CHAMADA (não no def): os testes trocam REPO_ROOT por um diretório
    # temporário e nenhum caminho relativo escapa para o repo de verdade
    return repo if repo is not None else REPO_ROOT


def resolve(path: str | Path, *, repo: Path | None = None) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = _repo(repo) / p
    return p.resolve()


def default_out_dir(job: str, plant: str = "planta_74", *,
                    repo: Path | None = None, stamp: str | None = None) -> Path:
    stamp = stamp or time.strftime("%Y%m%d_%H%M%S")
    return (_repo(repo) / "runs" / plant / "mcp" / f"{job}_{stamp}").resolve()


def check_output(path: str | Path, *, inputs: tuple[str | Path, ...] = (),
                 repo: Path | None = None) -> Path:
    """Devolve o caminho absoluto se for um destino permitido; senão levanta."""
    repo = _repo(repo)
    out = resolve(path, repo=repo)
    for root in FORBIDDEN_ROOTS:
        base = (repo / root).resolve()
        if out == base or base in out.parents:
            hint = (" — promova com promote_canonical depois dos gates"
                    if root == "artifacts" else " — fixtures são entrada pinada")
            raise OutputPathRefused(f"destino dentro de {root}/ é proibido: {out}{hint}")
    for src in inputs:
        if src and resolve(src, repo=repo) == out:
            raise OutputPathRefused(f"destino igual à entrada ({out}); edição sai em arquivo novo")
    return out
