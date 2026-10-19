# FP-042 — Auditoria técnica pós-modularização

Data: 2026-10-19. Base auditada: `65f1be7cb6a4828dc76769e59c2168bcb934fe4b`
(`develop`, merge do PR #279). Escopo: fases A–E do kickoff de validação final.

**Resultado: validação automatizada e auditoria concluídas no escopo abaixo;
SketchUp L2 BLOQUEADO; fidelidade visual e fabricação NÃO certificadas.**
Não houve regeneração ou alteração de SKP, fixtures, texturas ou renders versionados.

## Estado remoto confirmado

- HEAD de develop igual ao kickoff; nenhum PR aberto no início da auditoria.
- CI base: https://github.com/GFCDOTA/sketchup-mcp/actions/runs/39244477277
- Quatro jobs aprovados: pytest Python 3.11 e 3.12, fidelity-gates e MCP.
- A aprovação desse CI prova o commit base, não mudanças posteriores.

## A — Arquitetura e compatibilidade

Foram examinados os 50 módulos Python em `tools/rooms`, o manifesto e os
providers. A análise AST ampliada abrangeu 265 módulos de `tools/core/interior`
e 494 arestas candidatas de import (incluindo imports locais e submódulos).
Esse grafo conservador não é um grafo de execução e não certifica ausência
universal de ciclos dinâmicos.

Achado corrigido: o gate de ownership permitia dependências cruzadas por
fachadas históricas. Exemplo: kitchen podia importar `tools.bedroom_layout`
embora a dependência equivalente de `tools.rooms.bedroom.layout` fosse recusada.
Agora o gate resolve 13 fachadas de layouts/classes/planner antes de conferir
ownership; também recusa imports diretos do orquestrador por room/shared.
Imports de fachadas do próprio cômodo continuam permitidos. A checagem entra
explicitamente no job fidelity-gates, além dos testes existentes.

Sete cenários negativos falharam antes da correção. A regressão acrescenta
imports em processos Python novos, nas ordens direta/inversa, cobrindo todos
os módulos de room, fachadas e os nós de orquestração/diagnóstico abaixo.
Aliases públicos e implementação geométrica não foram reescritos.

O grafo conservador encontrou dois componentes cíclicos:

- furnish_apartment / living.furnishing / circulation_gate / variant_sweep /
  geometry_sanity / furniture_overlap_gate: contém arestas tardias de CLI,
  validação e emissão de galeria. Imports frios passam nas duas ordens; isso
  não prova todo caminho possível de chamada em runtime.
- consult_gpt_bridge / ingest / prompt_builder / store: inclui os re-exports
  normais do pacote. Os contratos do bridge são exercitados na suíte existente.

Três pares de funções top-level idênticas foram identificados por AST,
removendo apenas docstrings (mínimo de cinco linhas):

| Função | Implementações | Decisão |
|---|---|---|
| `_fbox` | layout_candidates / rooms.shared.geometry | Duplicação residual geométrica; não consolidada nesta auditoria sem prova de SKP. |
| `_load_consensus` | opening_host_audit / wall_overlap_audit | Pequeno loader em gates independentes; sem mudança necessária para esta validação. |
| `_pack` | rag_freshness / project_memory_db | Adapter de persistência duplicado; sem alteração de storage nesta missão. |

Não confundir ownership resolvido com eliminação de toda duplicação. Outros
helpers com nomes iguais podem ter assinaturas/finalidades diferentes. A análise
não detecta todos os clones semânticos. O campo legado
`legacy_migration_complete=false` do scanner permanece conservador; não invalida
o inventário P0–P6 nem atesta equivalência visual.

## B — Testes e gates

Comandos de reprodução (processos separados por escala):

```bash
python -m pip install -e '.[dev,mcp]'
MPLBACKEND=Agg python -m pytest tests/ -q -m 'not planta74_scale'
MPLBACKEND=Agg PT_TO_M=0.0259 python -m pytest tests/ -q -m planta74_scale
python -m tools.rooms.inventory_gate --strict
python -m tools.rooms.ownership_audit
python -m tools.rooms.p3_ownership
python -m tools.rooms.asset_provenance
python -m tools.rooms.reference_provenance
python -m tools.run_deterministic_gates --fixture planta_74
python -m tools.run_deterministic_gates --fixture quadrado
python -m tools.mcp_server.smoke
python -m tools.mcp_server.stdio_check
```

Resultados finais são registrados na seção de fechamento abaixo. A suíte
abrange dispatch, isolamento, escala, colisões, circulação, vãos, proteção da
arquitetura, âncora hidráulica da cozinha, materiais por módulo, builders,
idempotência de contratos e jobs com doubles. Esses testes não comprovam que
cada operação mutável é idempotente dentro do SketchUp real.

O gate determinístico de planta_74 avaliou 12 aberturas, sem conflitos de host
ou pares de paredes sobrepostas; quadrado avaliou uma abertura. Esses dois gates
não constituem uma avaliação visual completa ou de todas as colisões de móveis.
O smoke e o handshake listaram 18 tools MCP e completaram chamadas reais por
stdio. Chamadas SU indisponíveis e recusas esperadas são resultados válidos do
contrato, não execução real de modelagem.

## C — SketchUp L2 e V-Ray

Sondagem real de `tools.sketchup.jobs` nesta sessão:

| Verificação | Resultado observado |
|---|---|
| Plataforma | linux; platform_supported=false |
| SketchUp.exe / plugin autorun | Não encontrados |
| V-Ray executável | Não encontrado |
| Instâncias SketchUp | Nenhuma |
| status.proof_state | UNVERIFIED_ON_SKETCHUP |
| build_shell com micro-fixture quadrado | UNAVAILABLE — SketchUp exige Windows |
| furnish de planta_74 | UNAVAILABLE — SketchUp exige Windows |
| render_vray | REFUSED — launcher legado usa taskkill por nome de processo |

Não existe acesso nesta sessão ao SketchUp do computador do Felipe. Não foram
fabricados logs de execução, SKPs novos, renders ou comparações antes/depois.
Ruby também não está instalado neste runtime; os testes Ruby opcionais aparecem
como skips na suíte Python. Qdrant/Ollama ao vivo são opcionais e não foram
certificados por doubles.

Sequência necessária no ambiente Windows acessível:

1. Confirmar executável, plugins e versões; manter modo interactive e usar cópias
   de trabalho. Não promover ou regravar os artefatos aprovados.
2. Executar quadrado; inspecionar medidas, peitoril/verga, grupos e materiais.
3. Repetir gabinete sintético e verificar instâncias/definições, transformações,
   peças, folgas, colisões e preservação do shell; provar edição em cópia.
4. Com PT_TO_M=0.0259, executar sala, suítes, cozinha, banheiros e serviço.
   Comparar com contratos e referências aprovadas por cômodo.
5. Preservar SKP + renders top/iso + relatório, hashes, versões e comando exato.
   L2 depende dessas evidências; aparência continua pendente de VISUAL_REVIEW.
6. Não liberar V-Ray até portar e testar o launcher com isolamento por PID.

## D — Conhecimento especializado

Catálogos auditados: `video_recipes.v1.json` (3 fontes, 8 recipes) e
`environment_recipes.v1.json` (10 fontes, 11 recipes); skills
`sketchup-video-knowledge` e `sketchup-room-knowledge`.
Os IDs e referências cruzadas são íntegros. Novas regressões conferem todos os
IDs consultivos do manifesto e se cada provider declarado resolve para uma
função callable. Isso não autoriza mutações por catálogo.

| Categoria | Capacidade presente | Lacuna para técnicas descritas |
|---|---|---|
| Sala | Brain próprio; sofá/rack/mesas e circulação | Sofá orgânico por sweep/mesh e hierarquia de marcenaria não provados em L2 |
| Quartos/suítes | Planners e peças paramétricas compartilhadas | Montagem real, detalhes de cabeceira e ferragens não certificados |
| Cozinha | Layout, módulos e âncora da pia | Materializador de caixaria, recortes e gavetas completos não provados |
| Banheiros | Layout e validação de wet-room | Recortes, montagem e interfaces MEP exigem fixtures reais |
| Serviço/lavanderia | Brain SERVICE composto com terraços | Caixaria e envelopes específicos de eletros não comprovados |
| Varanda | Cobertura consultiva; participa de SERVICE | Sem brain independente de pergolado/jardineira |
| Closet | Peças shared de guarda-roupa | Sem brain independente; portas de correr/ferragens não provadas |
| Home office | Reuso do designer de quarto | Sem brain independente de escritório |
| Circulação | Gate de validação | Sem brain de mobiliário; nenhuma autorização de alterar vãos |

Todas as 19 recipes continuam KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP.
O estudo `cabinet_plan` da fixture existente retornou:
`L1=PASS_SYNTHETIC_CALCULATIONS_ONLY`, `L2=PENDING_SKETCHUP`,
`L3=PENDING_HUMAN`, `plan_state=BLOCKED_CAPABILITY_MISSING`.
Ele produz BOM proposta e bboxes, não Ruby, SKP ou plano de fabricação.
Faltam materializador comprovado, gavetas/ferragens e envelopes de movimento.
Os catálogos são consumidos por skill/consulta local; não são novas tools de
modelagem executável no MCP de 18 ferramentas.

Revalidação externa em 2026-10-19: as sete páginas oficiais responderam com
conteúdo do tema (grupos, componentes, organização, Follow Me, materiais,
posicionamento de textura e índice Ruby). As seis URLs YouTube retornaram erro
de recuperação nesta sessão; isso não permite classificá-las como removidas.
As alegações históricas de transcrição/inspeção visual não foram reexecutadas.
Os três vídeos de ambientes já são rotulados PUBLIC_DESCRIPTION_ONLY.
A cobertura de nove categorias é adaptação de técnicas gerais, não nove cursos
integrais assistidos nem nove implementações avançadas certificadas.

Fontes oficiais verificadas:

- https://help.sketchup.com/en/sketchup/grouping-geometry
- https://help.sketchup.com/en/sketchup/components
- https://help.sketchup.com/pt-br/sketchup/organizing-model
- https://help.sketchup.com/pt-br/sketchup/extruding-follow-me
- https://help.sketchup.com/pt-br/sketchup/adding-colors-and-textures-materials
- https://help.sketchup.com/pt-br/sketchup/positioning-textures
- https://ruby.sketchup.com/method_list.html

## E — Fechamento

- Python local: 3.12.14; pytest 8.4.2, dentro do intervalo do projeto.
- Suíte geral final: **1.711 passed, 19 skipped, 40 deselected**.
- Escala real final, processo separado: **74 passed, 1.730 deselected**.
- Regressões focadas de arquitetura/conhecimento: **23 passed** (subconjunto das suítes).
- Skips: 4 integrações Qdrant/Ollama, 10 testes com Ruby ausente e 5 dependentes
  de builds/geometry_report reais de quadrado ausentes. Nenhum skip equivale a PASS.
- 12 casos de regressão acrescentados; sete negativos demonstraram a lacuna
  antes da correção. Imports frios direta/inversa passaram.
- Gates de inventário, architecture/tooling/knowledge ownership, P3 e fronteiras:
  PASS; inventário final de 1.808 entradas, zero pendências.
- Proveniência: 707 binários e 1.060 referências preservados por blob/path.
- Fidelity planta_74/quadrado, smoke MCP e handshake stdio: PASS.
- Ruff nos três arquivos Python alterados e diff-check: PASS.
- O smoke SU-free de quatro variantes também passou dentro da suíte geral;
  seus renders sintéticos e veredictos PENDING_VISION não constituem L2.
- Python 3.11 e o commit candidato precisam dos checks remotos obrigatórios;
  o merge é condicionado aos quatro jobs verdes. A URL/veredito da execução
  final fica registrada no PR que entrega esta auditoria.
- SKP-proof: N/A nesta alteração de gate estático, testes, CI e documentação;
  nenhum algoritmo de modelagem ou arquivo de entrada foi alterado.

Pendências explícitas: execução L2 em Windows, evidência visual humana e
materialização avançada das recipes. Duplicações e ciclos estáticos acima
permanecem registrados; não representam falha de CI nem prova de L2.
