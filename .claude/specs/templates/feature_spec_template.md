# FP-NNN: <título curto da feature>

> Spec template para features que tocam contrato do pipeline.
> Salvar copia preenchida em `docs/specs/FP-NNN_<short_slug>.md`
> (convenção do repo, ver PRs #186, #189, #193).
> Apagar este aviso e o `<placeholders>` ao usar.

## Problem

<1-3 parágrafos. O que está errado / faltando. Inclui evidência
ou referência ao PR / issue que motivou.>

## Scope

<O que esta feature **faz**. Lista bullet objetiva.>

## Non-goals

<O que esta feature **NÃO** faz. Importante pra evitar scope
creep e pra que reviewer saiba o que rejeitar como out-of-scope.>

## Artifact contract

<Que arquivos / outputs esta feature produz ou modifica.
Format ideal:>

| Path | Mudança | Quem produz |
|---|---|---|
| `consensus.json` | novo campo X | manual / extractor |
| `geometry_report.json` | novo campo Y | builder |
| `artifacts/<plant>/<plant>.skp` | novo group Z | Ruby builder |

## Detection heuristic / algorithm

<Como o builder identifica/lida com a situação que motivou esta
feature. Pseudo-código aceito.>

## Acceptance criteria (PASS / WARN / FAIL)

| Status | Critério |
|---|---|
| PASS | <objetivo, testável> |
| WARN | <degradação aceitável com justificativa> |
| FAIL | <bloqueador> |

## Required tests

| Teste | Cobertura |
|---|---|
| `tests/test_<feature>.py::test_<case>` | <o que prova> |
| ... | ... |

Mínimo: 1 teste vermelho antes da implementação que vira verde
depois. Ver
[`specs/sdd_and_harness_engineering.md`](../sdd_and_harness_engineering.md).

## Regression coverage

Linhas a adicionar em
[`evals/regression_matrix.md`](../../evals/regression_matrix.md):

- Camada 1: <quais testes>
- Camada 2: <quais gates_self_check podem regredir>
- Camada 3: <quais dimensões da rubric podem regredir>

## Done means

- [ ] Spec mergeada em `docs/specs/FP-NNN_*.md`
- [ ] Fixture micro em `fixtures/<x>/` (se aplicável)
- [ ] Teste vermelho → verde em `tests/`
- [ ] Implementação em `tools/build_plan_shell_skp.{py,rb}` ou
      onde aplicável
- [ ] Aplicação na planta real (planta_74) — ou rejeição
      justificada
- [ ] Side-by-side PDF vs SKP gerado
- [ ] Artifact promovido se mudou fidelidade
- [ ] PR contra develop com checklist acima

## Out of scope (placeholder)

<Itens correlatos que NÃO entram aqui mas merecem PR/issue separada.>

## Reference

- Constitution: [`.claude/constitution.md`](../../constitution.md)
- Fidelity gate: [`specs/fidelity_gate.md`](../fidelity_gate.md)
- Artifact contract template: [`specs/templates/artifact_contract_template.md`](artifact_contract_template.md)
