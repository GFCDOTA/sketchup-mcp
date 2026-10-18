"""project_policy.py — thresholds numéricos com PROVENANCE (value/source/scope/
applicability), separados do "motor" (circulation_gate.py). Achado 2026-08-12,
revisão GPT-Docker: "0.90/0.80/0.75/0.02/0.70/0.50 são policy de PROJETO
(apê residencial planta_74), não lei universal do engine — outro projeto pode
exigir acessibilidade integral (NBR 9050 completa) e usar outros números.
Não hardcode no engine."

Cada entrada é um NumericPolicy(value, source, scope, applicability). O
motor (circulation_gate.py) importa só o `.value` pra fazer conta; o resto é
metadado consultável (ex. por uma futura auditoria "essa regra é aplicável
aqui?" ou por docs/interview-study/).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NumericPolicy:
    value: float
    source: str            # office_rule | manufacturer | standard | client_requirement | project_decision
    scope: str              # onde essa regra vale (ex. "apartamento residencial, sem exigência de acessibilidade")
    applicability: str       # quando NÃO aplicar / quando revisar


CIRCULATION_PRIMARY_TARGET_M = NumericPolicy(
    value=0.90,
    source="project_decision",
    scope="residencial planta_74 — rota PRIMARY (espinha de distribuição: porta que liga a outro cômodo)",
    applicability="NÃO é NBR 9050 completa (essa pede 0.90m pra rota ACESSÍVEL — usamos o mesmo número "
                  "por prudência de projeto, não porque o apê tem exigência de acessibilidade integral). "
                  "Revisar se o programa do apê mudar pra unidade adaptável/PCD.",
)
CIRCULATION_SECONDARY_TARGET_M = NumericPolicy(
    value=0.80,
    source="project_decision",
    scope="residencial planta_74 — rota SECONDARY (destino terminal: varanda/janela, não é passagem "
          "obrigatória de ninguém) OU rota PRIMARY cujo shell vazio só sustenta 0.80-0.90 (gargalo herdado)",
    applicability="Decisão GPT-Docker 2026-08-12 (consulta arquitetônica): destino terminal nunca "
                  "precisa da mesma largura que espinha de distribuição. Não é norma — é julgamento "
                  "de projeto pra apê compacto sem exigência de acessibilidade.",
)
CIRCULATION_SHELL_FLOOR_M = NumericPolicy(
    value=0.75,
    source="project_decision",
    scope="piso abaixo do qual a PLANTA (não a mobília) já é estreita demais — Hard Rule #1 "
          "(nunca inventar/alargar parede) faz esse caso virar WARN, não FAIL, se a mobília não piorar",
    applicability="Achado empírico planta_74 (não uma norma): abaixo disso, documentar como "
                  "constraint da planta, não tentar resolver com posição de móvel.",
)
CIRCULATION_GEOMETRY_TOLERANCE_M = NumericPolicy(
    value=0.02,
    source="project_decision",
    scope="tolerância numérica/de modelagem (arredondamento da busca binária de bottleneck_width, "
          "tol=0.01m, + folga) — não é 'perdão ergonômico', é margem de ruído geométrico",
    applicability="Se o método de medição de largura mudar (ex. de erosão-shapely pra outra técnica), "
                  "revisar junto.",
)
BEHIND_CHAIR_M = NumericPolicy(
    value=0.70,
    source="office_rule",
    scope="ergonomia de jantar — espaço pra puxar a cadeira e alguém passar atrás de quem está sentado",
    applicability="Regra de escritório (dining ergonomics), não lei espacial global — um banco de "
                  "cozinha ou uma cadeira de escritório podem ter regra diferente.",
)
CHAIR_PULL_M = NumericPolicy(
    value=0.50,
    source="office_rule",
    scope="ergonomia de jantar — recuo da cadeira PUXADA a partir da mesa antes de sentar",
    applicability="Mesma categoria de BEHIND_CHAIR_M — regra de dining, não global.",
)
