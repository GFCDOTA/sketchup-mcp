"""Load + validate config/assumptions.yaml — Stage 1 of the coherence
audit pipeline.

The yaml file is the project-level questionnaire answered ONCE per
plant. coherence_audit.py reads it to route each ambiguous detection
to clean / debug / ask / drop. This module does NOT mutate consensus
data; it only produces a typed Assumptions object the audit consumes.

Schema version 1.0. Future bumps must preserve backward compatibility
OR add an explicit migration in this loader.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ASSUMPTIONS_PATH = REPO_ROOT / "config" / "assumptions.yaml"
ASSUMPTIONS_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class AmbiguityPolicy:
    drop_below: float = 0.20
    ask_above: float = 0.20
    debug_above: float = 0.50
    clean_above: float = 0.75

    def decide(self, confidence: float) -> str:
        """Return one of: drop | ask | debug | clean."""
        if confidence < self.drop_below:
            return "drop"
        if confidence < self.debug_above:
            return "ask"
        if confidence < self.clean_above:
            return "debug"
        return "clean"


@dataclass(frozen=True)
class Assumptions:
    schema_version: str
    goal: str
    risk_policy: str
    ambiguity: AmbiguityPolicy
    walls: dict[str, Any] = field(default_factory=dict)
    openings: dict[str, Any] = field(default_factory=dict)
    transparent_elements: dict[str, Any] = field(default_factory=dict)
    rooms: dict[str, Any] = field(default_factory=dict)
    strict_blockers: list[str] = field(default_factory=list)
    source_path: str | None = None


def load_assumptions(path: Path | str | None = None) -> Assumptions:
    """Read the YAML at `path` (default: config/assumptions.yaml).

    Returns an Assumptions object. Raises ValueError if the file is
    missing required fields or has an unrecognised schema_version.
    """
    p = Path(path) if path is not None else DEFAULT_ASSUMPTIONS_PATH
    if not p.exists():
        raise FileNotFoundError(f"assumptions file not found: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"assumptions yaml must be a mapping at top: {p}")
    sv = str(raw.get("schema_version", ""))
    if sv != ASSUMPTIONS_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported assumptions schema_version={sv!r}; "
            f"expected {ASSUMPTIONS_SCHEMA_VERSION!r}. Either update "
            f"the file or add a migration to assumptions_loader.py"
        )
    amb = raw.get("ambiguity") or {}
    policy = AmbiguityPolicy(
        drop_below=float(amb.get("drop_below", 0.20)),
        ask_above=float(amb.get("ask_above", 0.20)),
        debug_above=float(amb.get("debug_above", 0.50)),
        clean_above=float(amb.get("clean_above", 0.75)),
    )
    if not (0.0 <= policy.drop_below <= policy.debug_above
            <= policy.clean_above <= 1.0):
        raise ValueError(
            f"assumptions ambiguity thresholds must be monotonically "
            f"increasing in [0,1]: drop_below={policy.drop_below}, "
            f"debug_above={policy.debug_above}, "
            f"clean_above={policy.clean_above}"
        )
    return Assumptions(
        schema_version=sv,
        goal=str(raw.get("goal", "furniture_layout")),
        risk_policy=str(raw.get("risk_policy", "conservative")),
        ambiguity=policy,
        walls=dict(raw.get("walls") or {}),
        openings=dict(raw.get("openings") or {}),
        transparent_elements=dict(raw.get("transparent_elements") or {}),
        rooms=dict(raw.get("rooms") or {}),
        strict_blockers=list(raw.get("strict_blockers") or []),
        source_path=str(p),
    )
