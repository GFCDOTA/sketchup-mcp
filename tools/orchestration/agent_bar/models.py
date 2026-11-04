"""models.py — estado tipado da barra de agentes (FP-058, refs FP-057/#589). Sem Qt, sem I/O."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Level(str, Enum):
    GREEN = "green"      # operacional / trabalhando normalmente
    BLUE = "blue"        # executando tarefa
    YELLOW = "yellow"    # aguardando, ocioso, dependencia pendente, estado ambiguo
    RED = "red"          # erro ou interrupcao inesperada
    GRAY = "gray"        # desligado, desconhecido, nao configurado ou nao integrado (NUNCA sucesso)


@dataclass(frozen=True)
class AgentStatus:
    name: str
    level: Level
    label: str                      # curto: aparece na barra/tooltip
    detail: str = ""                # uma linha de evidencia (de onde veio o dado)
    pid: int | None = None
    since: str | None = None        # ISO UTC do inicio do processo, quando conhecido

    def line(self) -> str:
        pid = f" pid {self.pid}" if self.pid else ""
        return f"{self.name}: {self.label}{pid}" + (f" - {self.detail}" if self.detail else "")


@dataclass(frozen=True)
class Event:
    at: str
    action: str
    item: str
    reason: str = ""


@dataclass
class Snapshot:
    at: str
    claude: AgentStatus
    codex: AgentStatus
    listener: AgentStatus
    github: AgentStatus
    pr: int | None = None
    pr_url: str | None = None
    mode: str = "indisponivel"                         # DRY_RUN | EXECUTE | indisponivel
    heartbeat_age_s: int | None = None
    kill_switch: bool | None = None                    # None = nao observavel
    concurrent_instances: int | None = None
    lock_holder: str | None = None
    last_error: str | None = None
    events: list[Event] = field(default_factory=list)
    backlog: dict[str, int | None] = field(default_factory=dict)
    github_checks: str = "indisponivel"

    def agents(self) -> list[AgentStatus]:
        return [self.claude, self.codex, self.listener, self.github]

    def diagnostic(self) -> str:
        """Texto para a area de transferencia. Sem segredos: so estado observado."""
        rows = [f"Agent bar snapshot {self.at}"]
        rows += [a.line() for a in self.agents()]
        rows += [f"modo: {self.mode}", f"PR atual: {self.pr if self.pr else 'indisponivel'}", f"checks: {self.github_checks}",
                 f"heartbeat: {'indisponivel' if self.heartbeat_age_s is None else str(self.heartbeat_age_s) + 's'}",
                 f"kill switch: {'indisponivel' if self.kill_switch is None else ('ATIVO' if self.kill_switch else 'inativo')}",
                 f"instancias do executor: {'indisponivel' if self.concurrent_instances is None else self.concurrent_instances}",
                 f"ultimo erro: {self.last_error or 'nenhum observado'}"]
        rows += [f"  {e.at} {e.action} {e.item} {e.reason}".rstrip() for e in self.events[:10]]
        return "\n".join(rows)
