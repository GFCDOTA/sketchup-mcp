# DOCS-CONSOLIDATION-TODO.md

Lista de docs com conteúdo duplicado ou sobreposto, identificados no
housekeeping de 2026-04-21. **Não consolidar agora** — isto é só o
backlog para um ticket próprio de documentação.

Produção (`CLAUDE.md`, `ROADMAP.md`, `README.md`, `AGENTS.md`) está
fora de escopo e não deve ser tocada neste ticket.

## Duplicatas confirmadas

### 1. `ANALYSIS.md` + `ANALYSIS-OVERVIEW.md`
- Provável duplicata de análise inicial do código.
- Ação sugerida: reler ambos, manter o mais completo, remover o outro
  ou mesclar trechos únicos no sobrevivente.

### 2. `SOLUTION.md` + `SOLUTION-FINAL.md`
- **Duplicata definitiva.** `SOLUTION-FINAL.md` é a versão atualizada
  após o fix estrutural em `a11724a` + revisão com 3 agents.
- Ação sugerida: manter `SOLUTION-FINAL.md`, deletar `SOLUTION.md`
  (ou mover para `archive/SOLUTION-historical.md` se houver contexto
  histórico único que queremos preservar).

## Sobreposições a avaliar

### 3. Cluster de openings / polygonização
- `CROSS-PDF-VALIDATION.md`
- `OPENINGS-EXPLOSION-AUDIT.md`
- `OPENINGS-REFINEMENT.md`
- `OVER-POLYGONIZATION-ANALYSIS.md`

Esses quatro têm overlap entre auditoria histórica, análise de
causa e estado atual do refinamento. Ação sugerida: identificar o que
é história (audit/analysis de problema passado) vs. o que é
descrição do estado atual, e separar em dois arquivos no máximo:
- `OPENINGS-REFINEMENT.md` (estado atual, como funciona hoje)
- `docs/archive/openings-history-YYYYMMDD.md` (auditorias e explosões
  passadas consolidadas)

## Notas

- Nada de produção deve ser tocado neste ticket
  (`CLAUDE.md`, `ROADMAP.md`, `README.md`, `AGENTS.md`).
- Nota de consolidação já foi adicionada ao topo de
  `SOLUTION-FINAL.md` apontando para os docs atuais (SVG-INGEST,
  OPENINGS-REFINEMENT, VALIDATION-F1-REPORT).
- Follow-up: abrir issue/ticket dedicado antes de deletar qualquer doc.
