# FP-042 — Fechamento do escopo automatizado

P0: inventário exaustivo de todos os arquivos versionados, controle de omissões.
P1: ownership core, shared, infra e fronteiras de import AST.
P2: geometria, escala, materiais e componentes compartilhados.
P3: módulos de sala, cozinha, banheiro, bedroom e service com facades estáveis; 97
caminhos com ownership exato verificado pelo `p3_ownership`.
P4: APIs legadas, scripts, MCP e Studio têm owner; teste de handshake MCP.
P5: documentação, skills, recipes, testes e contratos possuem owner por papel.
P6: preservação Git blob e path de 707 binários e 1.060 referências versionadas.

Merge somente após CI verde com Python 3.11/3.12, gates de fidelidade,
`inventory_gate --strict`, `p3_ownership` e provas de proveniência.

**Não inclui prova SketchUp L2, V-Ray, visual de renders nem revisão semântica
humana de cada documento.** Nenhum arquivo .skp, geometry/fixture ou artefato
protegido foi modificado pela fatia de fechamento.
