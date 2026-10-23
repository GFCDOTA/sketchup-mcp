# FP-045-F4 — Prova integrada independente e SketchUp real

> **Registro no repo (Claude, 2026-10-23):** recebida do Felipe como *FP-045*; renumerada para **FP-054** porque FP-045…FP-053 já existem (a FP-045 do repo é a de especialistas/modularização, mergeada). Texto original preservado abaixo; correções e reconciliação com o código ficam na §0 da spec-mãe (`docs/specs/FP-054_spatial_core_reliability_program.md`). Evidências em `docs/reports/fp054/`.

**Pré-requisito:** F1/F2/F3, com micro L2 obrigatório em mudanças no Ruby ou no pipeline.

## Harness independente
- Conectar `consensus -> scene -> planner -> validators -> MCP -> Ruby -> SKP -> reopen -> independent inspector`.
- O inspector não deve reutilizar exatamente a rotina que gerou o layout para confirmar a sua própria validade; calcular footprints/portais/transformações a partir de entidades materializadas no SKP.
- Guardar versões de ambiente, SketchUp, Ruby, plugins, caminho de entrada, SHA, seeds, logs, tempo, entidades geradas e hashes.

## Casos reais
- Para cada cômodo suportado: gerar, salvar, reabrir; validar escala, orientação, transform, GUID/ID, nesting groups, parede/porta/janela e colisão real com furniture.
- Verificar arco de porta, acesso a elementos utilizáveis, cadeiras recolhidas/puxadas, circulação real e folgas; comparar com plano Python e registrar delta numérico.
- Comparar top/iso com referência e screenshots; métricas automáticas para colisão, envelope e distância, revisão humana somente para atributos não mensuráveis de gosto.
- Rodar smoke de cada `su_*` aplicável e reinício idempotente; validar timeout, erro de Ruby, SketchUp ausente, arquivo travado, recuperação.

## Estados e aceite
- `L1_PASS` lógica Python; `L2_PASS` materialização real; `VISUAL_REVIEWED` opinião registrada; `BLOCKED_L2` ambiente indisponível; nunca confundir.
- Nenhuma mudança relevante declara DONE sem SKP reaberto e relatório independente, com evidências anexas e sem false green.
- CI Linux isolado de job Windows; prova Windows só quando runner com SketchUp de fato rodar.
