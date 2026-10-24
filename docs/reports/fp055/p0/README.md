# FP-055 P0 — auditoria forense e baseline (2026-10-23)

Reproduzir: `PT_TO_M=0.0259 python -m tools.navigation.pipeline_audit docs/reports/fp055/p0` (deterministico; sem relogio na
saida). `baseline_manifest.json` foi escrito por script nesta sessao (hashes de protegidos, snapshot, 8 violacoes conhecidas).

| Arquivo | Conteudo |
|---|---|
| `capability_inventory.json` | 18 capacidades, 9 especialistas, 19 receitas, 19 modulos vigiados × AVAILABLE/INVOKED/CONSUMED |
| `runtime_inventory.json` | checkout auditado, config do MCP, checkout do MCP (HEAD, atraso), worktrees |
| `generation_trace.json` | arquivos e funcoes chamados por `collect_boxes`, resumo por comodo, log do furnish |
| `baseline_manifest.json` | SHA-256 dos protegidos, snapshot da planta, violacoes conhecidas, origem dos `.skp` antigos |
| `execution_graph.md` | grafo real de execucao e entrypoints |
| `integration_gap_matrix.md` | lacunas por capacidade/componente |

## Reconciliacao com a auditoria anterior (mesma data, sessao de chat)
Todos os achados se confirmam com rastreio reproduzivel: sofa premium de 2026-07-11 (`4500916`); oficial de 2026-09-19
(`6c562b3`); MCP 102 commits atras (a auditoria anterior disse ~100); F1C do banheiro chamada e descartada; solver, especialistas,
receitas, gates funcionais e de colisao fora da geracao; geracao limpa com snapshot `5426c0087bdfcdc6` (394 pecas) e os 8
defeitos. **Correcao:** a auditoria anterior listou "shared cabinet nao executado" sem distinguir: as 4 capacidades de
marcenaria L2_PASS nunca sao invocadas pela geracao do apartamento (confirmado aqui).

Achados novos nesta fase:
- `furnish_apartment.main` **apaga e regrava `artifacts/planta_74/furnished/`** — o entrypoint "oficial" escreve direto no artefato
  protegido, sem gate funcional. `su_furnish` grava em `runs/`.
- `bake_theme.py` tambem grava em `artifacts/planta_74/furnished/`.
- O simbolo `circulation.gate` do catalogo (`circulation_gate.gate`) nao e o que os brains chamam (`GateSession.check`).
- `bathroom.wet-room.guard` so loga: nao bloqueia.
- Ha um worktree criado por engano nesta sessao em `E:/Claude/apps/sketchup-mcp/worktrees/w-audit` (fora de `E:/Claude/worktrees/`,
  Hard Rule #3 do workspace). Limpo, sem trabalho; remover na P1 depois de conferir refs.
- `baseline_manifest.json.pdf_candidates` inclui uma copia em `runs/` (scratch); a fonte e `projects/planta_74/source/planta_74.pdf`.

## Riscos (P0)
| Risco | Onde | Mitigacao proposta |
|---|---|---|
| Executar codigo velho pelo MCP | checkout do MCP 102 atras | P1: identidade de runtime antes de qualquer geracao inteligente |
| Sobrescrever o oficial sem gate | `furnish_apartment.main`, `bake_theme.py` | P1/P3: saida padrao em `runs/`; escrita oficial so com `allow_official_write` + gates |
| Integracao nominal | F1C importado e descartado | P3/P7: CONSUMED por regra + teste de mutacao |
| Prova L2 quebrada ao integrar marcenaria | `shared.cabinet.*` | P5: integrar via adaptador, sem tocar simbolos provados (R-18) |
| Esperar que integrar "conserte" os banheiros | r005–r007 | INFEASIBLE no DOF atual: decisao do Felipe, nao do pipeline |

**Gate P0:** os entrypoints que geram o apartamento inteiro (2) e os escritores parciais (7) estao classificados em
`execution_graph.md`; nenhuma dependencia critica ficou com estado desconhecido (REFLECTED/VALIDATED sao `NOT_EVALUATED` por
definicao nesta fase e ficam para P3/P8).
