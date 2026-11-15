# FP-060 M2 — publicação de um review pela conta independente via outbox, no GitHub real

Evidência datada (2026-11-15) de uma execução **real** contra o GitHub, num PR descartável. Refs #606. Código sob prova:
`github_review_target.py` e `outbox_publisher.py` no commit `0d175e3` (árvore limpa).

## O que é

A exigência do M2 "publicação externa via outbox idempotente com reconciliação" (diretriz FP-060-A01 §4), provada contra o
GitHub de verdade, e não só contra o GitHub em memória da suíte determinística:

1. um evento concluído deixa uma entrada no outbox do `EventStore` (mesma transação);
2. o publicador reivindica a entrada, pergunta ao GitHub pela chave, não acha, e **posta o review** pela conta independente;
3. o publicador **morre** depois do POST e antes do ACK (uma exceção que nenhum handler engole);
4. um segundo publicador não consegue tomar a entrada enquanto o lease do morto vale (`IDLE`);
5. depois do lease expirar, ele **reconcilia**: acha o review pelo marcador da chave e grava o ACK, **sem postar outro**.

O PR descartável era um commit vazio em draft, rotulado "não mergear". Autor do PR: conta do executor. Revisor: conta
independente, com token próprio. Foi fechado sem merge e a branch foi apagada.

## Resultado (`evidence.json`)

| Passo | Resultado |
|---|---|
| publicador 1 morreu depois do POST | outbox `RUNNING`, 1 tentativa; **1 review** com a chave no GitHub |
| publicador 2 logo depois | `IDLE` (lease do morto ainda vale); 1 review |
| publicador 2 depois do lease | `RECONCILED`, referência `github-review:5911952280`, tentativa 2; outbox `DONE`; **1 review** |
| publicador 2 de novo | `IDLE` |

Conferência feita **por fora do script**, com a credencial do executor, antes de fechar o PR: o PR tinha exatamente 1 review,
da conta independente, no commit `0d89d2f` (o HEAD do PR), estado `CHANGES_REQUESTED`, com o marcador da chave no corpo.
O review fica visível no PR fechado: https://github.com/GFCDOTA/sketchup-mcp/pull/622#pullrequestreview-5911952280.

## Tentativas anteriores (falharam, por causa do token)

Duas execuções anteriores, nos PRs descartáveis #620 e #621, falharam com `403 Resource not accessible by personal access
token`: o token do revisor ainda não tinha a permissão `Pull requests: write`. Em ambas **nada foi postado** (0 reviews) e a
entrada do outbox ficou `PENDING` para nova tentativa, que é o comportamento esperado de uma recusa. Os dois PRs foram fechados
sem merge. A permissão foi conferida antes da terceira execução com um POST de `event` inválido, que não cria nada
(403 = sem escrita; 422 = com escrita).

## O que NÃO é

- **Não é o M2 completo.** Não há review do Codex CLI neste fluxo: o corpo do review é um texto fixo e o PR não altera
  arquivo. O que foi provado é a camada de publicação (outbox + reconciliação + identidade independente), não a revisão.
- **Não passa pelo `codex_reviewer`.** `codex_reviewer.publish` continua fazendo o POST direto, e um APPROVE em produção continua
  impossível enquanto o runner de testes de produção for fail-closed (depende da revisão do #617 e de um PR que o ligue).
- **Só `REQUEST_CHANGES`.** Nenhum review `APPROVE` foi postado, de propósito: um PR descartável aprovado é um risco sem ganho.
- **Não é exactly-once.** A reconciliação depende de o GitHub devolver o review na listagem; a janela de consistência
  eventual não foi exercitada.
- **Uma morte, na primeira publicação.** Dois publicadores simultâneos sem o mesmo `EventStore` não foram testados.
- Uma execução bem-sucedida: é demonstração, não medida de taxa de sucesso. Os reviews de teste ficam no histórico público
  dos PRs fechados (#622 com o review; #620 e #621 sem review).

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_github_review_target.py tests/test_outbox_publisher.py -q          # suíte determinística
# prova real: exige CODEX_REVIEWER_GH_TOKEN de uma conta em `review_policy.reviewers` (nunca a do executor) com
# `Pull requests: Read and write` no repositório, e um PR descartável aberto em draft criado pela conta do executor
PYTHONPATH=. $PY artifacts/review/fp060/m2_outbox/2026-11-15_github_disposable_pr/e2e_outbox_github.py <pr> <dir novo>
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `evidence.json` | PR, HEAD, autor e revisor, os passos com o estado do outbox e a contagem de reviews com a chave, o review final e o veredito |
| `e2e_outbox_github.py` | o script que executou a prova (o token vem do ambiente e nunca é impresso) |
