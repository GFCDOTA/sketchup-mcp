---
paths:
  - "**/*.rb"
  - "tools/sketchup/**"
  - "tools/rooms/**/sketchup.py"
---
# Jobs Ruby e executor SketchUp

- **Editar, não reconstruir:** nunca `model.entities.clear!` no modelo do usuário; `defn.entities.clear!` só numa definição que o
  próprio job criou (padrão de `cabinet_build.rb`/`shaker_build.rb`). O job opera numa cópia e só no que criou.
- **Idempotente:** reexecutar o mesmo pedido não duplica nada — remover antes as definições órfãs com o prefixo do `request_id`
  (`purge_unused` depois).
- **Uma operação desfazível:** `model.start_operation(..., true)` … `commit_operation`; erro → `abort_operation` e status de falha no JSON de saída.
- **Unidades:** Python fala metros; o Ruby converte uma vez, na borda (`v.to_f * IN_PER_M`). Medida nunca nasce dentro do Ruby.
- **Caminhos:** `Path(...).resolve()` antes de passar ao SketchUp (path relativo salva no CWD dele). Scratch do job vai para `runs/`,
  nunca ao lado de um `.skp` de `artifacts/` ou `fixtures/`.
- **Processo:** abrir a partir de uma cópia de template `.skp`; registrar o PID que subiu; fechar só esse PID. `taskkill /IM` é proibido.
- **Prova:** depois de salvar, reabrir em outro processo e inspecionar (`*_inspect.rb`); o verificador Python compara medidas do modelo
  reaberto com o plano (erro máximo registrado), nunca confia no que o build disse de si mesmo.
- Ruby sem SketchUp nesta máquina não roda: cobrir com teste de contrato textual e marcar a prova como pendente de L2.
