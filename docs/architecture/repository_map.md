# Mapa do repositório

Onde mora cada responsabilidade, o que **existe hoje** e o que ainda é **previsto** (FP-043). O estado de cada
caminho nas tabelas abaixo é conferido por teste (`python -m tools.navigation.docs_check`): `existe` exige o caminho
presente, `previsto` exige o caminho ausente. Quando uma fase cria uma pasta, este arquivo muda no mesmo PR.

Partir daqui: [README](../../README.md) · de onde veio e para onde vai cada arquivo: [guia de migração](migration_guide.md) ·
decisões e riscos por item: [mapa P0](../specs/FP-043_P0_map.md).

## 1. Do pedido ao `.skp`

```
pedido (humano ou agente)
  → protocolo     tools/mcp_server/server.py        registra as 18 tools; sem regra de domínio
  → verbos        tools/sketchup/jobs.py            su_*: valida entrada; destino em tools/sketchup/paths.py
  → processo      tools/sketchup/batch.py + tools/sketchup/process.py   SketchUp próprio via -RubyStartup; resultado em JSON
  → Ruby          tools/sketchup/ruby/*.rb          jobs MCP (inspect, render, apply_edits)
                  tools/*.rb                        build do shell, mobília, vray (legado, carregados por caminho)
  → saída         runs/<planta>/mcp/<job>_<data>/   scratch; promoção → artifacts/<planta>/ (promote_canonical)

planejamento (antes do Ruby, sem SketchUp)
  consensus.json → tools/room_type.py (classifica o cômodo) → tools/rooms/dispatch.py (escolhe o brain)
  → tools/rooms/<cômodo>/ (planner + regras) → caixas/peças → tools/place_layout_skp.rb (materializa)
```

Quem decide o quê: **cômodo** decide posição e regras do ambiente; **shared** guarda geometria, materiais e builders
reutilizáveis; **sketchup** executa e inspeciona, sem decidir decoração; **mcp_server** só expõe.

## 2. Diretórios

| Caminho | Estado | Responsabilidade |
|---|---|---|
| `core/` | existe | IDs, unidades, escala (`core.scale` congela `PT_TO_M` no 1º import) e observabilidade |
| `interior/` | existe | semântica e composição de cena/intenção; adapters de render (não duplicam planners de `tools/rooms/`) |
| `tools/rooms/` | existe | dono dos cômodos: um pacote por ambiente + `shared/`, `dispatch.py`, `registry.py`, `manifest.v1.json` |
| `tools/rooms/shared/` | existe | geometria, materiais e builders paramétricos usados por mais de um cômodo |
| `tools/sketchup/` | existe | processo, jobs e inspeção no SketchUp (verbos `su_*`) |
| `tools/mcp_server/` | existe | protocolo MCP e registro das tools; apontado pelo `.mcp.json` do workspace |
| `tools/navigation/` | existe | consumidores de um arquivo, mapa de reorganização e verificação desta documentação |
| `tools/interior_studio/` | existe | loop do estúdio de interiores (juízes, propostas, ponte de consulta) |
| `tools/pdf_knowledge/` | existe | ingestão de PDFs de referência para um índice pesquisável |
| `tools/prompts/` | existe | prompts do oráculo visual e do gate de consulta |
| `tools/claude_bridge/` | existe | `skp_inventory` (MCP) e `WORKSPACE_ROOT`; o nome vem do cockpit removido |
| `tools/validation/` | previsto | gates e auditorias transversais (hoje `tools/*_gate.py`, `tools/*_audit.py`) |
| `tools/rendering/` | previsto | utilidades de imagem/render e pós-processamento (hoje `tools/render_*.py`) |
| `tools/orchestration/` | previsto | sequenciamento entre cômodos e executores (hoje `tools/furnish_apartment.py`) |
| `tools/knowledge/` | previsto | RAG, memória do projeto, banco de referências |
| `tools/oracle/` | previsto | juízes visuais e consultas; o veredito visual continua só do Felipe |
| `projects/` | previsto | fonte identificada do projeto (a planta em PDF, hoje na raiz) |
| `fixtures/` | existe | inputs canônicos e sintéticos; protegidos |
| `artifacts/` | existe | entregáveis canônicos (`artifacts/<planta>/`) e evidência (`artifacts/review/`) |
| `references/` | existe | fontes, recipes e referências de design |
| `assets/` | existe | recursos de entrada reutilizáveis (`assets/textures`) |
| `renders/` | existe | renders históricos do programa do sofá; classificação em P2 |
| `runs/` | local (ignorado pelo git) | scratch criado em tempo de execução; não faz parte da árvore versionada |
| `tests/` | existe | regressões em Python puro (marker `planta74_scale` separa a escala) |
| `scripts/` | existe | automação e geradores Ruby do sofá (migram ao cômodo `living` em P4) |
| `ops/` | existe | operação: painel do estúdio (`ops/estudio-front/`) |
| `docs/architecture/` | existe | esta pasta: mapa, guia de migração, rotas de navegação |
| `docs/specs/` | existe | especificações e manifestos (FP-042, FP-043) |
| `docs/handoffs/` | existe | passagens de bastão datadas |

Até P4 terminar, boa parte do código ainda está direto em `tools/`. Isso é o estado atual, não o desenho: o destino
de cada arquivo está no [mapa P0](../specs/fp043_p0_map.v1.json).

## 3. Cômodos

Cada cômodo é um pacote em `tools/rooms/<cômodo>/`; o manifesto
([`manifest.v1.json`](../../tools/rooms/manifest.v1.json)) declara providers, fontes de conhecimento e estado.
**Nove perfis não são nove brains independentes**: o estado abaixo é o que o manifesto declara.

| Caminho | Estado | O que há de fato |
|---|---|---|
| `tools/rooms/living/` | existe | brain próprio: planner, mobília, classes de sofá/rack/mesas/poltrona |
| `tools/rooms/bedroom/` | existe | brain próprio: layout, designer, cama e guarda-roupa compartilhados |
| `tools/rooms/kitchen/` | existe | brain próprio: layout galley, âncora hidráulica da pia ([README](../../tools/rooms/kitchen/README.md)) |
| `tools/rooms/bathroom/` | existe | brain próprio: layout e validação de ambiente molhado |
| `tools/rooms/service/` | existe | brain composto: área de serviço + terraços, como no consensus |
| `tools/rooms/balcony/` | existe | só `__init__.py`: sem brain independente; participa do `service` |
| `tools/rooms/closet/` | existe | só `__init__.py`: reusa peças de guarda-roupa do quarto |
| `tools/rooms/home_office/` | existe | só `__init__.py`: reusa o designer do quarto |
| `tools/rooms/circulation/` | existe | só `__init__.py`: validação (`circulation_gate`), sem mobiliário |

## 4. Convenção de um módulo de cômodo

A cozinha é o primeiro módulo a seguir a convenção; os demais a recebem em P4/P5.

| Caminho (relativo ao módulo) | Estado | Conteúdo |
|---|---|---|
| `tools/rooms/kitchen/README.md` | existe | comece aqui: entradas, fluxo, dependências, capacidades, testes, provas e limites |
| `tools/rooms/kitchen/specialist.md` | previsto | papel, decisões, fontes, ferramentas permitidas e condições de parada (P5) |
| `tools/rooms/kitchen/specialist.v1.json` | previsto | IDs do perfil, roteamento e estados, sem autorização implícita (P5) |
| `tools/rooms/kitchen/knowledge/index.v1.json` | previsto | referências por ID às recipes canônicas, sem copiá-las (P5) |
| `tools/rooms/kitchen/capabilities/` | previsto | adapters de capacidades específicas da cozinha (P6) |
| `tools/rooms/shared/cabinet/` | previsto | builder compartilhado de gabinete: **não existe** (P6) |

## 5. O que é prova, e de quê

| Nível | O que prova | Onde está |
|---|---|---|
| L1 | cálculo e plano em Python (brains, gates, testes) | `tests/`, `tools/run_deterministic_gates.py` |
| L2 | o que o SketchUp real materializou, salvou, reabriu e foi inspecionado | `artifacts/review/l2_fp042_20261019/` |
| Visual | aparência vs PDF | só o Felipe; nunca automático |

Capacidade de conhecimento (recipes em `references/sketchup/knowledge/`) é **consultiva**: nenhuma recipe autoriza
execução. Técnica sem capacidade implementada responde `BLOCKED_CAPABILITY_MISSING`; o plano consultivo do gabinete
(`cabinet_plan` em `tools/sketchup/knowledge.py`) não é plano de operação.

## 6. Rotas de navegação

Cinco perguntas que este mapa precisa responder em até três cliques a partir do README. As rotas e os símbolos de
resposta estão em [`navigation_routes.v1.json`](navigation_routes.v1.json) e são verificados por teste.

| Pergunta | Rota |
|---|---|
| Onde está o planner da cozinha e a regra que protege a pia? | README → este mapa → [README da cozinha](../../tools/rooms/kitchen/README.md) |
| Onde está o builder compartilhado de gabinete e quem o usa? | README → este mapa → [README da cozinha](../../tools/rooms/kitchen/README.md) (hoje: **não existe**) |
| Existe porta Shaker? | README → este mapa → [README da cozinha](../../tools/rooms/kitchen/README.md) (recipe sim, capacidade não) |
| Qual teste e qual evidência L2 provam uma capacidade? | README → este mapa → [README da cozinha](../../tools/rooms/kitchen/README.md) (cozinha), ou [relatório L2](../../artifacts/review/l2_fp042_20261019/README.md) |
| Onde entra o MCP, quem executa no SketchUp e onde sai o `.skp`? | README → este mapa (seção 1) |

## 7. Avisos

- **CLIs legadas que fecham o SketchUp por nome** (`taskkill /IM SketchUp.exe`): lista no [README](../../README.md#rodar).
  Prefira as tools `su_*`, que só fecham o PID que elas mesmas abriram.
- **Caminhos montados em tempo de execução** (Ruby carregado por caminho, `REPO / f"{fix}.pdf"`) não aparecem em busca
  textual: use `python -m tools.navigation.consumers <caminho>` e revise à mão antes de mover qualquer coisa.
- **Escala:** `core.scale` lê `PT_TO_M` uma vez por processo. `planta_74` usa `0.0259`; fixtures sintéticas e o
  `quadrado`, a escala padrão. Nunca misture no mesmo processo.
