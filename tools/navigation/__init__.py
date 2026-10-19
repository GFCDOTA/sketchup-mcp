"""tools.navigation — ferramentas de NAVEGAÇÃO do repositório (FP-043).

- `consumers`: quem consome um arquivo/diretório (imports por AST + referências em texto),
  para decidir mover sem quebrar entrypoint (Hard Rule #1 do workspace: grep refs ANTES).
- `p0_map`: o mapa origem/destino/consumidores/risco da reorganização e o gate que o
  mantém exato (cobre toda a raiz, tools/, scripts/, ops/ e interior/).

Só lê a árvore rastreada pelo git; não move, não escreve, não importa o código analisado.
"""
