"""Contratos do pipeline inteligente (FP-055 P2). Dominio puro: sem SketchUp, sem I/O.

Cada contrato valida os campos obrigatorios no construtor e serializa com `to_dict()`; campo obrigatorio ausente levanta
`ContractError` com o nome do campo (nunca e descartado em silencio). Unidades: polegadas no plano do SketchUp (`unit="in"`),
metros nas medidas funcionais (`*_m`).

Estados de capacidade num RunManifest (cada um exige o anterior):
  AVAILABLE -> SELECTED -> INVOKED -> CONSUMED -> REFLECTED_IN_MODEL -> VALIDATED
`CapabilityLedger` e o unico jeito de registrar; `consume` exige evidencia do efeito (qual estagio usou a saida e como).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

PROFILES = ("LEGACY_DIAGNOSTIC", "INTELLIGENT_DRY_RUN", "INTELLIGENT_BUILD")
CAPABILITY_STATES = ("AVAILABLE", "SELECTED", "INVOKED", "CONSUMED", "REFLECTED_IN_MODEL", "VALIDATED")
VALIDATION_STATES = ("PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE", "NOT_EXECUTED")
PROPOSAL_STATES = ("FEASIBLE", "INFEASIBLE", "UNKNOWN", "INVALID_INPUT", "NOT_INTEGRATED")


class ContractError(ValueError):
    pass


def _require(obj, *names: str) -> None:
    for n in names:
        v = getattr(obj, n)
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ContractError(f"{type(obj).__name__}.{n} obrigatorio")


@dataclass(frozen=True)
class GenerationRequest:
    project_id: str
    source_document: str                 # caminho do consensus/PDF que manda na arquitetura
    source_revision: str                 # sha256 do source_document
    repository_commit: str
    generation_profile: str
    output_directory: str
    target_rooms: tuple[str, ...] = ()   # vazio = todos os comodos com especialista integrado
    approved_decisions: tuple[str, ...] = ()
    allow_official_write: bool = False
    deterministic_seed: int = 0

    def __post_init__(self):
        _require(self, "project_id", "source_document", "source_revision", "repository_commit", "generation_profile",
                 "output_directory")
        if self.generation_profile not in PROFILES:
            raise ContractError(f"perfil desconhecido: {self.generation_profile}")
        if self.allow_official_write and not self.output_directory.replace("\\", "/").startswith("artifacts/"):
            raise ContractError("allow_official_write so faz sentido com saida em artifacts/")
        if not self.allow_official_write and self.output_directory.replace("\\", "/").startswith(("artifacts/", "fixtures/")):
            raise ContractError("saida em artifacts/ ou fixtures/ exige allow_official_write (e gates + aprovacao humana)")


@dataclass(frozen=True)
class RoomContext:
    room_id: str
    room_name: str
    room_type: str
    cell_polygon_in: tuple[tuple[float, float], ...]
    portals_in: tuple[tuple[float, float], ...]
    unit: str = "in"
    approved_decisions: tuple[str, ...] = ()

    def __post_init__(self):
        _require(self, "room_id", "room_name", "room_type")
        if len(self.cell_polygon_in) < 3:
            raise ContractError(f"RoomContext.cell_polygon_in de {self.room_id} com menos de 3 vertices")
        if self.unit != "in":
            raise ContractError("RoomContext.unit deve ser 'in'")


@dataclass(frozen=True)
class SpecialistPlan:
    room: str                            # chave do especialista (bathroom, kitchen, ...)
    profile_version: str
    profile_state: str
    builder_symbol: str                  # o builder que o especialista autoriza (precisa estar na allowlist)
    policy_version: str                  # tools/rooms/<comodo>/solver_policy.py POLICY_VERSION
    object_policies: dict[str, dict]     # tipo de objeto -> {anchor, dof}
    constraints: tuple[str, ...]
    recipe_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    capability_ids: tuple[str, ...]

    def __post_init__(self):
        _require(self, "room", "profile_version", "builder_symbol", "policy_version")
        if not self.object_policies:
            raise ContractError(f"SpecialistPlan de {self.room} sem politica de objetos (solver_policy)")


@dataclass(frozen=True)
class LayoutProposal:
    proposal_id: str
    room_id: str
    status: str                          # PROPOSAL_STATES
    candidate_id: str
    moves: tuple[dict, ...]
    hard_violations: tuple[dict, ...]
    metrics: dict
    rank: int | None
    candidates_total: int
    explanation: str
    algorithm_version: str
    policy_version: str
    boxes: tuple[dict, ...] = field(default=(), repr=False)   # caixas do comodo na proposta (o que o builder deve construir)

    def __post_init__(self):
        _require(self, "proposal_id", "room_id", "status", "candidate_id", "algorithm_version", "policy_version")
        if self.status not in PROPOSAL_STATES:
            raise ContractError(f"LayoutProposal.status invalido: {self.status}")
        if self.status == "FEASIBLE" and self.hard_violations:
            raise ContractError("proposta FEASIBLE com violacao rigida")

    @property
    def buildable_as_valid(self) -> bool:
        return self.status == "FEASIBLE"

    def to_dict(self, with_boxes: bool = False) -> dict:
        d = asdict(self)
        if not with_boxes:
            d.pop("boxes")
        return d


@dataclass(frozen=True)
class ValidationReport:
    gate: str
    status: str
    validator_version: str
    inputs: str
    evidence: dict

    def __post_init__(self):
        _require(self, "gate", "status", "validator_version", "inputs")
        if self.status not in VALIDATION_STATES:
            raise ContractError(f"ValidationReport.status invalido: {self.status}")


@dataclass(frozen=True)
class BuildResult:
    requested: tuple[str, ...]           # "<comodo> · <modulo>"
    built: tuple[str, ...]
    omitted: dict[str, str]              # o que nao saiu -> motivo
    divergences: tuple[dict, ...]        # proposta x construido acima da tolerancia
    sketchup_version: str
    errors: tuple[str, ...] = ()

    def __post_init__(self):
        _require(self, "sketchup_version")
        missing = set(self.requested) - set(self.built) - set(self.omitted)
        if missing:
            raise ContractError(f"BuildResult sem motivo para o que nao foi construido: {sorted(missing)[:5]}")


class CapabilityLedger:
    """Registro dos estados por capacidade. Ordem obrigatoria; CONSUMED/REFLECTED/VALIDATED pedem evidencia."""

    def __init__(self) -> None:
        self._s: dict[str, dict[str, Any]] = {}

    # pre-requisito de cada estado (SELECTED e opcional: capacidade obrigatoria e invocada sem selecao)
    _NEEDS = {"AVAILABLE": (None,), "SELECTED": ("AVAILABLE",), "INVOKED": ("AVAILABLE", "SELECTED"),
              "CONSUMED": ("INVOKED",), "REFLECTED_IN_MODEL": ("CONSUMED",), "VALIDATED": ("REFLECTED_IN_MODEL",)}

    def _set(self, name: str, state: str, evidence: str | None) -> None:
        cur = self._s.setdefault(name, {"state": None, "trail": []})
        if cur["state"] is not None and CAPABILITY_STATES.index(cur["state"]) >= CAPABILITY_STATES.index(state):
            return                                      # ja esta nesse estado ou alem: idempotente
        if cur["state"] not in self._NEEDS[state]:
            raise ContractError(f"{name}: {state} exige antes {self._NEEDS[state]}, esta em {cur['state']}")
        if state in ("CONSUMED", "REFLECTED_IN_MODEL", "VALIDATED") and not evidence:
            raise ContractError(f"{name}: {state} exige evidencia do efeito")
        cur["state"] = state
        cur["trail"].append({"state": state, "evidence": evidence})

    def available(self, name, evidence=None):
        self._set(name, "AVAILABLE", evidence)

    def select(self, name, evidence=None):
        self._set(name, "SELECTED", evidence)

    def invoke(self, name, evidence=None):
        self._set(name, "INVOKED", evidence)

    def consume(self, name, evidence):
        self._set(name, "CONSUMED", evidence)

    def reflect(self, name, evidence):
        self._set(name, "REFLECTED_IN_MODEL", evidence)

    def validate(self, name, evidence):
        self._set(name, "VALIDATED", evidence)

    def state(self, name: str) -> str | None:
        return (self._s.get(name) or {}).get("state")

    def to_dict(self) -> dict:
        return {k: dict(v) for k, v in sorted(self._s.items())}
