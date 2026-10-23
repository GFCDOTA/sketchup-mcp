"""functional_constraints.py — contratos de folga funcional e alcance por peca (FP-054 F1B, "o que e valido?").

Separacao (nada aqui mede geometria nem decide layout):
    politica/conhecimento (THRESHOLDS, com proveniencia)  ->  definicao (FUNCTIONAL_CONSTRAINTS, OBJECT_TYPES)
    ->  medicao/avaliacao (tools.validation.functional_clearance)  ->  veredito (FunctionalEvaluation)

Tres niveis por regra, nunca misturados: `reference_minimum` (referencia tecnica/guia), `project_target` (politica do projeto),
`preferred` (conforto). Cada nivel traz proveniencia: NORMATIVE so com fonte primaria comprovada — nenhum valor abaixo e
NORMATIVE. Os alvos de projeto propostos em 2026-10-23 aguardam aprovacao do Felipe (`approval`): por isso o gate da F1B roda
em REPORT_ONLY e nao bloqueia layout.

Contrato para a F2 (o solver so CONSOME): restricao hard (`reference_minimum`), alvo, preferido, valor medido, veredito, codigo
do motivo e geometria testemunha. O solver nao redefine limiar, nao relaxa hard, nao ignora INVALID, nao converte BLOCKED em PASS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PROVENANCE = ("NORMATIVE", "TECHNICAL_REFERENCE", "PROJECT_POLICY", "COMFORT_GUIDE", "HEURISTIC")
VERDICTS = ("INVALID", "VALID_BELOW_TARGET", "VALID", "PREFERRED", "BLOCKED_MISSING_INPUT", "NOT_APPLICABLE")
MEASURED_VERDICTS = ("INVALID", "VALID_BELOW_TARGET", "VALID", "PREFERRED")
UNITS = ("m",)
USE_FACE_CONTRACTS = ("opposite_single_backing_wall", "opposite_longest_backing_side", "single_free_side")

Verdict = Literal["INVALID", "VALID_BELOW_TARGET", "VALID", "PREFERRED", "BLOCKED_MISSING_INPUT", "NOT_APPLICABLE"]


@dataclass(frozen=True)
class Threshold:
    value: float
    unit: str
    provenance: str
    source: str
    approval: str = "N/A"          # PENDING_FELIPE | APPROVED | EXISTING_PROJECT_DECISION | N/A (referencias externas)

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE:
            raise ValueError(f"proveniencia desconhecida: {self.provenance!r}")
        if self.unit not in UNITS:
            raise ValueError(f"unidade invalida: {self.unit!r}")
        if not self.source:
            raise ValueError("proveniencia sem fonte")
        if self.value <= 0:
            raise ValueError("limiar precisa ser positivo")

    def to_dict(self) -> dict:
        return {"value": self.value, "unit": self.unit, "provenance": self.provenance, "source": self.source,
                "approval": self.approval}


@dataclass(frozen=True)
class FunctionalConstraint:
    id: str
    object_type: str
    metric: str                     # front_depth | opening_disk_diameter | reach_path_width
    reference_minimum: Threshold
    project_target: Threshold
    preferred: Threshold

    def __post_init__(self) -> None:
        a, b, c = self.reference_minimum.value, self.project_target.value, self.preferred.value
        if not a <= b <= c:
            raise ValueError(f"{self.id}: niveis fora de ordem (minimo {a} <= alvo {b} <= preferido {c})")

    def classify(self, measured: float) -> str:
        if measured < self.reference_minimum.value - 1e-9:
            return "INVALID"
        if measured < self.project_target.value - 1e-9:
            return "VALID_BELOW_TARGET"
        if measured < self.preferred.value - 1e-9:
            return "VALID"
        return "PREFERRED"


@dataclass(frozen=True)
class FunctionalEvaluation:
    room_id: str
    object_id: str
    object_type: str
    constraint_id: str
    verdict: Verdict
    reason_code: str
    measured: float | None = None
    unit: str | None = None
    missing_input: tuple[str, ...] = ()
    witness: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(f"veredito desconhecido: {self.verdict!r}")
        if self.verdict in MEASURED_VERDICTS and (self.measured is None or self.unit not in UNITS):
            raise ValueError(f"{self.constraint_id}: {self.verdict} exige medida em unidade valida")
        if self.verdict == "BLOCKED_MISSING_INPUT" and not self.missing_input:
            raise ValueError(f"{self.constraint_id}: BLOCKED_MISSING_INPUT exige missing_input")

    def to_dict(self, constraint: FunctionalConstraint | None = None) -> dict:
        out = {"room_id": self.room_id, "object_id": self.object_id, "object_type": self.object_type,
               "constraint": self.constraint_id, "verdict": self.verdict, "reason_code": self.reason_code,
               "measured": None if self.measured is None else round(self.measured, 4), "unit": self.unit,
               "missing_input": list(self.missing_input), "witness": self.witness}
        if constraint is not None:
            out.update(reference_minimum=constraint.reference_minimum.to_dict(),
                       project_target=constraint.project_target.to_dict(), preferred=constraint.preferred.to_dict())
        return out


# --------------------------------------------------------------------------------------------- fontes (2026-10-23)
_PLANNER5D_BATH = "Planner 5D, tamanho padrao de banheiro (guia de planejamento): ~60 cm livres na frente da bacia; circulacao 60-80 cm"
_IBIRAPUERA = "auditorioibirapuera.com.br, espaco para o vaso: 60 cm entre a bacia e a parede da frente (guia, nao norma)"
_LAV_GUIDE = "guia de planejamento citado na pesquisa de 2026-10-23: >= 55 cm livres na frente do lavatorio"
_NBR9050_VIA = ("ABNT NBR 9050:2020 citada por terceiros (lawinsider 'boxes comuns'): area livre de 0,60 m de diametro; vao 0,60 m "
                "em edificacao existente, 0,80 m em nova — fonte primaria NAO conferida, por isso TECHNICAL_REFERENCE e nao NORMATIVE")
_KITCHEN_GUIDE = "guias de planejamento (planner5d area de circulacao; catracalivre): 90 cm-1 m de passagem; ~1 m livre na frente de pia/fogao"
_POLICY_090 = "core/project_policy.py CIRCULATION_PRIMARY_TARGET_M = 0,90 (decisao de projeto existente, residencial planta_74)"
_PROPOSAL = "proposta FP-054 F1B de 2026-10-23 no chat; aguardando aprovacao do Felipe"


def _t(v, prov, src, approval="N/A"):
    return Threshold(v, "m", prov, src, approval)


FUNCTIONAL_CONSTRAINTS: dict[str, FunctionalConstraint] = {c.id: c for c in (
    FunctionalConstraint("toilet.front_clearance", "toilet", "front_depth",
                         _t(0.60, "COMFORT_GUIDE", _PLANNER5D_BATH + " | " + _IBIRAPUERA),
                         _t(0.60, "PROJECT_POLICY", _PROPOSAL, "PENDING_FELIPE"),
                         _t(0.80, "COMFORT_GUIDE", _PLANNER5D_BATH)),
    FunctionalConstraint("toilet.reach_path", "toilet", "reach_path_width",
                         _t(0.60, "COMFORT_GUIDE", _PLANNER5D_BATH),
                         _t(0.60, "PROJECT_POLICY", _PROPOSAL, "PENDING_FELIPE"),
                         _t(0.80, "COMFORT_GUIDE", _PLANNER5D_BATH)),
    FunctionalConstraint("lavatory.front_clearance", "lavatory", "front_depth",
                         _t(0.55, "COMFORT_GUIDE", _LAV_GUIDE),
                         _t(0.60, "PROJECT_POLICY", _PROPOSAL, "PENDING_FELIPE"),
                         _t(0.80, "COMFORT_GUIDE", _PLANNER5D_BATH)),
    FunctionalConstraint("lavatory.reach_path", "lavatory", "reach_path_width",
                         _t(0.60, "COMFORT_GUIDE", _PLANNER5D_BATH),
                         _t(0.60, "PROJECT_POLICY", _PROPOSAL, "PENDING_FELIPE"),
                         _t(0.80, "COMFORT_GUIDE", _PLANNER5D_BATH)),
    FunctionalConstraint("shower.opening_clearance", "shower", "opening_disk_diameter",
                         _t(0.60, "TECHNICAL_REFERENCE", _NBR9050_VIA),
                         _t(0.60, "PROJECT_POLICY", _PROPOSAL, "PENDING_FELIPE"),
                         _t(0.80, "TECHNICAL_REFERENCE", _NBR9050_VIA)),
    FunctionalConstraint("shower.reach_path", "shower", "reach_path_width",
                         _t(0.60, "TECHNICAL_REFERENCE", _NBR9050_VIA),
                         _t(0.60, "PROJECT_POLICY", _PROPOSAL, "PENDING_FELIPE"),
                         _t(0.80, "COMFORT_GUIDE", _PLANNER5D_BATH)),
    FunctionalConstraint("kitchen_counter.front_clearance", "kitchen_counter", "front_depth",
                         _t(0.90, "COMFORT_GUIDE", _KITCHEN_GUIDE),
                         _t(0.90, "PROJECT_POLICY", _POLICY_090, "EXISTING_PROJECT_DECISION"),
                         _t(1.00, "COMFORT_GUIDE", _KITCHEN_GUIDE)),
    FunctionalConstraint("kitchen_counter.reach_path", "kitchen_counter", "reach_path_width",
                         _t(0.90, "COMFORT_GUIDE", _KITCHEN_GUIDE),
                         _t(0.90, "PROJECT_POLICY", _POLICY_090, "EXISTING_PROJECT_DECISION"),
                         _t(1.00, "COMFORT_GUIDE", _KITCHEN_GUIDE)),
)}

# Tipo funcional por modulo (nome EXATO, tabela central editada por humano — nunca prefixo/forma) e o contrato que diz qual
# lado da peca e a face de uso. Peca sem face resolvivel pelo contrato -> BLOCKED_MISSING_INPUT (builder precisa declarar).
#   opposite_single_backing_wall  : exatamente 1 lado encostado (vaso: apoiado pela caixa acoplada; canto = ambiguo)
#   opposite_longest_backing_side : bancadas correm ao longo da parede; o lado encostado MAIS LONGO e o de apoio
#                                   (empate de comprimento ou lados opostos encostados = ambiguo)
#   single_free_side              : box fechado em parede/vidro; o unico lado livre e a abertura
OBJECT_TYPES: dict[str, dict] = {
    "toilet": {"modules": {("BATHROOM", "Vaso")}, "use_face_contract": "opposite_single_backing_wall"},
    "lavatory": {"modules": {("BATHROOM", "Bancada")}, "use_face_contract": "opposite_longest_backing_side"},
    "shower": {"modules": {("BATHROOM", "Box")}, "use_face_contract": "single_free_side"},
    "kitchen_counter": {"modules": {("KITCHEN", "countertop")}, "use_face_contract": "opposite_longest_backing_side"},
}


def constraints_for(object_type: str) -> list[FunctionalConstraint]:
    return [c for c in FUNCTIONAL_CONSTRAINTS.values() if c.object_type == object_type]


def registry_errors() -> list[str]:
    """Consistencia do registro (o que o gate REPORT_ONLY reprova): tipos, contratos, metricas e proveniencia."""
    errs = []
    for t, spec in OBJECT_TYPES.items():
        if spec["use_face_contract"] not in USE_FACE_CONTRACTS:
            errs.append(f"{t}: contrato de face desconhecido")
        metrics = {c.metric for c in constraints_for(t)}
        if "reach_path_width" not in metrics or not metrics - {"reach_path_width"}:
            errs.append(f"{t}: precisa de uma folga na face de uso E de alcance a partir do portal")
    for c in FUNCTIONAL_CONSTRAINTS.values():
        if c.object_type not in OBJECT_TYPES:
            errs.append(f"{c.id}: tipo sem registro")
        for lvl in (c.reference_minimum, c.project_target, c.preferred):
            if lvl.provenance == "NORMATIVE":
                errs.append(f"{c.id}: NORMATIVE sem fonte primaria comprovada nao e permitido nesta fase")
    return errs
