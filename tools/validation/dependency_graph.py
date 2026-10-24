"""dependency_graph.py — grafo de dependencias do backlog (FP-057 P1).

EPIC -> STORY -> TASK/BUG: a hierarquia (Epic pai) e **organizacao**, nao bloqueio. Uma dependencia so bloqueia quando representa uma
condicao concreta (outra Issue nao-Epic que precisa fechar). Este modulo so le Issues (dicts de `gh issue list --json
number,title,state,stateReason,labels,body`) e devolve fatos; nao escreve nada.

Achados (`GraphFinding.code`):
- DEP_MISSING        `#N` citado em `**Dependências:**` (so o que vem antes de ` · `: "relacionada"/"bloqueia" sao informativos) que nao existe;
- DEP_SELF           Issue depende dela mesma;
- DEP_CYCLE          ciclo entre Issues nao-Epic (lista o ciclo);
- DEP_RESOLVED       dependencia ja fechada como concluida (informativo: reavaliar dependentes);
- DEP_EPIC_BLOCKER   bloqueio `dependency` que so aponta para Epic (Epic aberta nao bloqueia filhas);
- BLOCK_STALE        `bloqueio:dependency` sem nenhuma dependencia aberta nao-Epic: o bloqueio acabou;
- BLOCK_MISCLASSIFIED  titulo `DECISÃO …` marcado como technical/dependency, ou `bloqueio:human-decision` num item cujo titulo
                     nao e decisao e que tem dependencia tecnica aberta (a decisao humana nao e o bloqueio real).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_DEPS = re.compile(r"\*\*Dependências:\*\*\s*(.*)")
_CHECK = re.compile(r"^\s*-\s*\[[ xX]\]\s*\S", re.MULTILINE)
_OPEN_CRIT = re.compile(r"^\s*-\s*\[ \]\s*(.+)$", re.MULTILINE)
_HUMAN_CRIT = re.compile(r"Felipe|propriet[aá]rio|veredito visual|decis[ãa]o d[oe]", re.IGNORECASE)


@dataclass(frozen=True)
class Node:
    number: int
    title: str
    state: str                       # OPEN | CLOSED
    completed: bool                  # fechada como concluida (nao "not planned")
    kind: str                        # epic | story | bug | task | technical-debt | ?
    prio: str                        # P0..P3 | ?
    labels: frozenset
    cause: str | None                # bloqueio:<causa>
    blocked: bool
    human_flag: bool
    spec: str | None
    fase: str | None
    deps: tuple[int, ...]
    has_acceptance: bool
    human_only_open_criteria: bool = False   # todo criterio ainda aberto depende do proprietario (veredito, decisao)
    status: str | None = None        # Status do Project, quando conhecido


def component(node: Node) -> str:
    """Chave grossa de componente para detectar trabalho concorrente na mesma area (SPEC + fase)."""
    return f"{node.spec or '-'}|{node.fase or '-'}"


@dataclass(frozen=True)
class GraphFinding:
    code: str
    issue: int
    detail: str

    def __str__(self) -> str:
        return f"#{self.issue} {self.code}: {self.detail}"


@dataclass
class Graph:
    nodes: dict[int, Node]
    children: dict[int, set[int]] = field(default_factory=dict)     # dependente por dependencia (quem espera quem)

    def hard_deps(self, n: int) -> list[int]:
        """Dependencias que realmente bloqueiam: existentes, nao-Epic."""
        return [d for d in self.nodes[n].deps if d in self.nodes and self.nodes[d].kind != "epic" and d != n]

    def open_hard_deps(self, n: int) -> list[int]:
        return [d for d in self.hard_deps(n) if not self.nodes[d].completed]

    def dependents(self, n: int) -> set[int]:
        """Dependentes transitivos abertos (tamanho = quanto o item destrava: caminho critico)."""
        seen: set[int] = set()
        stack = [n]
        while stack:
            cur = stack.pop()
            for c in self.children.get(cur, ()):
                if c not in seen and self.nodes[c].state == "OPEN":
                    seen.add(c)
                    stack.append(c)
        return seen


def parse(issue: dict, status: str | None = None) -> Node:
    names = {lab["name"] for lab in issue.get("labels", [])}
    body = issue.get("body") or ""
    m = _DEPS.search(body)
    deps = tuple(dict.fromkeys(int(x) for x in re.findall(r"#(\d+)", m.group(1).split("·")[0]))) if m else ()
    pick = lambda p: next((n.split(":", 1)[1] for n in sorted(names) if n.startswith(p)), None)    # noqa: E731
    acc = re.search(r"crit[ée]rios? de aceite", body, re.I)
    open_items = _OPEN_CRIT.findall(body[acc.start():]) if acc else []
    return Node(number=issue["number"], title=issue.get("title", ""), state=issue.get("state", "OPEN"),
                completed=issue.get("state") == "CLOSED" and issue.get("stateReason", "COMPLETED") == "COMPLETED",
                kind=pick("tipo:") or "?", prio=pick("prio:") or "?", labels=frozenset(names), cause=pick("bloqueio:"),
                blocked="blocked" in names, human_flag="aprovação-humana-pendente" in names, spec=pick("spec:"), fase=pick("fase:"), deps=deps,
                has_acceptance=bool(acc and _CHECK.search(body[acc.start():])),
                human_only_open_criteria=bool(open_items) and all(_HUMAN_CRIT.search(x) for x in open_items), status=status)


def build(issues: list[dict], statuses: dict[int, str] | None = None) -> Graph:
    nodes = {i["number"]: parse(i, (statuses or {}).get(i["number"])) for i in issues}
    g = Graph(nodes)
    for n, node in nodes.items():
        for d in node.deps:
            if d in nodes and d != n:
                g.children.setdefault(d, set()).add(n)
    return g


def _cycles(g: Graph) -> list[list[int]]:
    """Ciclos entre Issues nao-Epic (DFS com pilha; cada ciclo uma vez, na ordem canonica)."""
    adj = {n: g.hard_deps(n) for n in g.nodes if g.nodes[n].kind != "epic"}
    out, seen_cycles = [], set()
    color: dict[int, int] = {}

    def dfs(u: int, path: list[int]) -> None:
        color[u] = 1
        path.append(u)
        for v in adj.get(u, ()):
            if color.get(v, 0) == 0:
                dfs(v, path)
            elif color.get(v) == 1:
                cyc = path[path.index(v):]
                key = tuple(sorted(cyc))
                if key not in seen_cycles:
                    seen_cycles.add(key)
                    out.append(cyc + [v])
        path.pop()
        color[u] = 2

    for n in sorted(adj):
        if color.get(n, 0) == 0:
            dfs(n, [])
    return out


def analyze(g: Graph) -> list[GraphFinding]:
    f: list[GraphFinding] = []
    for n, node in sorted(g.nodes.items()):
        for d in node.deps:
            if d == n:
                f.append(GraphFinding("DEP_SELF", n, "depende de si mesma"))
            elif d not in g.nodes:
                f.append(GraphFinding("DEP_MISSING", n, f"#{d} nao existe"))
            elif g.nodes[d].completed and g.nodes[d].kind != "epic" and node.state == "OPEN":
                f.append(GraphFinding("DEP_RESOLVED", n, f"#{d} ja concluida: reavaliar"))
        if node.state == "OPEN" and node.blocked and node.cause == "dependency":
            real = [d for d in node.deps if d in g.nodes and g.nodes[d].kind != "epic"]
            if not real and node.deps:
                f.append(GraphFinding("DEP_EPIC_BLOCKER", n, "bloqueio de dependencia que so aponta para Epic"))
            elif not g.open_hard_deps(n):
                f.append(GraphFinding("BLOCK_STALE", n, "nenhuma dependencia aberta: o bloqueio acabou"))
        if node.state == "OPEN" and node.blocked:
            is_decision = bool(re.match(r"\s*(DECIS[ÃA]O|REVIS[ÃA]O VISUAL)\b", node.title, re.I))
            if is_decision and node.cause == "technical":
                f.append(GraphFinding("BLOCK_MISCLASSIFIED", n, "titulo de decisao com bloqueio technical"))
            if node.cause == "human-decision" and not is_decision and g.open_hard_deps(n):
                f.append(GraphFinding("BLOCK_MISCLASSIFIED", n, f"decisao humana, mas ha dependencia tecnica aberta {g.open_hard_deps(n)}"))
    for cyc in _cycles(g):
        f.append(GraphFinding("DEP_CYCLE", cyc[0], " -> ".join(f"#{x}" for x in cyc)))
    return f


def parallel_groups(g: Graph, candidates: list[int]) -> list[list[int]]:
    """Particiona candidatos em grupos que podem rodar em paralelo: item de um grupo nao depende (direta ou transitivamente)
    de outro candidato do mesmo grupo. Guloso, na ordem dada (a prioridade ja foi decidida por quem chama)."""
    def reach(n: int) -> set[int]:
        out, stack = set(), list(g.hard_deps(n))
        while stack:
            x = stack.pop()
            if x not in out:
                out.add(x)
                stack.extend(g.hard_deps(x))
        return out
    groups: list[list[int]] = []
    for c in candidates:
        for grp in groups:
            if all(c not in reach(m) and m not in reach(c) for m in grp):
                grp.append(c)
                break
        else:
            groups.append([c])
    return groups
