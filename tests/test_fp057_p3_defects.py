"""FP-057 P3: defeito novo vira Issue (sem duplicar), falha critica reordena, independente nao paralisa, contrato lista consumidores."""
from __future__ import annotations

from tools.validation import backlog_discovery as bd
from tools.validation import defect_intake as di
from tools.validation import dependency_graph as dg
from tools.validation import impact_analysis as ia
from tools.validation import issue_integrity_gate as ig

DEFECT = di.Defect(title="Jardineira atravessa a mureta h_sb001 na variante de 0,85 m", evidence="barrier_penetration 437 cm2 em tools/rooms/service/layout.py",
                   components=["tools/rooms/service/layout.py"], spec="FP-056", fase="P3", prio="P1")


def issue(n, title, body="", state="OPEN", labels=()):
    return {"number": n, "title": title, "state": state, "body": body, "labels": [{"name": x} for x in labels], "comments": []}


class Sink:
    def __init__(self):
        self.created, self.comments = [], []

    def create(self, title, labels, body):
        self.created.append((title, labels, body))
        return 900 + len(self.created)

    def comment(self, n, body):
        self.comments.append((n, body))


def test_new_defect_creates_an_issue_that_already_satisfies_the_integrity_gate():
    s = Sink()
    res = di.file_defect([issue(1, "Outra coisa qualquer")], DEFECT, s.create, s.comment)
    assert res == {"action": "CREATED", "issue": 901, "commented": False}
    title, labels, body = s.created[0]
    assert "tipo:bug" in labels and "spec:FP-056" in labels and "<!-- evidence:" in body and "tools/rooms/service/layout.py" in body
    found = ig.check({901: {"state": "OPEN", "labels": [{"name": x} for x in labels], "body": body}}, {"FP-056_x.md"})
    assert found == []                                                    # criterios de aceite presentes, SPEC conhecida


def test_duplicate_reuses_the_existing_issue_and_comments_the_new_evidence_only_once():
    s = Sink()
    existing = issue(7, "Jardineira da A.S. atravessa a mureta h_sb001", "Contexto antigo")
    first = di.file_defect([existing], DEFECT, s.create, s.comment)
    assert first["action"] == "REUSED" and first["issue"] == 7 and first["commented"] and not s.created
    existing["comments"] = [{"body": s.comments[0][1]}]                   # a evidencia ja esta registrada
    second = di.file_defect([existing], DEFECT, s.create, s.comment)
    assert second["action"] == "REUSED" and not second["commented"] and len(s.comments) == 1


def test_same_evidence_or_component_is_a_duplicate_even_with_a_different_title():
    eid = di.evidence_id(DEFECT)
    by_evidence = issue(8, "Titulo totalmente diferente", f"x <!-- evidence:{eid} -->")
    assert di.find_duplicate([by_evidence], DEFECT)["number"] == 8
    by_component = issue(9, "Barreira e jardineira no layout do servico", "mexe em tools/rooms/service/layout.py")
    assert di.find_duplicate([by_component], DEFECT)["number"] == 9
    assert di.find_duplicate([issue(10, "Banheiro sem papeleira", "outro assunto")], DEFECT) is None


def test_closed_duplicate_is_found_but_an_open_one_is_preferred():
    closed = issue(3, "Jardineira atravessa a mureta h_sb001 na variante", state="CLOSED")
    opened = issue(5, "Jardineira atravessa a mureta h_sb001 (variante 0,85)", state="OPEN")
    assert di.find_duplicate([closed], DEFECT)["number"] == 3
    assert di.find_duplicate([closed, opened], DEFECT)["number"] == 5


def test_critical_defect_in_the_same_area_or_that_invalidates_the_evidence_interrupts_but_independent_ones_do_not():
    cur = {"issue": 20, "components": ["tools/rooms/service/layout.py"], "invalidated_by": []}
    crit = di.Defect(title="x", evidence="e", components=["tools/rooms/service/layout.py"], severity="CRITICAL")
    other = di.Defect(title="y", evidence="e2", components=["tools/rooms/bathroom/layout.py"], severity="CRITICAL")
    normal = di.Defect(title="z", evidence="e3", components=["tools/rooms/service/layout.py"], severity="NORMAL")
    assert di.should_interrupt(cur, crit) and not di.should_interrupt(cur, other) and not di.should_interrupt(cur, normal)
    invalidating = {**cur, "invalidated_by": [di.evidence_id(other)]}
    assert di.should_interrupt(invalidating, other)
    assert di.should_interrupt(None, other)                                # sem tarefa corrente: trata de imediato


def test_an_independent_failure_is_registered_without_stopping_the_scheduler_selection():
    body = "**Dependências:** —\n\n## Critérios de aceite\n- [ ] x\n"
    base = [{"number": 1, "title": "Tarefa corrente", "state": "OPEN", "stateReason": None, "body": body,
             "labels": [{"name": "spec:FP-056"}, {"name": "fase:P3"}, {"name": "tipo:task"}, {"name": "prio:P1"}]},
            {"number": 2, "title": "Outra tarefa", "state": "OPEN", "stateReason": None, "body": body,
             "labels": [{"name": "spec:FP-055"}, {"name": "fase:P7"}, {"name": "tipo:task"}, {"name": "prio:P2"}]}]
    s = Sink()
    di.file_defect(base, di.Defect(title="Defeito independente em outro cômodo", evidence="e", severity="NORMAL"), s.create, s.comment)
    assert len(s.created) == 1
    new_issue = {"number": 901, "title": s.created[0][0], "state": "OPEN", "stateReason": None, "body": s.created[0][2],
                 "labels": [{"name": x} for x in s.created[0][1]]}
    verdicts = bd.evaluate(dg.build(base + [new_issue]))
    assert {v.node.number for v in verdicts if v.eligible} == {1, 2, 901}      # nova Issue entra no backlog; nada para


def test_critical_new_defect_is_ranked_ahead_of_the_rest_by_the_spec_priority():
    body = "**Dependências:** —\n\n## Critérios de aceite\n- [ ] x\n"
    mk = lambda n, t, labels: {"number": n, "title": t, "state": "OPEN", "stateReason": None, "body": body,    # noqa: E731
                               "labels": [{"name": x} for x in labels]}
    issues = [mk(1, "Melhoria de acabamento", ["tipo:story", "prio:P3"]),
              mk(2, "Gate aceita PASS vazio sem medir", ["tipo:bug", "prio:P1", "spec:FP-056"]),
              mk(3, "Escritor grava em artifacts/ sem gate (oficial)", ["tipo:bug", "prio:P0", "spec:FP-055"])]
    order = [v.node.number for v in bd.evaluate(dg.build(issues)) if v.eligible]
    assert order[:2] == [3, 2] and order[-1] == 1


# ------------------------------------------------------------------------------------------------ impacto
FILES = {
    "core/pipeline_contracts.py": "class GenerationRequest: ...",
    "tools/orchestration/a.py": "from core.pipeline_contracts import GenerationRequest\n",
    "tools/orchestration/b.py": "import core.pipeline_contracts as pc\n",
    "tools/validation/c.py": "from core import pipeline_contracts\n",
    "tools/validation/solo.py": "x = 1\n",
    "tests/test_a.py": "from tools.orchestration.a import main\nfrom core.pipeline_contracts import GenerationRequest\n",
    "docs/specs/FP-055_x.md": "o contrato `core/pipeline_contracts.py` define GenerationRequest",
    "docs/specs/FP-056_y.md": "nada a ver com isso",
}


def test_contract_change_lists_consumers_tests_specs_and_open_issues_without_touching_unrelated_ones():
    issues = [issue(30, "Ajustar core/pipeline_contracts.py", state="OPEN"), issue(31, "Outro assunto", state="OPEN"),
              issue(32, "core.pipeline_contracts antigo", state="CLOSED")]
    imp = ia.analyze(["core/pipeline_contracts.py"], FILES, issues)
    assert imp.contract_change
    assert imp.consumers == ["tools/orchestration/a.py", "tools/orchestration/b.py", "tools/validation/c.py"]
    assert imp.tests == ["tests/test_a.py"] and imp.specs == ["docs/specs/FP-055_x.md"] and imp.issues == [30]


def test_non_contract_change_only_lists_its_own_consumers():
    imp = ia.analyze(["tools/orchestration/a.py"], FILES, [])
    assert not imp.contract_change and imp.tests == ["tests/test_a.py"] and imp.consumers == [] and imp.specs == []
    assert ia.analyze(["tools/validation/solo.py"], FILES, []).consumers == []


def test_spec_change_is_a_contract_change_and_summary_is_readable():
    imp = ia.analyze(["docs/specs/FP-056_y.md"], FILES, [])
    assert imp.contract_change and "contrato=SIM" in imp.summary()
