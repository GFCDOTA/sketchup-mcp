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
    store: dict = field(default_factory=lambda: {"state": "indisponivel", "error": "nao coletado"})   # EventStore (SQLite) lido somente leitura

    def store_line(self) -> str:
        """Uma linha honesta do EventStore. So `ok` sem DLQ nem lease morto e saudavel; ausente/indisponivel NUNCA parece saudavel."""
        st = self.store or {}
        from tools.orchestration.agent_bar.collectors import redact_secrets
        if st.get("state") != "ok":                                        # o erro cita nomes de arquivo/diretorio configurados: tambem passa pela redacao
            return f"EventStore {redact_secrets(st.get('state', 'indisponivel'))}: {redact_secrets(st.get('error') or 'sem leitura')} (NAO e saudavel)"
        c = st["counts"]
        live = ", ".join(f"{redact_secrets(x['owner'])} ({x['seconds_left']}s)" for x in st["live_leases"]) or "nenhum"
        line = (f"EventStore: {c.get('PENDING', 0)} pendente(s) ({st['backoff']} em backoff), {c.get('RUNNING', 0)} rodando, "
                f"DLQ {c.get('DLQ', 0)}, retries {st['retries']}; leases vivos: {live}")
        if st["zombies"]:
            line += f"; ATENCAO {st['zombies']} RUNNING com lease vencido (worker morto?)"
        if st["dlq"]:
            line += "; DLQ: " + "; ".join(f"#{x['id']} {redact_secrets(x['key'])[:40]}" for x in st["dlq"][:3])
        if st["last_error"]:
            line += f"; ultimo erro: {redact_secrets(st['last_error']['error'])[:120]}"
        ob = st.get("outbox") or {}
        oc = ob.get("counts", {})
        line += f"; outbox: {oc.get('PENDING', 0)} pendente(s), {oc.get('RUNNING', 0)} rodando, DLQ {oc.get('DLQ', 0)}"
        if ob.get("zombies"):
            line += f"; ATENCAO {ob['zombies']} publicacao(oes) da outbox com lease vencido"
        dead = ob.get("dlq", [])
        if dead:                                                                          # SEM evidencia persistida de falha remota DEFINITIVA, nunca afirmar perda: o remoto pode ter aplicado
            line += "; PUBLICACAO NA DLQ DA OUTBOX (resultado remoto possivelmente desconhecido: reconciliar com o GitHub ANTES de republicar): " + "; ".join(
                f"#{x['id']} {redact_secrets(x['target'])[:20]} {redact_secrets(x['key'])[:40]}" for x in dead[:3])
        return line

    def store_ok(self) -> bool:
        st = self.store or {}
        ob = st.get("outbox")
        return st.get("state") == "ok" and not st["dlq"] and not st["zombies"] and isinstance(ob, dict) and not ob.get("dlq") and not ob.get("zombies")      # sem leitura da outbox: nao e saudavel

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
                 f"ultimo erro: {self.last_error or 'nenhum observado'}", f"log: {self.log_path or 'indisponivel'}", self.store_line()]
        rows += [f"  {e.last_at} {e.action} {e.pr_label()} x{e.count} {e.reason}".rstrip() for e in self.events[:10]]
        return "\n".join(rows)
