# FP-045-F2 — Busca e otimização confiável de layout

> **Registro no repo (Claude, 2026-10-23):** recebida do Felipe como *FP-045*; renumerada para **FP-054** porque FP-045…FP-053 já existem (a FP-045 do repo é a de especialistas/modularização, mergeada). Texto original preservado abaixo; correções e reconciliação com o código ficam na §0 da spec-mãe (`docs/specs/FP-054_spatial_core_reliability_program.md`). Evidências em `docs/reports/fp054/`.

**Pré-requisito:** gates F1 capazes de distinguir PASS, FAIL e BLOCKED.

## Modelo matemático
- Decisão por móvel: posição contínua `(x,y)`, orientação `theta`, dimensões permitidas se parametrizáveis; móveis fixos não são alterados.
- Hard constraints: dentro do domínio, colisões, porta, acesso, folgas, semântica, distâncias obrigatórias e restrições por cômodo/política.
- Soft objectives: folga excedente, acessibilidade prática, alinhamento, uso, simetria e composição, sempre com pesos/versionamento e unidades/normalização.
- `infeasible` é resposta legítima. Nunca escolher solução inválida porque o solver esgotou candidatos ou max time.

## Algoritmo em etapas
1. Detectar regiões livres geométricas e domínios de orientações plausíveis; registrar justificativa para poda.
2. Gerar seeds diversificadas: cantos viáveis, paredes, eixos, regiões centrais, distribuições determinísticas e grid adaptativo como fallback (15 cm não é verdade única).
3. Filtrar candidatos por hard constraints usando índices espaciais e cache seguro de geometria estática; não pular checks caros sem prova matemática.
4. Refinar posições/orientações em espaço contínuo com múltiplos inícios e `scipy.optimize` se aplicável; CP-SAT/constraint programming para escolhas discretas sob benchmark; bounded budget explícito.
5. Reavaliar toda solução final em gate independente (não confiar no score interno do solver).
6. Rankear top N por objetivos transparentes + heurística explicada de desempate; emitir relatório das tentativas, causas de rejeição, conflito entre restrições e alternativas.

## Fixture suite / Oracle
- Sala sintética livre, sala com sofá, rack, acesso em arco, passagem estreita, sala sem lugar para mesa, sala com duas áreas viáveis, mesa com cadeiras em 4 orientações.
- Comparar solver vs referência enumerativa fina em cenas pequenas, invariantes e soluções manualmente calculáveis.
- Testes de qualidade com thresholds objetivos definidos ANTES do algoritmo e não recalibrados para fazê-lo passar.
- A mesa não pode bloquear porta; mudança de grade não deve resultar em solução materialmente pior sem motivo; resultado com hard violation tem score descartado.

## Métricas e gates
- Coverage de candidatos/áreas, taxa de feasible correta, falsa viabilidade=0 nos casos certificados, solução não dominada entre top N, minimal clearance, p50/p95, memória.
- Toda escolha com `hard_constraints`, `soft_scores`, `policy_version`, `algorithm_version`, seed, candidatos avaliados e explicação.
- Se nenhuma solução: `INFEASIBLE` com constraints conflitantes e sugestões de alterações de móveis (sem aplicá-las).
