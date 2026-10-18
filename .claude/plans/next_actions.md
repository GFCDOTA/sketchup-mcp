# Next actions — sketchup-mcp

Fila curta. Máximo 5 itens. Adicionar novo só se houver espaço E
valor claro pro produto.

> **Snapshot:** 2026-10-18. Decai rápido.

## Fila atual

### 1. VISUAL_REVIEW do PR #247 (cômodo SERVICE)

- **Objetivo:** Felipe valida o render/`.skp` do brain SERVICE vs PDF.
- **Por quê:** é o único gate humano; sem ele o PR não lança.
- **Critério de parada:** veredito IMPROVED/SAME/WORSE registrado + merge ou ajuste.

### 2. Reconciliar ou fechar o PR #245

- **Objetivo:** checar se as 19 correções de baseline já estão em `develop`
  (CI verde desde ago/12); fechar se superado, rebasear se houver delta real.
- **Critério de parada:** PR fechado ou mergeado.

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
