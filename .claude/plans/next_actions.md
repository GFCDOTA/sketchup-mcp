# Next actions — sketchup-mcp

Fila curta. Máximo 5 itens. Adicionar novo só se houver espaço E
valor claro pro produto.

> **Snapshot:** 2026-10-18. Decai rápido.

## Fila atual

### 1. Provar as tools `su_*` num SketchUp real (#249)

- **Objetivo:** rodar o checklist do corpo do PR #249 no Windows com SketchUp
  2026 (status, inspect × Outliner, render, apply_edits + VISUAL_REVIEW,
  recusas de arquitetura, move em eixo de mundo dentro do sofá girado).
- **Por quê:** hoje toda a prova é lógica pura + dublês
  (`proof_state = UNVERIFIED_ON_SKETCHUP`); nenhum cliente deve tratar as
  `su_*` como capacidade comprovada antes disso.
- **Critério de parada:** evidência em `artifacts/review/` e `PROOF_STATE`
  atualizado no código.

### 2. Gate B do FP-041 (aguarda autorização)

- **Objetivo:** Fase 1 do SketchUp Tooling Specialist (plano rev. 3:
  competência operacional + ledger/validador de 3 camadas).
- **NÃO INICIAR** sem ok explícito do Felipe.

### 3. AI Pipeline Inspector — SSE + `Last-Event-ID`

- **Objetivo:** próxima fatia do `GFCDOTA/harness-app` (hoje só replay JSONL;
  `SseTraceSource` falha alto de propósito). Requer emissor SSE no lado Python.
- **Por quê:** tempo real é a próxima fase declarada da ADR-001.

### 4. (follow-up) `tools/check_skp_proof_of_progress.py` CI gate

- **Objetivo:** implementar o gate executável de
  `specs/skp_proof_of_progress_gate.md`.
- **NÃO INICIAR** sem ok explícito do Felipe.

### 5. (produto, HIGH) DIFF-001 — extrator PDF → consensus

- **Objetivo:** hoje o `consensus.json` é autoria humana; sem extrator o
  pipeline não generaliza para planta nova. Roadmap M4.

## Backlog observado

- Branches remotas `backup/stash-0..4` sem PR — arquivar/deletar com ok do Felipe.
- SU 2026 pode deixar processos pendurados após runs interactive — kill antes de reuso.

## Regra de fila

Concluir a fila → escolher próximo item **só se houver valor claro pro
produto** (gerar/revisar `.skp` fiel). Não inventar trabalho cosmético.
Ver `specs/product_goal.md` § "Critérios de avanço real" e
`memory/operational_rules.md` § "Continuar automaticamente vs parar".
