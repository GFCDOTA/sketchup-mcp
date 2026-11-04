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
    command: str = ""               # linha de comando resumida do processo atribuido (sem segredos)

    def line(self) -> str:
        pid = f" pid {self.pid}" if self.pid else ""
        return f"{self.name}: {self.label}{pid}" + (f" - {self.detail}" if self.detail else "")


@dataclass(frozen=True)
class Event:
    at: str
    action: str
    item: str
    reason: str = ""


@dataclass(frozen=True)
class GroupedEvent:
    """Eventos consecutivos identicos (mesma acao/item/motivo) viram UMA linha com contagem (sem spam de DRY_RUN)."""
    first_at: str
    last_at: str
    action: str
    item: str
    reason: str
    count: int
    error: bool

    def pr_label(self) -> str:
        parts = self.item.split(":")
        return f"PR #{parts[2]}" if len(parts) > 2 and parts[2].isdigit() else self.item


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
    lock_status: str = "indisponivel"                  # correlacao do lock com processos reais
    last_error: str | None = None
    events: list[GroupedEvent] = field(default_factory=list)
    backlog: dict[str, int | None] = field(default_factory=dict)
    backlog_error: str | None = None
    backlog_synced: str | None = None                  # ISO UTC da ultima leitura bem-sucedida
    github_checks: str = "indisponivel"
    executor_summary: str = "indisponivel"             # fila/tentativas/execucoes 24 h
    work: str = "indisponivel"                         # "monitorando" | "trabalhando" | ...
    review_ref: str = ""                               # review/SHA atual da fila
    log_path: str | None = None

    def agents(self) -> list[AgentStatus]:
        return [self.claude, self.codex, self.listener, self.github]

    def mode_banner(self) -> str:
        if self.mode == "DRY_RUN":
            return "DRY_RUN — execução automática desligada"
        if self.mode == "EXECUTE":
            return "EXECUTE — execução automática LIGADA"
        return "modo indisponível"

    def diagnostic(self) -> str:
        """Texto para a area de transferencia. Sem segredos: so estado observado."""
        def n(v, suffix=""):
            return "indisponivel" if v is None else f"{v}{suffix}"
        rows = [f"Agent bar snapshot {self.at}"]
        rows += [a.line() + (f" | cmd: {a.command}" if a.command else "") + (f" | inicio: {a.since}" if a.since else "") for a in self.agents()]
        rows += [f"modo: {self.mode_banner()}", f"trabalho: {self.work}", f"PR atual: {self.pr if self.pr else 'indisponivel'}",
                 f"review/SHA: {self.review_ref or 'indisponivel'}", f"checks: {self.github_checks}",
                 f"heartbeat: {n(self.heartbeat_age_s, 's')}",
                 f"kill switch: {'indisponivel' if self.kill_switch is None else ('ATIVO' if self.kill_switch else 'inativo')}",
                 f"instancias do executor: {n(self.concurrent_instances)}", f"lock: {self.lock_holder or 'indisponivel'} ({self.lock_status})",
                 f"executor: {self.executor_summary}",
                 "backlog: " + (", ".join(f"{k}={n(v)}" for k, v in self.backlog.items()) if self.backlog else "indisponivel")
                 + (f" (erro: {self.backlog_error})" if self.backlog_error else f" (sync {self.backlog_synced or 'nunca'})"),
                 f"ultimo erro: {self.last_error or 'nenhum observado'}", f"log: {self.log_path or 'indisponivel'}"]
        rows += [f"  {e.last_at} {e.action} {e.pr_label()} x{e.count} {e.reason}".rstrip() for e in self.events[:10]]
        return "\n".join(rows)
