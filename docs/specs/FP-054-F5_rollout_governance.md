# FP-045-F5 — Cobertura por cômodo, rollout e liberação do congelamento

> **Registro no repo (Claude, 2026-10-23):** recebida do Felipe como *FP-045*; renumerada para **FP-054** porque FP-045…FP-053 já existem (a FP-045 do repo é a de especialistas/modularização, mergeada). Texto original preservado abaixo; correções e reconciliação com o código ficam na §0 da spec-mãe (`docs/specs/FP-054_spatial_core_reliability_program.md`). Evidências em `docs/reports/fp054/`.

**Pré-requisito:** núcleo provado em F1–F4.

## Matriz por ambiente
- Sala: sofá, rack, TV, mesa/cadeiras, porta e varanda; layouts difíceis e inviabilidade.
- Cozinha: pia ancorada, circulação funcional, aberturas de armários, eletros, ergonomia, portas e instalações.
- Dormitórios: cama, circulação lateral, armários e abertura de portas, mesas de cabeceira.
- Banheiros: box, vaso, bancada, ralos, porta, zonas molhadas e tolerâncias de peças estruturais.
- Serviço: lavadora, tanque, porta/manutenção e passagens; varanda, closet, home office, corredores com seus casos explícitos.
- Não exigir suporte fictício: perfis consultivos/incompletos recebem `NOT_IMPLEMENTED` e plano de capacidade, não `PASS`.

## Governança
- Definir níveis `P0 blocker`, `P1`, `P2`, com owner, risco, regressão e evidência; não resolver por alteração arbitrária de política.
- Revisão mensal de coverage funcional, métricas, falsos positivos e tempo de execução; processar defeitos por cenário reproduzível.
- Cada PR final: issue ligada, contrato, testes negativos, cobertura, tempo/memória, rollout, rollback, prova L2 (se aplicável), limite visual.
- Nenhum PR aberto ao final de handoff: mergear com gates ou fechar explicando bloqueios; backlog em issues.

## Gate para retomar tutoriais
- F0–F4 com relatórios e prova de todos os caminhos críticos alterados, F5 com regressão por ambiente, riscos residuais aceitos explicitamente.
- Zero falso PASS conhecido em requisitos espaciais hard nos casos certificados; comportamento determinístico e diagnósticos de inviabilidade.
- Matriz `feature -> capacity -> specialist owner -> unit/integration/L2 -> status` disponível na documentação; não confundir perfis com agentes ativos.
- Só então retomar conhecimento/tutoriais em trilha própria, com recipes e gates que validem comportamento, não apenas texto transcrito.
