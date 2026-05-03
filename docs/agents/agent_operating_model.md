# Agent Operating Model

> Regras universais que todo agente especialista deste repo segue.
> Documentos individuais (`repo_auditor.md`, `geometry_specialist.md`, etc.)
> apenas restringem ainda mais o escopo de cada agente.

## Regra fundamental

**Agentes não comitam direto em `main`.** Sempre branch + PR.
**Agentes não deletam.** Sempre add-only ou modify-with-rollback.
**Agentes não escondem falha.** Sempre documentam o que viram, mesmo
ruim.

## Princípios

1. **Trabalhar em branches** — uma branch por sessão de trabalho do
   agente, nome `agents/<agent-name>/<task-slug>`.
2. **Commits pequenos** — uma ideia = um commit. Nunca misturar
   refactor + bugfix + feature.
3. **Sempre PR** — mesmo agentes que podem editar abrem PR pro user
   revisar. Nunca merge automático.
4. **Nunca delete sem aprovação** — só add-only ou modify. Se algo
   precisa ser deletado, propõe em comentário no PR e espera aprovação
   humana explícita.
5. **Schema/threshold/algoritmo congelados sem validação empírica**
   — qualquer mudança em `plan_core/schema`, thresholds em
   `classify/`, `topology/`, `openings/`, `extract/` exige medição
   antes/depois em PDFs canônicos (planta_74, p10, p12, synth_*) e
   dump das métricas no PR.
6. **Todo PR de agente inclui:**
   - Summary
   - What changed
   - What did NOT change (escopo proibido confirmado)
   - Validation (comandos rodados + outputs)
   - Métricas antes/depois (se aplicável)
   - Risks
   - Rollback (`git revert <hash>` sempre como mínimo)

## Hierarquia de permissões

| Nível | Quem | O que pode fazer |
|---|---|---|
| **Read-only** | Repo Auditor, Geometry, Openings, SketchUp, Performance, Validator | Lê código + dados, escreve apenas em `reports/` |
| **Docs-edit** | Docs Maintainer | Edita `docs/`, `OVERVIEW.md`, `README.md`. NUNCA edita `CLAUDE.md`/`AGENTS.md` (precisa autorização user). |
| **CI-edit** | CI Guardian | Pode propor mudanças em `.github/workflows/` via PR draft. Nunca merge direto. |
| **Code-edit** | (nenhum por enquanto) | Reservado pra agentes futuros com autorização explícita do user. |

Nenhum agente atual mexe em `extract/`, `classify/`, `topology/`,
`openings/`, `model/`, `validator/scorers/`, `tools/consume_consensus.rb`,
`tools/inspect_walls_report.rb`, `tools/build_vector_consensus.py`,
`tools/extract_openings_vector.py`, `tools/skp_from_consensus.py`,
`api/app.py`, ou `sketchup_mcp_server/server.py` sem PR humano dedicado.

## Output obrigatório

Todo agente termina sua sessão com:

1. **Branch pushed** (mesmo se nada mudou — branch vazia também
   reportável)
2. **PR aberto ou URL pra abrir** (se gh não autenticado, URL é
   `https://github.com/<repo>/pull/new/<branch>`)
3. **Relatório em `reports/<agent-name>_<timestamp>.md`** com:
   - O que rodei
   - O que encontrei
   - O que mudei (se algo)
   - Métricas
   - Próximos passos sugeridos
4. **Diff do que foi tocado** (`git diff main...HEAD --stat`)
5. **Comando de rollback** (`git revert <hash>` ou `git push origin
   --delete <branch>`)

## Tarefas explicitamente proibidas pra TODOS os agentes

- Push direto em `main`
- `git push --force` em qualquer branch sem autorização
- `git rebase -i` (interativo, requer humano)
- `--no-verify` em commits
- Deletar arquivos em `runs/`, `patches/`, `docs/`, `vendor/`
- Mover arquivos sem PR dedicado de move (constraints da Phase 4-5
  do roadmap)
- Aplicar patches em `patches/archive/` (07-09 são alto risco,
  exigem decisão humana)
- Mexer em `classify/service.py:160-171` (gate `len(strokes) > 200`)
- Alterar invariantes do `AGENTS.md §2` (não inventar walls/rooms,
  não usar bbox como room, não acoplar a PDF específico, debug
  artifacts obrigatórios, ground truth nunca no extrator)
- Deletar/modificar `CLAUDE.md` ou `AGENTS.md` sem autorização
- Alterar `.mcp.json` (carregado automaticamente pelo Claude Code,
  mudança quebra todas as sessões)
- Subir output do pipeline pra serviços externos (validator vision
  é local-only via Ollama)

## Estilo de PR padrão

Toda PR de agente segue este template no body:

```markdown
## Agent
<repo-auditor | geometry-specialist | ...>

## Summary
<1-3 bullets do que mudou>

## What changed
- <arquivo>: <breve descrição>

## What did NOT change (escopo proibido confirmado)
- nenhum arquivo de algoritmo
- nenhum threshold
- nenhum schema
- nenhum Ruby/SketchUp
- (etc.)

## Validation
```
<comandos rodados + output relevante>
```

## Métricas antes/depois (se aplicável)
| Métrica | Antes | Depois |

## Risks
<o que pode dar errado>

## Rollback
```bash
git revert <hash>
# ou
git push origin --delete <branch>
```
```

## Auditor recorrente

O Repo Auditor é especial — pode ser invocado por workflow agendado
(`.github/workflows/repo-auditor.yml`) que roda semanalmente. Mesmo
assim:
- **Nunca merge automático** — sempre abre PR draft
- **Nunca commit direto em `main`** — sempre na branch do PR
- **Sempre comparação com previous report** — diff de findings
- **Sempre lista de findings novos vs resolvidos**

Detalhes em `docs/agents/repo_auditor.md`.
