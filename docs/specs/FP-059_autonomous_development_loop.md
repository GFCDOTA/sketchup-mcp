# FP-059 — Autonomous Development Loop

Versao 1.0.0 · status RASCUNHO · Engineering Automation / Orchestration & Governance. Depende de FP-057/#589 (bridge, executor), FP-058/#599 (barra), PR #598 (entrega
pelo executor), #597 (sonda E2E), #600 (observabilidade). GitHub e a fonte de verdade; nenhum orquestrador novo: estende `event_bridge`, `event_executor`,
`executor_delivery`, `execution_guards`, `task_scheduler`, `execution_state`, `board_sync`.

## Objetivo
Ciclo autonomo e duravel: **selecionar -> implementar -> testar -> publicar -> revisar -> corrigir -> aprovar -> concluir -> proxima tarefa**, que continua depois
de a sessao interativa do Claude Code encerrar (processo residente que reconcilia o GitHub por polling). Nao objetivos: outro orquestrador, ignorar branch
protection, dar credenciais irrestritas, merge automatico de mudanca critica sem as aprovacoes exigidas, agentes alterando a propria politica, fechar Issue sem
evidencia, dashboards novos, mexer em algoritmo/visual do SketchUp.

## Papeis e identidades
Claude Code = executor (implementa/corrige; nao aprova, nao publica o veredito, nao ignora a entrega controlada). Codex CLI = revisor (`codex exec --sandbox read-only`,
worktree separada, parecer JSON validado). Orquestrador Python = coordena processos, estados, permissoes, testes, publicacao, recuperacao, idempotencia. ChatGPT Web =
auditor externo, so por fluxo realmente disponivel ou consulta humana (nao ha webhook). Executor e revisor tem credenciais independentes; o Codex autenticado no ChatGPT
NAO recebe a identidade `fmmodesto`. Sem identidade independente: `REVIEW_BLOCKED`, nunca aprovacao simulada.

## Maquina de estados (persistida e recuperavel)
`READY -> CLAIMED -> IMPLEMENTING -> LOCAL_VALIDATION -> PUBLISHING -> WAITING_CI -> (CI_FAILED -> CORRECTION_REQUIRED | CI_PASSED -> REVIEW_QUEUED -> REVIEWING ->
(CHANGES_REQUESTED -> CORRECTION -> IMPLEMENTING | APPROVED -> COMPLETING -> COMPLETED | REVIEW_BLOCKED -> NEEDS_HUMAN))`. Complementares: `PAUSED`,
`FAILED_RETRYABLE`, `FAILED_TERMINAL`, `STALE_HEAD`, `BLOCKED_DEPENDENCY`, `NEEDS_CLARIFICATION`, `SUPERSEDED`.
Cada transicao registra {issue, pr, branch, head_sha, review_id, from, to, actor, reason, attempt, timestamp, correlation_id} com valores reais do GitHub.
Idempotencia: unidade = evento + HEAD; nunca executa 2x a mesma revisao concluida, nunca publica sobre HEAD velho, nunca consome review substituido, nunca 2 executores
na mesma tarefa, nunca aprova SHA diferente do revisado. Recuperacao: ler estado -> conferir donos de lease/lock -> consultar GitHub -> reconciliar HEAD/CI/review/branch
-> retomar so se os controles permitirem -> registrar por que nao retomou. Publicacao de resultado desconhecido nao e repetida sem reconciliar.

## Fases (PRs pequenos por fase; cada fase so avanca com testes + revisao independente)
- **F0 — corrigir bloqueios:** #599 (`ACCEPTANCE_MISSING`), #598 (symlink/recuperacao), #600; 8/8 verdes e aprovacao independente; sem mudar politica para esconder falha.
- **F1 — E2E do executor (#597):** Claude executa e o executor commita/publica (pytest/ruff fora do LLM, guards, HEAD/identidade revalidados); 1 commit real, CI no novo HEAD.
- **F2 — revisor Codex:** adaptador `codex exec --sandbox read-only --output-schema --output-last-message`, HEAD fixo, JSON por schema, timeout/tentativas, erro de auth/limite
  => bloqueio; publicador confiavel com identidade independente; nunca aprova por erro/evidencia insuficiente.
- **F3 — ciclo Claude <-> Codex:** implementa -> testa/publica -> CI -> Codex acha defeito -> REQUEST_CHANGES -> corrige -> CI -> Codex aprova; 3 correcoes/ciclo, 1 executor
  e 1 revisor por vez, caminhos criticos so com aprovacao humana, kill switch; caso negativo sem alteracao de codigo.
- **F4 — retomada por eventos:** PR aberto, novo HEAD, CI, review, merge, Issue desbloqueada, falha recuperavel, lease expirado, tarefa elegivel; polling + reconciliacao;
  sobrevive a reinicio do Windows sem duplicar.
- **F5 — backlog:** elegivel = Issue aberta, Ready, dependencias resolvidas, proxima acao objetiva, autorizacao, sem decisao humana, escopo protegido, sem outro executor no
  escopo; nunca bloqueadas/epicos/visuais; 2 Issues independentes em sequencia; Project #1 atualizado; merge/fechamento so se a politica autorizar.

## Seguranca e modos
Inegociaveis: sem token compartilhado, sem autoaprovacao, sem push irrestrito/force-push, sem ignorar checks, erro nunca e aprovacao, caminhos criticos so no fluxo autorizado,
sem apagar worktree com alteracoes, sem `taskkill` por nome, sem execucao continua antes do E2E e dos gates, agente nao altera os proprios limites. Escalar ao proprietario/ChatGPT
Web: politica de seguranca, o proprio orquestrador, arquitetura de alto impacto, aprovacao visual/geometrica, conflito entre agentes, falha apos as tentativas; silencio do auditor
nao autoriza. Modos: `DRY_RUN` (observa), `SUPERVISED` (alvo especifico, com limites), `CONTINUOUS` (so tarefas elegiveis e protegidas; exige gates + autorizacao explicita).

## Observabilidade (FP-058)
A barra consome estados duraveis do orquestrador (nao infere de processos): Claude (ocioso/implementando/corrigindo/testando/falhou), Codex (nao integrado/ocioso/revisando/
solicitou alteracoes/aprovou/falhou), orquestrador (DRY_RUN/SUPERVISED/CONTINUOUS/PAUSED/ERROR), backlog; por execucao: Issue, PR, HEAD, agente, duracao, tentativa, resultado.

## Testes obrigatorios
Review novo/duplicado, HEAD alterado, CI pendente/falho, Claude falhou, commit nao publicado, credencial invalida, Codex indisponivel, JSON invalido, revisao sem evidencia,
processo duplicado, Windows reiniciado, kill switch, Issue bloqueada, worktree inesperada, symlink/path critico, merge concluido, nenhuma tarefa (IDLE sem custo de LLM).
Mocks e integracao real.

## Conclusao
Concluida so quando: #598 integrado; E2E #597 (ou sonda equivalente justificada); Codex integrado e publicacao independente comprovada; Claude corrige REQUEST_CHANGES sem
intervencao e o Codex aprova o novo HEAD; retomada apos merge e apos reinicio; scheduler inicia tarefas elegiveis; 2 Issues em sequencia sem mensagens manuais; barra com estados
reais; QG/CI verdes; nenhuma protecao contornada; logs/evidencias reproduzem o ciclo. **O produto desta SPEC e o ciclo autonomo funcionando, nao documentacao.**
