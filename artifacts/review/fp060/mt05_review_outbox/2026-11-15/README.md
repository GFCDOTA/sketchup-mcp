# FP-060 MT-05 — publicação do parecer do `codex_reviewer` pelo outbox transacional, no GitHub real

Evidência datada (2026-11-15). Refs #624 e #606. Código sob prova: `codex_reviewer.publish_via_outbox` e
`github_review_target.py` no commit `7a6f06d` (árvore limpa), Windows 11, Python 3.12.13.

## O que é

O `review_pr` publicava o parecer com um POST direto do `gh`, sem reconciliar e sem sobreviver a uma morte entre o POST e a
confirmação. Essa função foi removida: `publish_via_outbox` é agora o **único** caminho de publicação de produção e o padrão do
parâmetro `publisher` do `review_pr`. Ela grava o evento de publicação e a entrada do outbox na mesma transação, reconcilia
pelo marcador de chave escrito pela conta independente antes de enviar, o destino revalida PR aberto e HEAD no momento do POST,
e o review é conferido no GitHub depois.

Esta evidência chama essa função de produção contra o GitHub real, num PR descartável, e **mata o processo logo depois do
POST** (uma exceção que nenhum handler engole, injetada por um invólucro da chamada de API).

## Resultado (`evidence.json`)

PR descartável #631 (commit vazio, draft, "não mergear"). Autor: conta do executor. Revisor: conta independente.

| Passo | Resultado |
|---|---|
| processo morto depois do POST e antes do ACK | outbox `RUNNING`, 1 tentativa; **1 review** com a chave no GitHub |
| nova chamada, lease do morto ainda válido | não reenvia; **acha o review** e devolve a URL; continua 1 review |
| nova chamada depois do lease expirar | reconcilia e grava o ACK: outbox `DONE`, **2 tentativas**; **1 review** |

Veredito do script: **PASS**. Conferência feita por fora do script, com a credencial do executor, antes de fechar o PR:
exatamente 1 review, da conta independente, no commit do HEAD do PR, `CHANGES_REQUESTED`, com o marcador da chave. O review
continua visível no PR fechado: https://github.com/GFCDOTA/sketchup-mcp/pull/631#pullrequestreview-5912160819.

## Testes que acompanham (determinísticos)

`tests/test_review_outbox_publication.py` (13 testes) e os novos de `tests/test_github_review_target.py`: evento e entrada na
mesma transação; mesma chave não publica duas vezes; veredito diferente para o mesmo HEAD é outra publicação; morte entre POST
e ACK não duplica; HEAD movido não posta; `NEEDS_HUMAN` nunca entra na fila; POST negado devolve o motivo e deixa a entrada
para nova tentativa; entrada de **outro repositório** no outbox compartilhado não é postada; o `gh` recebe só um ambiente de
allowlist (a função antiga passava o ambiente inteiro do processo). 10 guardas removidas uma a uma: as 10 foram pegas (uma
sobreviveu na primeira rodada, por falta de teste do ambiente filtrado, e ganhou o teste).

## O que NÃO é

- **Não passa pelo Codex.** O veredito é fixo (`REQUEST_CHANGES` com um achado de texto explícito de prova); nenhum código foi
  revisado. O que se prova é a camada de publicação.
- **Só a publicação é transacional.** A revisão em si ainda roda de forma síncrona, fora de um evento reivindicado; o revisor
  dirigido por eventos é a MT-07.
- **Só `REQUEST_CHANGES`**: nenhum `APPROVE` foi postado, de propósito.
- **Não é exactly-once**: depende de o GitHub devolver o review na listagem; a janela de consistência eventual não foi
  exercitada. Dois coordenadores sem o mesmo `EventStore` não são coordenados por este mecanismo.
- Uma execução bem-sucedida: é demonstração, não medida de taxa de sucesso. O review de teste fica no histórico público do PR
  fechado.

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
$PY -m pytest tests/test_review_outbox_publication.py tests/test_github_review_target.py tests/test_codex_reviewer.py -q
# prova real: exige CODEX_REVIEWER_GH_TOKEN de conta em `review_policy.reviewers` (nunca a do executor) com
# `Pull requests: Read and write`, e um PR descartável aberto em draft criado pela conta do executor
PYTHONPATH=. $PY artifacts/review/fp060/mt05_review_outbox/2026-11-15/mt05_real_run.py <pr> <dir novo>
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `evidence.json` | PR, HEAD, autor e revisor, os passos com o estado do outbox e a contagem de reviews com a chave, o review final, o evento de publicação e o veredito |
| `mt05_real_run.py` | o script que gerou a evidência (o token vem do ambiente e nunca é impresso); o único ajuste depois da execução foi remover um `import os` não usado, sem efeito no comportamento |
