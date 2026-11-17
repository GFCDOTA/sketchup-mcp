# FP-060 M2 — publicação via outbox no GitHub real, com o script ATUAL (2026-11-16)

Evidência datada (2026-11-16) de uma execução **real** contra o GitHub do script
`../2026-11-15_github_disposable_pr/e2e_outbox_github.py` no estado do HEAD `e2b2a329` deste PR (árvore limpa). Refs #606.

Refaz a prova de `2026-11-15_github_disposable_pr/` com a versão endurecida do script. A execução anterior foi feita antes da
guarda de PR descartável e da espera pelo teto do envio, e por isso não comprovava o comportamento atual.

## O que mudou em relação à execução de 2026-11-15

- **Guarda de PR descartável** (`github_review_target.require_disposable_pr`) antes de qualquer entrada no outbox. O PR precisa
  estar aberto, em draft, com o marcador `<!-- fp060-disposable-e2e -->` no corpo, 0 arquivos alterados e autor diferente do
  revisor. Um erro explícito, não um `assert`, recusa o PR se faltar qualquer item.
- **Lease durante o envio inteiro:** o alvo GitHub declara `send_timeout_s` (GET + POST, 120 s). O segundo publicador só reconcilia
  depois desse teto mais a folga, não depois do lease curto.

## Resultado (`evidence.json`)

PR descartável **#673** (commit vazio `fe7c0c5`, draft, marcador no corpo, 0 arquivos). Autor do PR: conta do executor. Revisor:
conta independente, com token próprio.

| Passo | Resultado |
|---|---|
| publicador 1 morreu depois do POST e antes do ACK | **1 review** com a chave no GitHub |
| publicador 2 logo depois | `IDLE` (o lease do morto ainda cobre o envio); 1 review |
| publicador 2 depois do teto do envio | `RECONCILED` na tentativa 2, referência `github-review:5931862539`; outbox `DONE`; **1 review** |
| publicador 2 de novo | `IDLE` |

Veredito do script: **PASS**.

Conferência feita **por fora do script**, com a credencial do executor, antes de fechar o PR: o #673 tinha exatamente 1 review
com a chave, da conta independente, no commit `fe7c0c5` (o HEAD do PR), estado `CHANGES_REQUESTED`. Em seguida o PR foi fechado
sem merge e a branch foi apagada.

## O que NÃO é

- **Não é exactly-once.** É "pelo menos uma tentativa + reconciliação pela chave"; depende de o GitHub listar o review.
- **Uma execução:** é demonstração, não taxa de sucesso.
- O conteúdo do review é deliberadamente nenhuma revisão de código: o PR não altera arquivo.

## Reprodução

```bash
# PR descartável: draft, commit vazio, corpo com <!-- fp060-disposable-e2e -->; token do revisor só no ambiente do processo
CODEX_REVIEWER_GH_TOKEN=<token do revisor> PYTHONPATH=. python \
  artifacts/review/fp060/m2_outbox/2026-11-15_github_disposable_pr/e2e_outbox_github.py <pr> <diretório novo>
```
