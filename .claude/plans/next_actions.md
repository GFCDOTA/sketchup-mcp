# Next actions — sketchup-mcp

Fila curta. Máximo 5 itens. Adicionar novo só se houver espaço E
valor claro pro produto.

> **Snapshot:** 2026-07-11. Decai rápido.

## Fila atual (backlog do review clínico 2026-07-11 — 3 revisores, 32 findings; vf_004 + integridade do shell JÁ corrigidos)

### 1. Janelas: peitoril/verga MEDIDOS do PDF + eixo Z nos gates

- **Por quê:** hoje o builder decide "basculante" por LARGURA e usa sills
  hardcoded (1.10/1.50m) — o PDF carrega o dado como texto ("PEITORIL
  H=1,10M"); e NENHUM gate olha Z (o geometry_report já emite bbox 3D,
  o position_fidelity só usa x/y). É a dupla que esconde a próxima
  classe de bug invisível (irmã do swing). Template: door_swing_audit.

### 2. Gate reverso PDF→consensus (opening faltante)

- **Por quê:** arco de porta no PDF SEM opening no consensus é invisível
  hoje — a classe mais grave de infidelidade sem detector. O matcher
  arco↔porta e o filtro de louças JÁ existem em door_swing_audit; falta
  só o loop reverso + FAIL em arco órfão.

### 3. Cache do build: chave incompleta (mordeu ao vivo em 2026-07-11)

- **Por quê:** `should_skip` só olha o sha do consensus — mudou builder
  (.py/.rb), PT_TO_M ou soft_barriers_mode, devolve .skp velho com
  "[skip] unchanged". Incluir hash dos builders + config na chave.

### 4. Contrato pra plantas novas: campos obrigatórios + openings no report

- **Por quê:** os defaults silenciosos continuam (`hinge_side||'left'`,
  `swing_side||'pos'`) — planta nova regride a chute sem sinal; e o
  geometry_report não registra o resultado por opening (janela pode
  sumir em silêncio). Gate de campos + bloco `openings` no report.

### 5. (follow-up menor) MÉDIAs do review + docs

- rb: face_tol 3.4× maior que o necessário (:1076), is_basc/esquadria
  só wall H, rollback do carve 3D, espessura global nos paths 2D.
  py: floor snap sem limite de spread (~35cm), floors com massa
  diferente do shell, modo attach lança SU, sliver inválido sem reparo.
  contrato: metadata mentiroso do consensus, triagem das 8 sb órfãs,
  louças extraíveis, rooms merged (r001/r002). docs: roadmap/index/
  README/current_state (auditoria 2026-07-11).

## Regra de fila

Concluir a fila → escolher próximo item **só se houver valor claro pro
produto** (gerar/revisar `.skp` fiel). Não inventar trabalho cosmético.
Ver `specs/product_goal.md` § "Critérios de avanço real".
