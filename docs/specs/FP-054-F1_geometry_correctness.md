# FP-045-F1 — Regras espaciais, fail-closed e contraprovas

> **Registro no repo (Claude, 2026-10-23):** recebida do Felipe como *FP-045*; renumerada para **FP-054** porque FP-045…FP-053 já existem (a FP-045 do repo é a de especialistas/modularização, mergeada). Texto original preservado abaixo; correções e reconciliação com o código ficam na §0 da spec-mãe (`docs/specs/FP-054_spatial_core_reliability_program.md`). Evidências em `docs/reports/fp054/`.

**Pré-requisito:** F0 baseline rastreável.

## Domínios de auditoria
- `SceneSnapshot` imutável e IDs tipados; escala única, orientação, frame local/global, metros/polegadas/pontos e tolerância única por domínio.
- Validar polígonos invalid/empty, furos, multipolígonos, geometrias tangentes, precision snapping, `buffer`, `contains` vs `covers` e limiares de inclusão.
- Diferenciar `occupied_floor`, `overhead`, `walkable`, `wall`, `clearance_envelope`, `swing_arc` e geometria 3D; obstruction policy independente do nome do móvel.
- Portal obrigatório ausente/sem tipo/sem geometria precisa produzir `BLOCKED_MISSING_INPUT`; casos legítimos de portal único explicitamente `NOT_APPLICABLE` conforme contrato e nunca `PASS` de circulação sem prova.
- Corredor com folga contínua da região interna do portal de origem à região interna do destino; testar estreitamentos e linha central enganadora; não aceitar mera proximidade (distância <= limiar) sem conexidade real.
- Cadeiras: posição de uso, envelope puxado, colisão entre cadeiras e móveis, orientação, recuo e largura; garantir que todos componentes esperados existem antes de avaliar.
- Arcos de porta: abertura total e parcial, dobradiça, espessura, sentido; portas de correr e passagens sem arco tratados distintamente.

## Primeiro pacote adversarial (red -> green)
1. Zero portal, 1 portal, 2 portais conectados, 2 portais desconectados; portal omitido inadvertidamente.
2. Dois polígonos livres separados por vão de 20 cm; corredor nominal 90 cm mas gargalo 70 cm; portal 30 cm distante da região livre.
3. Mesa na trajetória da porta; mesa tangente ao arco com epsilon ±; mesa rotacionada 15°, 45°, 90°.
4. Cadeiras ausentes/desidentificadas/duplicadas, puxadas bloqueadas, cadeiras encostadas entre si, colisão com rack/sofá.
5. Obstáculos overhead, objetos walkable, dimensões sem escala e IDs repetidos.
6. Polígono com buraco, interseção na borda, multipolígono desconectado, rooms convexos e côncavos.

## Property-based / metamórficos
- Rigid transforms com mesma política devem preservar status e distâncias.
- Escala convertida por unidade de forma bijetiva preserva interpretação física.
- Acrescentar um obstáculo bloqueador não pode aumentar área transitável.
- Permutar ordem de objetos não pode mudar resultado; mesmo seed + input implica saída idêntica.
- Gate sem elementos obrigatórios retorna BLOCKED; não pode virar PASS por exceção engolida.

## Critérios de aceite
- Teste que prova cada bug falha na baseline, passa no novo código; preservar contraprova no repositório.
- `ConstraintResult` sempre traz reason code, medição/unidade/threshold e evidência ou motivo da ausência.
- CI em ambas as escalas; nenhuma fixture canônica adulterada; diffs de efeito explicados.
- Revisão independente por especialista em geometria + testes, não pelo mesmo implementador apenas.
