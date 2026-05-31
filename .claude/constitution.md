# Constitution — sketchup-mcp

Princípios load-bearing. Curto por design. Qualquer regra
operacional, spec, plan ou skill deve poder ser justificada a
partir destes 7 pontos. Se algo neste arquivo conflita com
qualquer outro `.md`, **este arquivo vence** — o outro precisa
mudar.

## 1. SKP é o artefato principal

O entregável final pro humano é o `.skp` versionado em
`artifacts/<plant>/`. Renders, reports, side-by-side e teste
verde são evidência auxiliar — não substitutos.

## 2. Sem `.skp` versionado, não há sucesso canônico

Geração que termina com PNG bonito mas sem `.skp` em
`artifacts/<plant>/` é **incompleta**, nunca "done". Ver
[`memory/artifact_policy.md`](memory/artifact_policy.md) §
critério de sucesso.

## 3. PDF / ground truth vence inferência do agente

Quando há conflito entre o que o PDF mostra e o que o pipeline
infere, **o PDF vence**. Hard Rule #1: nunca inventar walls /
rooms / openings que não existem no consensus. Honesto > completo.

## 4. Spec precisa virar teste + harness + artifact

Spec sem teste é ADR de prateleira. Cada feature relevante
exige: spec curto em `docs/specs/FP-NNN_*.md` → fixture mínima →
teste vermelho → implementação → teste verde → aplicação na
planta real → artifact promovido. Ver
[`specs/sdd_and_harness_engineering.md`](specs/sdd_and_harness_engineering.md).

## 5. Cleanup não é progresso sem ROI de produto

Hygiene precisa de trigger real (gate quebrando, ref duplicada,
arquivo solto confundindo agente). Cleanup em loop sem trigger é
bikeshed. Ver
[`specs/repository_hygiene.md`](specs/repository_hygiene.md).

## 6. Slice complete IS a valid stop

Concluir o escopo declarado de uma branch / PR / ciclo é parada
válida. Continuar automaticamente só se houver **próximo item de
ROI claro ligado a SKP / fidelidade / gate falhando / PR ativa /
milestone pedida pelo usuário**. Não criar novo ciclo de
governance/docs/refactor só porque não há blocker RED.

## 7. Multi-agent exige fetch → worktree → reconcile

Nunca assumir exclusividade do repo. Antes de mutação remota:
`git fetch --all --prune` (sequencial, não paralelo a
`rev-parse`), comparar HEAD local vs remoto, usar worktrees
isoladas quando houver paralelismo. Mudança out-of-band detectada
= parar e reconciliar. Ver
[`memory/multi_agent_coordination.md`](memory/multi_agent_coordination.md).

## 8. No SKP, no progress

Toda **SKP-affecting PR** (path-triggered — ver spec) deve
entregar **um** `.skp` final em pasta human-facing
(`artifacts/review/<plant>/<branch_or_pr>/final/`) + renders top
e iso + `regression_summary.md` com **evidência específica por
axis**. Sem isso, melhoria **não está concluída**. `/runs/` é
scratch — `.skp` lá sozinho NÃO conta como evidência.

**Escape hatch**: PRs doc-only / test-only / CI-only podem
marcar `SKP-proof: N/A` no body, justificando por que nenhum
path SKP-affecting foi tocado.

**Intermediários** (attempt_0/1/2) ficam em `/runs/` ou CI
artifacts — **não commitar por default**. Só commitar attempt
intermediário quando ele documenta uma decisão chave (regressão
identificada + fix aplicado).

**Não exigir pixel-perfect hard gate** — renders são evidência
de review, não diff bit-exato. Hard FAILs reservados pra
absurdos (missing SKP, missing render, window count mismatch,
floating door, orphan glass sem source).

Spec completa em
[`specs/skp_proof_of_progress_gate.md`](specs/skp_proof_of_progress_gate.md).

---

Estes 8 pontos são **constituição**. Mudança aqui exige PR
explícita e justificativa. Tudo o mais é regulamentação.
