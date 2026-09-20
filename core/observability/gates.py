"""gates — FASE 2: normaliza os cinco formatos de saída dos gates em UM.

Os gates determinísticos deste repo cresceram em épocas diferentes e devolvem
formas incompatíveis:

    run_deterministic_gates.run_all  {"overall": ..., "gates": {nome: sub}}
    circulation_gate                 {"result": ..., "room": ..., "checks": {...}}
    furniture_overlap_gate           {"result": ..., "fails": [...], "warns": [...]}
    semantic_geometry_contract_gate  {"overall": ..., "n_parts": ..., "findings": [...]}
    opening_host_audit               {"overall": ..., "n_fail": ..., "n_openings": ...}
    wall_presence (sem sidecar)      {"verdict": "SKIPPED_NO_SIDECAR", "reason": ...}

Sem esta camada o grafo do Inspector teria que adivinhar onde está o veredito de
cada gate — e adivinhar errado significa desenhar um nó verde sobre um FAIL. Por
isso a normalização vem ANTES da UI no plano, não depois.

DUAS REGRAS DE SEGURANÇA
------------------------
1. **Veredito ausente ou desconhecido vira UNKNOWN, nunca PASS.** Um gate que
   mudou de formato e passou a devolver uma chave que não conhecemos precisa
   acender a luz, não sumir do radar. `SKIPPED != PASS` pela mesma razão — o
   próprio `run_all` já aprendeu isso (LL-035) e trata sidecar ausente como
   INCOMPLETE em vez de deixar o CI passar.
2. **Medida ausente é ausência, nunca zero.** Se o formato não expõe o valor
   medido, `measured=None` e a UI escreve "não instrumentado". Preencher com 0.0
   produziria um card "0 cm medido / 60 cm exigido" — uma mentira com aparência
   de dado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# status canônico
# ---------------------------------------------------------------------------

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
INCOMPLETE = "INCOMPLETE"
SKIPPED = "SKIPPED"
UNKNOWN = "UNKNOWN"

# Severidade decrescente. UNKNOWN fica logo abaixo de FAIL de propósito: "não sei
# o que este gate disse" é quase tão grave quanto "reprovou", e muito mais grave
# que "avisou".
SEVERITY: tuple[str, ...] = (FAIL, UNKNOWN, INCOMPLETE, WARN, SKIPPED, PASS)

_STATUS_ALIASES: dict[str, str] = {
    "PASS": PASS, "OK": PASS, "GREEN": PASS,
    "WARN": WARN, "WARNING": WARN,
    "FAIL": FAIL, "FAILED": FAIL, "RED": FAIL,
    "INCOMPLETE": INCOMPLETE,
}

# ordem de precedência das chaves de veredito (a primeira presente vence)
_VERDICT_KEYS = ("overall", "result", "verdict", "status")

_ROOM_KEYS = ("room", "room_id", "roomId")
_COUNT_KEYS = ("n_fail", "n_total", "n_pass", "n_parts", "n_openings",
               "n_modules", "n_findings")
_FINDING_KEYS = ("fails", "warns", "findings", "errors")

# vocabulário EXPLÍCITO de medida. Heurística genérica sobre `*_m` traria lixo
# (`tol_pt`, `pt_to_m`) travestido de medição.
_REQUIRED_KEYS: dict[str, str] = {
    "min_m": "m", "recuo_m": "m", "required_m": "m", "min_clearance_m": "m",
    "min_area_m2": "m²", "target_m": "m",
}
_MEASURED_KEYS: dict[str, str] = {
    "livre_atras_m": "m", "measured_m": "m", "clearance_m": "m", "gap_m": "m",
    "dist_m": "m", "largura_m": "m", "area_m2": "m²", "free_m": "m",
}
_ENTITY_KEYS = ("entity_ref", "entityRef", "module", "cadeira", "id", "name",
                "label", "kind")


def normalize_status(raw: Any) -> tuple[str, str | None]:
    """(status canônico, motivo). Desconhecido -> UNKNOWN com o valor cru no motivo."""
    if raw is None:
        return UNKNOWN, "gate não expôs veredito em nenhuma chave conhecida"
    token = str(raw).strip().upper()
    if token in _STATUS_ALIASES:
        return _STATUS_ALIASES[token], None
    if token.startswith("SKIPPED"):
        return SKIPPED, str(raw)
    return UNKNOWN, f"veredito não reconhecido: {raw!r}"


def worst(statuses: Iterable[str]) -> str:
    """Agrega vereditos pela severidade declarada. Vazio -> UNKNOWN."""
    seen = [s for s in statuses if s in SEVERITY]
    if not seen:
        return UNKNOWN
    return min(seen, key=SEVERITY.index)


# ---------------------------------------------------------------------------
# forma canônica
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Measurement:
    """Uma comparação medida-vs-exigida. É o que vira o card do gate na UI."""

    metric: str
    measured: float | None
    required: float | None
    unit: str
    status: str = UNKNOWN
    entity_ref: str | None = None

    @property
    def slack(self) -> float | None:
        """Folga (medido − exigido). None se qualquer lado faltar."""
        if self.measured is None or self.required is None:
            return None
        return round(self.measured - self.required, 4)

    def to_meta(self) -> dict[str, Any]:
        return {"metric": self.metric, "measured": self.measured,
                "required": self.required, "unit": self.unit,
                "status": self.status, "entityRef": self.entity_ref}


@dataclass(frozen=True)
class NormalizedGate:
    name: str
    status: str
    room: str | None = None
    measurements: tuple[Measurement, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)
    findings: tuple[str, ...] = ()
    reason: str | None = None
    raw_verdict: Any = None

    def to_meta(self) -> dict[str, Any]:
        """Payload leve pro evento: contagens e medidas, não a lista de achados."""
        meta: dict[str, Any] = {"gate": self.name, "verdict": self.status}
        if self.room:
            meta["room"] = self.room
        if self.counts:
            meta["counts"] = dict(self.counts)
        if self.measurements:
            meta["measurements"] = [m.to_meta() for m in self.measurements]
        if self.reason:
            meta["reason"] = self.reason
        if self.findings:
            meta["nFail"] = self.counts.get("n_fail", len(self.findings))
        return meta


# ---------------------------------------------------------------------------
# extração
# ---------------------------------------------------------------------------


def _first_key(d: dict, keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _as_float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # descarta NaN


def _entity_of(d: dict) -> str | None:
    for k in _ENTITY_KEYS:
        v = d.get(k)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, (list, tuple)) and v:
            return str(list(v))
    return None


def _measurement_from_check(metric: str, check: dict) -> Measurement | None:
    """Extrai UMA medição de um sub-check. Nada reconhecível -> None (não inventa)."""
    required = unit = None
    for key, u in _REQUIRED_KEYS.items():
        if key in check:
            required, unit = _as_float(check[key]), u
            break

    measured: float | None = None
    entity: str | None = None
    for key, u in _MEASURED_KEYS.items():
        if key in check:
            measured, unit = _as_float(check[key]), unit or u
            entity = _entity_of(check)
            break

    if measured is None:
        # varre listas aninhadas (ex.: circulation_gate -> checks.cadeiras[]) e
        # fica com o PIOR caso: é ele que explica o veredito.
        worst_val: float | None = None
        worst_entity: str | None = None
        for value in check.values():
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict):
                    continue
                for key, u in _MEASURED_KEYS.items():
                    if key in item:
                        cand = _as_float(item[key])
                        if cand is not None and (worst_val is None or cand < worst_val):
                            worst_val, worst_entity, unit = cand, _entity_of(item), unit or u
        measured, entity = worst_val, worst_entity

    if measured is None and required is None:
        return None
    status, _ = normalize_status(_first_key(check, _VERDICT_KEYS))
    return Measurement(metric=metric, measured=measured, required=required,
                       unit=unit or "", status=status, entity_ref=entity)


def _collect_findings(raw: dict) -> tuple[tuple[str, ...], dict[str, int]]:
    findings: list[str] = []
    counts: dict[str, int] = {}
    for key in _FINDING_KEYS:
        value = raw.get(key)
        if not isinstance(value, list):
            continue
        counts[f"n_{key}"] = len(value)
        for item in value:
            if isinstance(item, str):
                findings.append(item)
            elif isinstance(item, dict):
                findings.append(str(_first_key(item, ("detail", "message", "msg", "type"))
                                    or item))
    for key in _COUNT_KEYS:
        if isinstance(raw.get(key), int):
            counts[key] = raw[key]
    return tuple(findings), counts


def normalize_one(name: str, raw: Any) -> NormalizedGate:
    """Normaliza UM resultado de gate (sem descer em sub-gates)."""
    if not isinstance(raw, dict):
        return NormalizedGate(name=name, status=UNKNOWN, raw_verdict=raw,
                              reason=f"resultado não é dict: {type(raw).__name__}")

    verdict = _first_key(raw, _VERDICT_KEYS)
    status, reason = normalize_status(verdict)
    findings, counts = _collect_findings(raw)

    measurements: list[Measurement] = []
    checks = raw.get("checks")
    if isinstance(checks, dict):
        for metric, check in sorted(checks.items()):
            if isinstance(check, dict):
                m = _measurement_from_check(metric, check)
                if m is not None:
                    measurements.append(m)
    else:
        m = _measurement_from_check(name, raw)
        if m is not None:
            measurements.append(m)

    # veredito ausente mas sub-checks presentes: agrega em vez de dizer UNKNOWN
    if status is UNKNOWN and verdict is None and isinstance(checks, dict):
        sub = [normalize_status(_first_key(c, _VERDICT_KEYS))[0]
               for c in checks.values() if isinstance(c, dict)]
        if sub:
            status, reason = worst(sub), "veredito derivado dos sub-checks"

    # A explicação do PRÓPRIO gate vence a nota do normalizador: "projection
    # sidecar missing; rebuild or promote_canonical to emit it" diz o que fazer;
    # "SKIPPED_NO_SIDECAR" só repete o veredito, que já está em `raw_verdict`.
    explicit = raw.get("reason")
    if isinstance(explicit, str) and explicit:
        reason = explicit

    return NormalizedGate(
        name=name, status=status,
        room=_first_key(raw, _ROOM_KEYS),
        measurements=tuple(measurements), counts=counts,
        findings=findings, reason=reason, raw_verdict=verdict,
    )


def normalize(name: str, raw: Any) -> list[NormalizedGate]:
    """Achata um resultado, descendo no `gates` aninhado do `run_all`.

    Devolve o agregado PRIMEIRO, seguido dos filhos — a UI desenha o pai como
    nó e os filhos como sub-nós, e o replay preserva essa ordem.
    """
    out = [normalize_one(name, raw)]
    if isinstance(raw, dict) and isinstance(raw.get("gates"), dict):
        for sub_name, sub in sorted(raw["gates"].items()):
            out.extend(normalize(sub_name, sub))
    return out


# ---------------------------------------------------------------------------
# ponte com os eventos
# ---------------------------------------------------------------------------

_EVENT_BY_STATUS = {
    PASS: ("gate.passed", "ok"),
    WARN: ("gate.passed", "degraded"),
    FAIL: ("gate.failed", "failed"),
    INCOMPLETE: ("gate.incomplete", "degraded"),
    SKIPPED: ("gate.skipped", "skipped"),
    UNKNOWN: ("gate.incomplete", "degraded"),
}


def emit_gate(gate: NormalizedGate, *, component: str | None = None) -> None:
    """Emite `gate.*` + um `gate.measurement` por medição. No-op se desligado."""
    from core import observability as obs

    if not obs.is_enabled():
        return
    name, status = _EVENT_BY_STATUS[gate.status]
    comp = component or f"gate.{gate.name}"
    obs.emit(name, component=comp, status=status, meta=gate.to_meta())
    for m in gate.measurements:
        obs.emit("gate.measurement", component=comp, status="ok", meta=m.to_meta())


def emit_all(name: str, raw: Any, *, component: str | None = None) -> list[NormalizedGate]:
    """Normaliza e emite de uma vez. Devolve os gates normalizados."""
    gates = normalize(name, raw)
    for g in gates:
        emit_gate(g, component=component)
    return gates
