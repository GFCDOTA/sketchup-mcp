"""functional_constraints.py — contratos de folga funcional e alcance por peca (FP-054 F1B/F1C, "o que e valido?").

Separacao (nada aqui mede geometria nem decide layout):
    politica/conhecimento (limiares + FONTES estruturadas)  ->  definicao (FUNCTIONAL_CONSTRAINTS, OBJECT_TYPES)
    ->  interface funcional (FunctionalInterface: use_face / work_face / shower_entry, com BASE declarada)
    ->  medicao/avaliacao (tools.validation.functional_clearance)  ->  veredito (FunctionalEvaluation)

Tres niveis por regra, nunca misturados: `reference_minimum`, `project_target`, `preferred`. Cada nivel tem proveniencia e
FONTES no modelo de autoridade de `docs/engineering/external-documentation-policy.md` (#394): `source_tier` A-E, `source_type`,
`source_ref`, `source_version_or_date`, `exact_claim_supported` (texto conferido na fonte), `applicability`, `limitations`.
Regras do registro: NORMATIVE proibido nesta fase (nenhuma fonte A conferida); COMFORT_GUIDE so com fonte C/D;
TECHNICAL_REFERENCE exige ao menos uma fonte A/B/C; PROJECT_POLICY e HEURISTIC sao internas (tier E).

Interface (F1C): a face de uso vem de semantica EXPLICITA (builder / ancora do PDF). O fallback geometrico da F1B continua so em
REPORT_ONLY e sai marcado `HEURISTIC_GEOMETRY`; em modo SOLVER a ausencia de semantica e BLOCKED_MISSING_INPUT.

Contrato para a F2 (o solver so CONSOME): hard (`reference_minimum`), alvo, preferido, medida, veredito, motivo, geometria
testemunha e base da interface. O solver nao redefine limiar, nao relaxa hard, nao ignora INVALID, nao converte BLOCKED em PASS e
nao usa interface HEURISTIC_GEOMETRY como restricao hard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PROVENANCE = ("NORMATIVE", "TECHNICAL_REFERENCE", "PROJECT_POLICY", "COMFORT_GUIDE", "HEURISTIC")
SOURCE_TIERS = ("A", "B", "C", "D", "E")
VERDICTS = ("INVALID", "VALID_BELOW_TARGET", "VALID", "PREFERRED", "BLOCKED_MISSING_INPUT", "NOT_APPLICABLE")
MEASURED_VERDICTS = ("INVALID", "VALID_BELOW_TARGET", "VALID", "PREFERRED")
UNITS = ("m",)
USE_FACE_CONTRACTS = ("opposite_single_backing_wall", "opposite_longest_backing_side", "single_free_side")
INTERFACE_KINDS = ("use_face", "work_face", "shower_entry")
SEMANTIC_BASES = ("SEMANTIC_BUILDER", "SEMANTIC_PDF_ANCHOR", "SEMANTIC_DECLARED")
INTERFACE_BASES = SEMANTIC_BASES + ("HEURISTIC_GEOMETRY",)
MODES = ("REPORT_ONLY", "SOLVER")

Verdict = Literal["INVALID", "VALID_BELOW_TARGET", "VALID", "PREFERRED", "BLOCKED_MISSING_INPUT", "NOT_APPLICABLE"]


@dataclass(frozen=True)
class SourceRef:
    source_tier: str
    source_type: str
    source_ref: str
    source_version_or_date: str
    exact_claim_supported: str
    applicability: str
    limitations: str

    def __post_init__(self) -> None:
        if self.source_tier not in SOURCE_TIERS:
            raise ValueError(f"tier desconhecido: {self.source_tier!r}")
        for name in ("source_type", "source_ref", "source_version_or_date", "exact_claim_supported", "applicability",
                     "limitations"):
            if not getattr(self, name):
                raise ValueError(f"fonte sem {name}")

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class Threshold:
    value: float
    unit: str
    provenance: str
    sources: tuple[SourceRef, ...]
    approval: str = "N/A"          # PENDING_FELIPE | APPROVED | EXISTING_PROJECT_DECISION | N/A (referencias externas)

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE:
            raise ValueError(f"proveniencia desconhecida: {self.provenance!r}")
        if self.unit not in UNITS:
            raise ValueError(f"unidade invalida: {self.unit!r}")
        if not self.sources:
            raise ValueError("proveniencia sem fonte")
        if self.value <= 0:
            raise ValueError("limiar precisa ser positivo")

    @property
    def source(self) -> str:
        return " | ".join(s.source_ref for s in self.sources)

    def tier_errors(self) -> list[str]:
        tiers = {s.source_tier for s in self.sources}
        if self.provenance == "NORMATIVE":
            return ["NORMATIVE exige fonte A com afirmacao conferida — proibido nesta fase"]
        if self.provenance == "COMFORT_GUIDE" and not tiers <= {"C", "D"}:
            return [f"COMFORT_GUIDE com fonte tier {sorted(tiers)} (so C/D)"]
        if self.provenance == "TECHNICAL_REFERENCE" and not tiers & {"A", "B", "C"}:
            return [f"TECHNICAL_REFERENCE sem fonte A/B/C ({sorted(tiers)})"]
        if self.provenance in ("PROJECT_POLICY", "HEURISTIC") and tiers != {"E"}:
            return [f"{self.provenance} e interno: fonte tem de ser tier E ({sorted(tiers)})"]
        return []

    def to_dict(self) -> dict:
        return {"value": self.value, "unit": self.unit, "provenance": self.provenance, "approval": self.approval,
                "sources": [s.to_dict() for s in self.sources]}


@dataclass(frozen=True)
class FunctionalConstraint:
    id: str
    object_type: str
    metric: str                     # front_depth | entry_clear_width | reach_path_width
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
class FunctionalInterface:
    room_id: str
    module: str
    object_type: str
    interface: str                  # use_face | work_face | shower_entry
    segment_in: tuple[tuple[float, float], tuple[float, float]]
    normal: tuple[float, float]
    basis: str
    source: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.interface not in INTERFACE_KINDS:
            raise ValueError(f"interface desconhecida: {self.interface!r}")
        if self.basis not in INTERFACE_BASES:
            raise ValueError(f"base desconhecida: {self.basis!r}")
        nx, ny = self.normal
        if abs((nx * nx + ny * ny) - 1.0) > 1e-6:
            raise ValueError("normal da interface precisa ser unitaria")
        (x0, y0), (x1, y1) = self.segment_in
        if (x1 - x0) ** 2 + (y1 - y0) ** 2 <= 0:
            raise ValueError("segmento da interface vazio")
        if not self.source:
            raise ValueError("interface sem fonte")

    @property
    def semantic(self) -> bool:
        return self.basis in SEMANTIC_BASES

    def to_dict(self) -> dict:
        return {"interface": self.interface, "segment_in": [list(p) for p in self.segment_in], "normal": list(self.normal),
                "basis": self.basis, "source": self.source, "note": self.note}

    @classmethod
    def from_builder(cls, room_id: str, d: dict) -> "FunctionalInterface":
        return cls(room_id, d["module"], d["object_type"], d["interface"],
                   (tuple(d["segment_in"][0]), tuple(d["segment_in"][1])), tuple(d["normal"]), d["basis"], d["source"],
                   d.get("note", ""))


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
    interface_basis: str | None = None

    def __post_init__(self) -> None:
        if self.verdict not in VERDICTS:
            raise ValueError(f"veredito desconhecido: {self.verdict!r}")
        if self.verdict in MEASURED_VERDICTS and (self.measured is None or self.unit not in UNITS):
            raise ValueError(f"{self.constraint_id}: {self.verdict} exige medida em unidade valida")
        if self.verdict == "BLOCKED_MISSING_INPUT" and not self.missing_input:
            raise ValueError(f"{self.constraint_id}: BLOCKED_MISSING_INPUT exige missing_input")
        if self.verdict in MEASURED_VERDICTS and self.interface_basis not in INTERFACE_BASES:
            raise ValueError(f"{self.constraint_id}: veredito medido exige a base da interface")

    def to_dict(self, constraint: FunctionalConstraint | None = None) -> dict:
        out = {"room_id": self.room_id, "object_id": self.object_id, "object_type": self.object_type,
               "constraint": self.constraint_id, "verdict": self.verdict, "reason_code": self.reason_code,
               "measured": None if self.measured is None else round(self.measured, 4), "unit": self.unit,
               "missing_input": list(self.missing_input), "interface_basis": self.interface_basis, "witness": self.witness}
        if constraint is not None:
            out.update(reference_minimum=constraint.reference_minimum.to_dict(),
                       project_target=constraint.project_target.to_dict(), preferred=constraint.preferred.to_dict())
        return out


# ------------------------------------------------------------------------- fontes (conferidas na pagina em 2026-10-23)
S_IBIRAPUERA = SourceRef(
    "D", "blog/portal de conteudo", "https://www.auditorioibirapuera.com.br/qual-o-espaco-necessario-para-o-vaso-sanitario/",
    "ultima atualizacao 2023-05-18 (consultado 2026-10-23)",
    "'considere a medida de 60 cm como distancia entre a bacia sanitaria e a parede da frente'; '60 a 80 cm de circulacao "
    "entre o vaso e outros objetos'",
    "banheiro residencial, recomendacao de conforto", "nao cita norma nem fonte; recomendacao geral, nao minimo obrigatorio")
S_P5D_CIRC = SourceRef(
    "D", "blog comercial", "https://planner5d.com/blog/pt/area-de-circulacao/", "atualizado 2025-08-06 (consultado 2026-10-23)",
    "banheiro: 'entre o vaso e a parede frontal: pelo menos 60 cm'; 'entre a pia e o box: ao menos 80 cm' (recomendavel); "
    "cozinha: entre bancadas paralelas 'no minimo 1 metro'",
    "residencial, planejamento de layout",
    "cita a NBR 9050 so de forma generica (sem item); a citacao NAO e prova normativa; 80 cm e distancia pia-box, nao folga "
    "frontal do lavatorio")
S_P5D_BATH = SourceRef(
    "D", "blog comercial", "https://planner5d.com/blog/pt/tamanho-de-banheiro-padrao/",
    "publicado 2025-08-12, modificado 2026-08-27 (consultado 2026-10-23)",
    "lavatorio: 'ao menos 55 cm livres na frente para circulacao'", "banheiro residencial",
    "nao cita norma; nao da valor frontal para o vaso (a F1B atribuia erradamente o 60 cm do vaso a esta pagina)")
S_P5D_BOX = SourceRef(
    "D", "blog comercial", "https://planner5d.com/blog/pt/tamanho-box-banheiro/", "2026-01-27 (consultado 2026-10-23)",
    "'Area livre em frente ao box: pelo menos 60 cm para secagem e troca de roupa'; 'Largura minima de acesso: cerca de 60 cm "
    "livres para entrada no box, especialmente em modelos com porta de abrir'",
    "box residencial", "sem norma; a largura citada e para porta de abrir — a planta usa porta de CORRER (aplicada por analogia)")
S_CATRACA = SourceRef(
    "D", "portal de noticias", "https://catracalivre.com.br/noticias/a-que-distancia-da-parede-sao-instalados-os-moveis-da-"
    "cozinha-planejada-e-por-que-isso-e-importante/", "2026-05-15 (consultado 2026-10-23)",
    "'a passagem principal deve ter entre 90 cm e 1 m de largura'; 'frente a pia e ao fogao, recomenda-se pelo menos 1 m livre'; "
    "'Em cozinhas estreitas, um corredor de no minimo 90 cm ja permite deslocamento confortavel'",
    "cozinha residencial planejada", "nao cita estudo nem norma")
S_POLICY_090 = SourceRef(
    "E", "project_policy", "core/project_policy.py CIRCULATION_PRIMARY_TARGET_M", "decisao de 2026-08-12",
    "0,90 m para rota PRIMARY entre portais (decisao de projeto, residencial planta_74)",
    "corredor entre portais; aplicado a cozinha por analogia", "nao e NBR 9050 completa; decisao do projeto")
S_PROPOSAL = SourceRef(
    "E", "project_policy_proposal", "proposta FP-054 F1B no chat (2026-10-23)", "2026-10-23",
    "alvo de projeto proposto, ainda nao aprovado", "planta_74", "PENDING_FELIPE: nao usar como hard enquanto nao aprovado")
S_ANALOGY = SourceRef(
    "E", "heuristic", "FP-054 F1C (analogia declarada)", "2026-10-23",
    "mesma largura de passagem usada para o vaso, sem fonte propria para esta peca", "planta_74",
    "sem fonte externa; precisa de fonte ou decisao do Felipe")


def _t(v, prov, *sources, approval="N/A"):
    return Threshold(v, "m", prov, tuple(sources), approval)


_POLICY = dict(approval="PENDING_FELIPE")
FUNCTIONAL_CONSTRAINTS: dict[str, FunctionalConstraint] = {c.id: c for c in (
    FunctionalConstraint("toilet.front_clearance", "toilet", "front_depth",
                         _t(0.60, "COMFORT_GUIDE", S_IBIRAPUERA, S_P5D_CIRC),
                         _t(0.60, "PROJECT_POLICY", S_PROPOSAL, **_POLICY),
                         _t(0.80, "COMFORT_GUIDE", S_IBIRAPUERA)),
    FunctionalConstraint("toilet.reach_path", "toilet", "reach_path_width",
                         _t(0.60, "COMFORT_GUIDE", S_IBIRAPUERA),
                         _t(0.60, "PROJECT_POLICY", S_PROPOSAL, **_POLICY),
                         _t(0.80, "COMFORT_GUIDE", S_IBIRAPUERA)),
    FunctionalConstraint("lavatory.front_clearance", "lavatory", "front_depth",
                         _t(0.55, "COMFORT_GUIDE", S_P5D_BATH),
                         _t(0.60, "PROJECT_POLICY", S_PROPOSAL, **_POLICY),
                         _t(0.80, "COMFORT_GUIDE", S_P5D_CIRC)),
    FunctionalConstraint("lavatory.reach_path", "lavatory", "reach_path_width",
                         _t(0.60, "HEURISTIC", S_ANALOGY),
                         _t(0.60, "PROJECT_POLICY", S_PROPOSAL, **_POLICY),
                         _t(0.80, "HEURISTIC", S_ANALOGY)),
    FunctionalConstraint("shower.entry_front_clearance", "shower", "front_depth",
                         _t(0.60, "COMFORT_GUIDE", S_P5D_BOX),
                         _t(0.60, "PROJECT_POLICY", S_PROPOSAL, **_POLICY),
                         _t(0.80, "HEURISTIC", S_ANALOGY)),
    FunctionalConstraint("shower.entry_width", "shower", "entry_clear_width",
                         _t(0.60, "COMFORT_GUIDE", S_P5D_BOX),
                         _t(0.60, "PROJECT_POLICY", S_PROPOSAL, **_POLICY),
                         _t(0.80, "HEURISTIC", S_ANALOGY)),
    FunctionalConstraint("shower.reach_path", "shower", "reach_path_width",
                         _t(0.60, "HEURISTIC", S_ANALOGY),
                         _t(0.60, "PROJECT_POLICY", S_PROPOSAL, **_POLICY),
                         _t(0.80, "HEURISTIC", S_ANALOGY)),
    FunctionalConstraint("kitchen_counter.front_clearance", "kitchen_counter", "front_depth",
                         _t(0.90, "COMFORT_GUIDE", S_CATRACA),
                         _t(0.90, "PROJECT_POLICY", S_POLICY_090, approval="EXISTING_PROJECT_DECISION"),
                         _t(1.00, "COMFORT_GUIDE", S_CATRACA)),
    FunctionalConstraint("kitchen_counter.reach_path", "kitchen_counter", "reach_path_width",
                         _t(0.90, "COMFORT_GUIDE", S_CATRACA),
                         _t(0.90, "PROJECT_POLICY", S_POLICY_090, approval="EXISTING_PROJECT_DECISION"),
                         _t(1.00, "COMFORT_GUIDE", S_CATRACA)),
)}

# Tipo funcional por modulo (nome EXATO, tabela central editada por humano — nunca prefixo/forma). A interface vem do builder
# (semantica); o contrato geometrico abaixo so serve de FALLBACK em REPORT_ONLY e sai como HEURISTIC_GEOMETRY.
#   opposite_single_backing_wall  : exatamente 1 lado encostado (vaso; canto = ambiguo)
#   opposite_longest_backing_side : bancadas correm ao longo da parede; o lado encostado MAIS LONGO e o de apoio
#   single_free_side              : box fechado em parede/vidro; o unico lado livre (o MEIO dele nao e a porta: so heuristica)
OBJECT_TYPES: dict[str, dict] = {
    "toilet": {"modules": {("BATHROOM", "Vaso")}, "interface": "use_face",
               "fallback_contract": "opposite_single_backing_wall"},
    "lavatory": {"modules": {("BATHROOM", "Bancada")}, "interface": "use_face",
                 "fallback_contract": "opposite_longest_backing_side"},
    "shower": {"modules": {("BATHROOM", "Box")}, "interface": "shower_entry", "fallback_contract": "single_free_side"},
    "kitchen_counter": {"modules": {("KITCHEN", "countertop")}, "interface": "work_face",
                        "fallback_contract": "opposite_longest_backing_side"},
}


def constraints_for(object_type: str) -> list[FunctionalConstraint]:
    return [c for c in FUNCTIONAL_CONSTRAINTS.values() if c.object_type == object_type]


def registry_errors() -> list[str]:
    """Consistencia do registro (o que o gate REPORT_ONLY reprova): tipos, contratos, metricas, proveniencia x tier da fonte."""
    errs = []
    for t, spec in OBJECT_TYPES.items():
        if spec["fallback_contract"] not in USE_FACE_CONTRACTS:
            errs.append(f"{t}: contrato de fallback desconhecido")
        if spec["interface"] not in INTERFACE_KINDS:
            errs.append(f"{t}: interface desconhecida")
        metrics = {c.metric for c in constraints_for(t)}
        if "reach_path_width" not in metrics or not metrics - {"reach_path_width"}:
            errs.append(f"{t}: precisa de uma folga na interface E de alcance a partir do portal")
    for c in FUNCTIONAL_CONSTRAINTS.values():
        if c.object_type not in OBJECT_TYPES:
            errs.append(f"{c.id}: tipo sem registro")
        for name in ("reference_minimum", "project_target", "preferred"):
            errs += [f"{c.id}.{name}: {e}" for e in getattr(c, name).tier_errors()]
    return errs
