# FP-057 / P8 — Rollout supervisionado do executor local (Issue #589)

```yaml
id: FP-057-P8
status: PROPOSTA            # nada aqui autoriza -Execute continuo; cada fase exige APPROVE independente do gate
issue: 589
depende_de: [FP-057, "#590 bridge", "#591 executor", "#594 estabilizacao"]
principios: [fail_closed, verificar_antes_de_publicar_fora_do_LLM, executor_nao_se_autoautoriza, sem_notificacao_fingida]
fonte_das_decisoes: https://github.com/GFCDOTA/sketchup-mcp/issues/589#issuecomment-6640578567
```

## 1. Objetivo e nao-objetivos
Deixar o executor local (`fmodesto30`) consumir `CHANGES_REQUESTED` de `fmmodesto` com o minimo de intervencao manual, **sem** que o
executor possa ampliar o proprio escopo. Nao-objetivos: merge automatico, publicar review como `fmmodesto`, tocar PRs de producao
antes da fase 2 aprovada, barra flutuante de status (depois da estabilizacao).

## 2. Fases e gates
| Fase | O que roda | Entrada | Criterio de saida (todos verificaveis) |
|---|---|---|---|
| F0 | listener em **dry-run** no Agendador | #594 mergeado e tarefa reiniciada | 24 h de ciclos reais (ver §6) sem 2a instancia/orfao/erro de encoding; separar "processo existe" de "gh autenticado + ultimo ciclo ok" |
| F1 | `run --once --execute` manual, owner presente, **so** PR descartavel `chore/e2e-*` | F0 verde | (a) E2E com **alteracao pequena de codigo** + pytest/ruff do filho; (b) **teste negativo**: review ambiguo => nenhum commit, comentario do executor e estado diagnosticavel; (c) revisao do TL |
| F2 | janela supervisionada de **ate 2 h** com `-Execute` | §3 (R1-R4) implementado, testado e aprovado | 0 push fora da branch do PR, 0 duplicata, 0 FAILED sem diagnostico, 0 violacao de §3 nos logs; TL revisa commits e logs da janela |
| F3 | `-Execute` continuo | decisao explicita do **proprietario** + nova revisao independente apos a evidencia da F2 | fora do escopo desta SPEC |

## 3. Protecoes obrigatorias antes da F2 (cada uma em PR pequeno, com testes e revisao)
- **R1 — filtro fail-closed de execucao.** O item so roda se, **relido no GitHub no momento da execucao**: PR aberto, da mesma repo, com
  label `executor-ok`, review `CHANGES_REQUESTED` de revisor autorizado no HEAD atual, e `Refs #N` do item presente no corpo. Falha de leitura
  da label = recusa (`REFUSED`), nunca "assume que tem". Label removida durante a execucao cancela o filho no proximo heartbeat.
- **R2 — paths criticos.** Lista inicial (configuravel em arquivo versionado, so aumenta sem revisao especial): `.github/workflows/`,
  `docs/governance/review_policy.json`, `tools/validation/`, `tools/orchestration/` e scripts de governanca/execucao (`execution_state`,
  `task_scheduler`, `review_verification`, `protection_check`), o proprio arquivo da lista. Qualquer diff tocando um deles => bloqueio.
- **R3 — teto auditavel de arquivos/linhas** (iniciais propostos: <= 8 arquivos, <= 300 linhas adicionadas+removidas; a decidir pelo TL).
  Excedeu => bloqueio, item `FAILED` com a medida registrada.
- **R4 — a verificacao acontece ANTES do push e fora do LLM.** Nao se presume que restricoes possam ser aplicadas apos publicar. Desenho
  preferido: **push feito pelo executor, nao pelo filho** — retirar `git push` da allowlist do Claude; o filho so edita/testa/`git commit`;
  ao terminar, o executor calcula `git diff --numstat <HEAD_do_PR>..HEAD`, aplica R2/R3 (`execution_guards`), exige HEAD do PR inalterado e
  so entao roda `git push origin HEAD:<branch>` (sem force) e posta o comentario. Violacao => nada e publicado; a worktree e preservada
  para auditoria (Hard Rule #2). Alternativa descartada: hook `pre-push` na worktree (o filho tem `Write` e poderia sobrescreve-lo).
- **R5 — pedido ambiguo.** O filho nao inventa: se o review for ambiguo ou exigir decisao do proprietario, nao faz commit; o executor classifica
  "sem commit novo" como `NEEDS_CLARIFICATION` (nao gasta tentativa como falha) e o comentario do executor descreve a duvida.

## 4. Kill switch (qualquer um basta, sem editar codigo)
`runs\governance\EXECUTOR_DISABLED` (para no proximo ciclo) · `Stop-ScheduledTask "sketchup-mcp event bridge"` (derruba tambem o filho
via `--watch-pid`) · `install_event_bridge_task.ps1 -Remove` · `gh auth logout` do executor (preflight falha fechado, exit 3).
Remover a label `executor-ok` do PR tambem interrompe aquele PR (R1).

## 5. Observabilidade (sem notificacao push fingida)
- Ja existente: `event_bridge.log` (UTF-8, por ciclo), `runs\governance\executor\*.log` (redatado), `event_executor status`, comentario do
  executor em todo PR tocado.
- A adicionar: `status` separa **vivo** (instancia segura o lock) de **saudavel** (`gh` autenticado como o executor **e** ultimo ciclo sem
  `ERROR` ha < 2x o intervalo); contadores 24 h (execucoes, FAILED, BLOCKED, REFUSED por motivo).
- Alerta minimo inicial = linha no log/`status` + comentario na #589 quando `FAILED >= 2` seguidos ou `BLOCKED_*` por > 1 h. Canal push so
  depois de decisao do proprietario; ate la nao se afirma notificacao em tempo real.

## 6. Coleta das 24 h da F0 (nao declarar antes de observar)
Por ciclo ja existe a linha do log; adicionar rotina de **amostragem** (`status --json` agendado ou comando manual) que registra: PIDs e linha
de comando da cadeia, idade do ultimo ciclo, identidade `gh`, erros. A validacao so e declarada concluida com >= 24 h corridas de relogio
**e** a evidencia anexada na #589; reinicios/suspensao do Windows durante a janela contam como interrupcao e reiniciam ou anotam a contagem.

## 7. Rollback
Parar (kill switch) -> `-Remove` da tarefa -> itens `RUNNING` voltam a fila pelo lease (ou `FAILED`) -> remover worktrees `bridge-pr*` **so se
limpas** -> commit indesejado do executor: `git revert` em PR normal (nunca reset/force) -> registrar o incidente na #589.

## 8. Entregas (PRs pequenos, nesta ordem)
1. Esta SPEC. 2. `execution_guards` (funcoes puras R1-R3 + testes). 3. Ligacao do filtro `executor-ok` no `preflight` (depois do #594).
4. Push pelo executor com verificacao pre-publicacao (R4) e `NEEDS_CLARIFICATION` (R5). 5. `status` saude + amostragem 24 h. 6. Roteiro
F1 (E2E com codigo + negativo) executado com o owner. 7. Janela F2 so apos tudo acima aprovado.
