# Regression summary — relocação dos módulos de produto (FP-062)

- **Base:** `7ea99dae` (`origin/develop`)
- **Head avaliado (código):** `a3499dbd` (commits: relocação, testes, docs/inventário)
- **Escopo SKP:** `tools/sketchup/shell/build_plan_shell_skp.py` é path-trigger (SKP-proof gate). A mudança nele é uma linha de import em `_auto_promote`, que aponta para a mesma função `promote` no novo caminho. Esse builder **não foi executado** nesta prova.

## Método

- Execução real do pipeline `furnish_apartment.main()` no SketchUp 2026 (26.0.429), com o mesmo `.skp` base copiado para scratch nas duas árvores (baseline `7ea99dae` e relocação `a3499dbd`).
- A galeria de corpus foi redirecionada para scratch; nenhum artefato canônico foi tocado.
- Driver: `reproduce/run_furnish.py` (incluído em `artifacts/review/planta_74/fp062-relocation/reproduce/`).

## Resultados por eixo

1. **Log do pipeline (decisões, bboxes, gates):** idêntico. SHA-256 `3496fa96b83d6c80b7c3d0a5bbdd28235f414ae2e304c629e05b7624f8c2cac0` nas duas árvores, 414 linhas, zero diferenças. Inclui `flat_white_check => PASS`. O log não é versionado (regra `*_furnished_log.txt` do `.gitignore`); a identidade da prova é o hash.
2. **Render antes/depois (top e iso):** diferenças de 2 a 4 px, delta máximo 3 a 10. A comparação baseline × baseline (controle, segunda execução do baseline) dá a mesma ordem de grandeza (4, 2 e 4 px; delta máximo 10, 3 e 10). Trata-se de ruído do renderizador, não de regressão.
3. **Arquivo `.skp`:** o tamanho varia entre execuções idênticas do baseline (3.350.655, 3.350.704 e 3.350.984 bytes). Comparação por bytes não é critério válido aqui; a evidência é o log e os renders acima.
4. **Testes:**
   - subconjunto `planta74_scale`: 217 passed, 1 xfailed, igual ao baseline;
   - suíte padrão (não planta74): 3976 passed, 1 failed; a falha é `tests/test_rooms_index.py::test_committed_index_matches_the_sources` (CRLF do checkout Windows), idêntica ao baseline (traceback idêntico).

## Limites

- Só `furnish_apartment` tem caminho SketchUp testado nesta prova. Os demais módulos relocados têm testes unitários, identidade de módulo e, para `promote_canonical` e `variant_sweep`, o teste de `python -m` (`tests/test_fp062_alias_cli.py`).
- **Aparência não avaliada.** `visual = PENDING_HUMAN`; o veredito visual é do Felipe, no chat.
