# FP-060 MT-06 — E2E real com Claude, Codex e GitHub em PRs descartáveis

Evidência datada (2026-11-15). Refs #625, #606. Três fluxos reais, todos em PRs/Issues **descartáveis** do próprio repositório, **fechados sem merge**.

## O que é

| Fluxo | Issue → PR | O que percorreu | Resultado |
|---|---|---|---|
| **A — correção** | #650 → #651 (defeito semeado) | Codex real `REQUEST_CHANGES` (HEAD `4346d5c`) → correção `7c3d7bc` no PR → Codex real `APPROVED` no HEAD final. **Limite:** a evidência versionada registra o único `CORRECTION_REQUESTED` como `PENDING` ("terminou sem commit novo no PR"); a trilha da execução que publicou `7c3d7bc` pelas guardas e testes **não** está nesta evidência, então ela não prova a publicação pelo executor | CI 9/9 no HEAD final |
| **B — implementação** | #653 → #655 | Issue com a label humana `executor-intake` → intake → worker (Claude real) → PR aberto pelo executor → Codex real `APPROVED` (HEAD `cf31eb4`) | CI 9/9 |
| **C — corrida contínua** | #658 → #659 | executor em **laço** (`run --interval 45 --execute`, fonte SQLite, intake e revisão publicada ligados) sem nenhum disparo manual depois da label | CI 9/9, Codex real `APPROVED` (HEAD `a6ee910`) |

Linha do tempo do fluxo C (UTC, 2026-11-15): `23:41:25` label `executor-intake` aplicada (**única ação humana**) · `23:46:53` o intake publicou `IMPLEMENT_REQUESTED` (o passo roda a cada 5 min) · `23:49:04` o worker abriu o PR #659 · `23:54:49` CI 9/9 · `23:55:49` o ciclo acionou o revisor (`codex_review`) · `23:56:01` review `APPROVED` publicado por `fmmodesto` pelo outbox. Da label ao APPROVE: cerca de 14,5 min, dos quais ~5 min de CI.

Os reviews foram publicados pela identidade independente `fmmodesto` (conta distinta do executor `fmodesto30`) pelo caminho de produção do `codex_reviewer` + outbox (marcador `fp060-outbox-key` em cada review). Nenhum review foi simulado.

## Código sob prova (importante)

Os componentes **ainda não estão no `develop`**: o E2E rodou numa worktree de integração **local** (`e2e/fp060-integration`, nunca publicada) que mescla os ramos dos PRs abertos #632 (pilha #617–#632), #645, #646 (inclui #636 e #641), #640, #643, #649 (inclui #642 e #648), #652, #654 e #657. O resultado vale para essa combinação, não para o `develop` atual.

## Defeitos que a prova revelou (todos corrigidos em PR)

| Achado | Onde | PR |
|---|---|---|
| `executor_delivery.run_checks` devolvia `False` sempre: o executor **nunca publicava** uma correção | entrega | #645 |
| O executor publicou o commit e registrou `FAILED` porque a leitura REST logo após o push ainda devolvia o HEAD antigo | `_launch` | #652 |
| `gh_json` decodificava a saída do `gh` pelo locale (cp1252) e quebrava com byte inválido (`0x81`) fora do launcher | `event_bridge` | #654 |
| A trava de arquivo do estado ficava presa no Windows (`PermissionError` 32): 2/180 aquisições; era a causa do teste instável de concorrência | `execution_state` | #643 |
| O laço do executor não chamava o intake nem **publicava** o review (`lifecycle` aciona o revisor sem publicar) | ciclo | #657 |

## O que NÃO é

- **Não é produção:** estado, store SQLite e worktrees ficaram isolados (`data/runs/fp060_e2e*`, fora do repositório); nada foi ligado no ambiente principal e o `--execute` do ambiente principal continua desligado.
- **O laço de correção não foi provado em corrida contínua:** o fluxo C foi aprovado na primeira revisão. A correção (fluxo A) foi provada com etapas disparadas por mim. A combinação "contínuo **e** com `REQUEST_CHANGES`" não foi exercitada.
- **Merge não foi exercitado.** A decisão de merge automático foi calculada só como plano sobre o #651 (`MERGE` com as labels de autorização na época; `DISABLED` com o padrão desligado). Os três PRs foram fechados sem merge.
- **O Codex aprovou na primeira revisão duas implementações pequenas** (2 arquivos, ~40 linhas): isto mostra o encadeamento, não a qualidade do revisor em mudanças grandes. Uma revisão aprovada também não substitui testes.
- O primeiro poll do fluxo C registrou um erro transitório (`unexpected end of JSON input`, backoff de 30 s) e os seguintes passaram; a causa não foi isolada.
- `store_reconcile` não consegue descartar (`supersede`) um evento que está em backoff de retry até o backoff acabar (visto no fluxo A: o evento ficou `PENDING` com HEAD já movido). O resultado final é seguro (o preflight o descartaria), mas não é imediato.
- Custo e duração de cada execução do Claude/Codex **não foram medidos**.
- O intake roda a cada 5 min: o tempo da label até o PR inclui até 5 min de espera.

## Reprodução

```bash
PY=<venv do repositório>/Scripts/python.exe
# 1) estado isolado + flags (fora do repositório), com o token do revisor so no ambiente do processo:
#    EVENT_BRIDGE_STATE_PATH / BRIDGE_WORKTREE_ROOT / EVENT_STORE_DB_PATH / EXECUTION_STATE_PATH apontando para um diretorio novo
#    EXECUTOR_SOURCE=sqlite INTAKE_ENABLED=1 REVIEW_AUTOPUBLISH=1 CODEX_REVIEWER_GH_TOKEN=<token do revisor>
$PY -m tools.orchestration.event_executor run --interval 45 --execute
# 2) cadastrar uma Issue descartavel (spec:FP-060) e aplicar a label `executor-intake`
# 3) coletar a evidencia (somente leitura):
$PY artifacts/review/fp060/mt06_e2e/2026-11-15/collect_evidence.py <diretorio novo> NOME=<PR>:<Issue>:<store.db> [...]   # os numeros sao SEMPRE informados
#    ex.: A_correcao=<PR>:<Issue>:<store A/B>  C_continua=<PR>:<Issue>:<store C>   (caminhos do Windows com letra de unidade: E:/pasta/store.db)
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `data/evidence.json` | por fluxo: PR, HEAD final, commits (autor e mensagem), reviews (id, revisor, estado, commit, horário, marcador do outbox), checks no HEAD final; eventos e transições dos dois stores SQLite |
| `collect_evidence.py` | o coletor: somente leitura (SQLite em `mode=ro` por URI codificada); PR/Issue informados na linha de comando; toda string passa por `clean` e uma verificação final **recusa gravar** se achar token, e-mail ou caminho de máquina (lógica em `tools/validation/fp060_e2e_evidence.py`, testada em `tests/test_fp060_e2e_evidence.py`) |
