# FP-057 P0 — mapa do fluxo atual e lacunas comprovadas (2026-10-24)

Auditoria do que **já existe** antes de construir (nada é reescrito; cada lacuna cita a evidência no repositório ou na sessão).

## 1. Fluxo atual (o que funciona hoje)
| Etapa | Mecanismo existente | Onde |
|---|---|---|
| Backlog | Issues (#380–#510) + Project #1 (campos Tipo, Prioridade, Estado da prova, Aprovação humana, SPEC, Fase, Dependências) | GitHub |
| Integridade do backlog | `backlog_gate` (Done só com Issue fechada + prova + comentário `**Evidência`; status × labels; dependências) | `tools/validation/backlog_gate.py`, check `qg: backlog, issues and specs` |
| Qualidade das Issues | `issue_integrity_gate` (critérios de aceite, causa de bloqueio única, Epic nunca bloqueada, decisão humana com alternativas/recomendação, dependência obsoleta) | idem |
| SPEC × backlog | `spec_integrity_gate` | idem |
| Política de PR | `pr_policy_gate` (`Refs`, sem `Closes`, `SKP-proof`, testes, aparência sem prova) | check `qg: PR policy` |
| Geometria e programa | `quality_geometry_gate` (gêmeo × baseline, perda de programa registrada, varredura real da folha) + `known_gaps.json` | check `qg: geometry, program and integration` |
| Integração | `consumption_baseline` (INVOKED/CONSUMED por capacidade) | idem |
| Board | `board_sync` (rascunho/pendente → In Progress; pronto e verde → GPT Review; Blocked/Done não se movem) | `tools/validation/board_sync.py` (manual) |
| Revisão independente | regra `DONE_WITHOUT_GPT_REVIEW` (marcador `GPT-REVIEW: APPROVED`, vale para fechamentos ≥ 2026-10-25) | `backlog_gate` + `review_policy.json` |
| Auditoria | `audit_report` (+ workflow semanal) | `docs/reports/audit/` |
| Proteção | 8 checks obrigatórios em `develop` e `main`, `enforce_admins` ligado, merge precoce recusado (testado) | API de proteção de branch |
| Retomada | `.ai_bridge/HANDOFF.md` (texto livre), memória da sessão | repositório |

## 2. Lacunas comprovadas (o que a FP-057 precisa fechar)
| # | Lacuna | Prova | Fase |
|---|---|---|---|
| L1 | **Ninguém escolhe a próxima tarefa**: a seleção vem de mensagem do proprietário; não existe descoberta, elegibilidade nem priorização em código | não há módulo de descoberta/scheduler em `tools/`; histórico da sessão (cada rodada começou por pedido humano) | P1/P2 |
| L2 | Dependências só são lidas como texto (`**Dependências:** #N`); **sem grafo**: ciclo, referência inexistente, dependência já resolvida e "paralelizável" não são detectados (só `BLOCK_DEPENDENCY_STALE` isolado) | `issue_integrity_gate.py` | P1 |
| L3 | **Sem manifesto de execução**: retomar depende da conversa e do `HANDOFF.md` livre; nada reconcilia branches/worktrees/PRs abertos com o GitHub | worktrees `w-*` de sessões antigas coexistem com os atuais | P2 |
| L4 | **Sem controle de concorrência**: duas execuções podem pegar a mesma Issue/branch/arquivos | não há lease nem label de execução | P2 |
| L5 | **Revisão GPT forjável**: qualquer comentário com `GPT-REVIEW: APPROVED` basta; não liga PR, SHA, revisor nem data; novo commit não invalida | `backlog_gate._needs_gpt_review` | P4 |
| L6 | **Independência não verificável por conta**: o ChatGPT conectado ao GitHub e o executor atuam pela mesma conta do proprietário; o marcador não distingue um do outro | `gh api user` único | P4 (decisão do proprietário registrada) |
| L7 | Taxonomia de bloqueio sem `EXTERNAL` e `ENVIRONMENT` (a #508 é credencial externa e estava como "decisão humana") | `issue_integrity_gate.CAUSES` (corrigido nesta PR) | P0 |
| L8 | `board_sync` só faz 3 transições, sem `Backlog→Ready`/`Blocked→Ready`, **sem tratar rate limit** (a cota GraphQL estourou duas vezes) e sem garantia de não duplicar cartão | execuções de 2026-10-24 | P5 |
| L9 | Sem **entrada de defeito** (dedupe + Issue + impacto) nem **análise de impacto** de mudança de contrato | nenhum módulo; Issues criadas à mão | P3 |
| L10 | Automação do Project no Actions é **parcial**: falta `BACKLOG_PROJECT_TOKEN` (#508) | `quality-guardian.yml` roda `--no-project` | P5 (externo) |
| L11 | Workflows de `schedule`/`issues`/`workflow_dispatch` só rodam na branch padrão (`main`); `develop` ainda não foi promovida (#507) | `gh workflow list` mostra só `ci` | fora (task própria) |
| L12 | Não há **prova de recuperação** ponta a ponta no GitHub | — | P6 |

## 3. Responsabilidades (quem faz o quê)
| Papel | Responsabilidade | Não pode |
|---|---|---|
| Backlog (Issues) | fonte de planejamento, critérios, dependências | ser duplicado em outro backlog |
| SPEC | fonte dos critérios e contratos | mudar versão em bloco |
| Testes/contratos/evidência | fonte de validação | ser substituídos por mensagem de progresso |
| Executor (Claude) | descobrir, escolher, implementar, testar, abrir PR, corrigir, reconciliar | aprovar a própria revisão independente; relaxar gate; alterar artefato oficial |
| Quality Guardian | bloquear violação objetiva | aprovar geometria/aparência |
| Revisor independente | aprovar com PR + SHA + veredito | ser o executor |
| Proprietário | decisões arquitetônicas, visuais e de escopo; credenciais; promoção `develop → main` | — |

## 4. Entregas desta PR (P0)
SPEC `docs/specs/FP-057_autonomous_engineering_orchestration.md`; taxonomia `EXTERNAL`/`ENVIRONMENT` no `issue_integrity_gate`
(+ teste); labels `bloqueio:external` e `bloqueio:environment`; #508 reclassificada como `external`. Nenhum mecanismo existente foi
duplicado: as fases seguintes estendem `backlog_gate`, `issue_integrity_gate`, `board_sync` e `audit_report`.
