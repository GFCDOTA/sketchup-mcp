# FP-062 — relocação dos módulos de produto: prova L2 do pipeline `furnish_apartment`

A prova canônica desta PR fica em `final/` (`regression_summary.md`, `planta_74_after.skp`, renders top e iso, log do pipeline).
Este README descreve como a prova foi executada.

## Commit sob prova

- Código avaliado: `a3499dbd` (três commits sobre a base `7ea99dae` = `origin/develop`).
- Árvore limpa durante a execução (`git status` vazio no commit sob prova).
- A própria pasta de evidência é um commit posterior, sem código.

## SketchUp

- Versão: SketchUp 2026, 26.0.429.
- Executável: `C:\Program Files\SketchUp\SketchUp 2026\SketchUp\SketchUp.exe`, aberto pelo `furnish_apartment` com `-RubyStartup place_layout_skp.rb` e o `.skp` base como argumento posicional.
- Base usada: uma **cópia** de `artifacts/planta_74/planta_74.skp`, feita em scratch. O original não foi aberto para escrita.
- PIDs: o driver encerra apenas o processo que abriu (`owned_su.terminate()`), nunca por nome de imagem. Os PIDs não foram gravados nesta execução. Depois do término, `tasklist` não mostrou nenhum processo SketchUp.

## Reprodução

1. Copiar `artifacts/planta_74/planta_74.skp` para uma pasta de scratch.
2. Com o venv canônico do sketchup-mcp:

   ```powershell
   E:\Claude\apps\sketchup-mcp\.venv\Scripts\python.exe artifacts\review\planta_74\fp062-relocation\reproduce\run_furnish.py <arvore> <out_dir> <gallery_dir> <base_copia.skp> tools.sketchup.pipeline.furnish_apartment
   ```

   `<arvore>` é a raiz da árvore a testar. Para a baseline use `tools.orchestration.furnish_apartment` como último argumento.
3. O driver redireciona o corpus de galeria para `<gallery_dir>`. Sem isso, `furnish_apartment` acrescenta um item de galeria `PENDING_VISION` ao corpus do workspace.
4. Comparar o log `planta_74_furnished_log.txt` (SHA-256) e os renders top e iso.

## Verificações feitas

- Log do pipeline idêntico entre baseline (`7ea99dae`) e relocação (`a3499dbd`): mesmo SHA-256 `3496fa96b83d6c80b7c3d0a5bbdd28235f414ae2e304c629e05b7624f8c2cac0`, 414 linhas. O log não é versionado (`.gitignore`, regra `*_furnished_log.txt`); a identidade é o hash.
- Renders: diferenças de 2 a 4 px, delta máximo 3 a 10. Um controle baseline × baseline dá a mesma ordem de grandeza.
- Arquivos protegidos (fixtures de `planta_74` e `quadrado`, `artifacts/planta_74/planta_74.skp`, `artifacts/planta_74/furnished/*.skp`): SHA-256 idênticos nas duas árvores, 0 diferentes.
- Subconjunto `planta74_scale`: 217 passed, 1 xfailed, igual ao baseline.

## O que esta prova é

Equivalência de execução do `furnish_apartment` (decisões, bboxes, gates e renders) entre baseline e relocação, em SketchUp real.

## O que esta prova não é

- **Não é avaliação visual.** `visual = PENDING_HUMAN`. O veredito de aparência é do Felipe, no chat.
- Não cobre `build_plan_shell_skp` (a mudança nele é uma linha de import, não executada aqui) nem os demais módulos relocados em SketchUp.
- Não é comparação byte a byte do `.skp`: o arquivo varia entre execuções idênticas do baseline.
- Não é prova de qualidade de design, de layout ou de fidelidade ao PDF.
