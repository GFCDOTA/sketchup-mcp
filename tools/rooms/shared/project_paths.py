"""Caminhos estáveis do projeto, sem dependência do orquestrador de mobiliário."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLANTA_74_CONSENSUS = (
    ROOT / "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json"
)
