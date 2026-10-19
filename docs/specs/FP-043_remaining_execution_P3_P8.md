# FP-043 — Spec executável de conclusão (P3 residual → P8)

**Estado:** PLANO DE EXECUÇÃO; a existência deste documento não prova execução.
**Criado:** 2026-10-19.
**Baseline verificada:** `develop` = `d2e952c4b4ad30317305e18ada4dfdbbdb54ca65` (PR #296).
**Executor-alvo:** Claude Code no workspace Windows com SketchUp 2026, ou agente com GitHub + testes Python; L2 só no Windows real.
**Missão:** concluir integralmente as pendências da [FP-043 original](FP-043_repository_navigation_and_room_specialists.md), sem reexecutar o que já foi aceito e sem criar falsas aprovações.
**Fatos dominantes:** [FP-042 L2](../../artifacts/review/l2_fp042_20261019/README.md), [mapa P0](fp043_p0_map.v1.json), [decisões abertas](FP-043_open_decisions.md), [inventário FP-042](fp042_inventory.v1.json), [guia de migração](../architecture/migration_guide.md).

> Esta é a instrução operacional de execução, não uma nova fonte de verdade sobre cotas,
> estética ou aprovação do apartamento. Em conflito, vencem Constituição / regras do
> repositório, PDF + consensus + referência aprovada e contratos/gates versionados.
> A spec original define o produto; este documento define a fila concreta para terminá-lo.
> Conferir o HEAD, PRs e evidências reais antes de alterar qualquer arquivo: o baseline
> acima é um checkpoint, **não** um SHA a ser usado como se fosse sempre atual.

## 0. Política de execução autônoma

1. **Continuar pelas fases sem pedir autorização para cada PR técnico.** Abrir branches a partir de `develop` atualizado, trabalhar em fatias pequenas, esperar todos os checks aplicáveis verdes, dar merge em `develop` e registrar commit/PR. Não deixar PRs abandonados.
2. **Nunca ignorar gate vermelho.** Falha, timeout, skip indevido ou evidência ausente = FAIL / INCOMPLETE / BLOCKED / NOT_RUN, com causa e etapa seguinte. Não reclassificar um teste como skip, reduzir limites ou trocar expected apenas para obter verde.
3. **Respeitar o ambiente.** Python/CI headless prova L1, contratos e integração MCP sem SketchUp. SketchUp 2026 no Windows é obrigatório para L2. `--mode headless` proibido em dev local; usar `interactive`. Se ambiente indisponível, executar tudo o que for independente e documentar somente o segmento bloqueado.
4. **Proteger fontes e modelos.** Não alterar `fixtures/planta_74/`, `fixtures/quadrado/`, `assets/`, fontes/consensus, `.skp` canônico, renders aprovados ou snapshots protegidos sem a autorização específica prevista. Não mover/promover artefatos por conveniência. Trabalhar em `runs/` e preservar outras sessões, com evidência final em `artifacts/review/` conforme política.
5. **Aparência exige revisão do Felipe.** Reparar determinismo com contrato fixo é trabalho técnico; mudança estética/canônica precisa de comparação e estado `VISUAL_REVIEW`, nunca autoatribuir `APPROVED`. D-001 não é licença para atualizar referência protegida.
6. **Isolar processos e protocolo.** Jamais `taskkill /IM SketchUp.exe` ou equivalente global, jamais usar arquivo de controle global compartilhado; fechar apenas instância própria identificada e preservar janela humana. Stdout de MCP é somente JSON-RPC.
7. **Evitar duplicação.** Um owner/implementação por comportamento; fachada legada delega. Não criar pacote vazio, `misc`, um segundo orquestrador/registry, ferramenta executável implícita nem uma "IA especialista" fictícia por módulo.
8. **Não confundir conhecimentos e provas.** Fonte vista por descrição não significa tutorial assistido. Recipe consultiva não significa capacidade implementada; teste de cálculo não é L2; render não prova geometria; L2 não prova estética/fabricação.
9. **Coordenar agentes.** Conferir branches/PRs/HEAD antes de cada fatia; não reescrever histórico ou força-push de colega. Rebase/merge com `develop` e resolver conflito por evidência, preservando o trabalho concorrente.
10. **Marcar progresso concretamente.** No final de cada PR atualizar mapa/inventário/documentação aplicável e quadro de execução (`PENDENTE / EM_ANDAMENTO / DONE / BLOCKED_DECISION / BLOCKED_ENV`), com links e testes reproduzíveis. Não marcar `DONE` no planejamento sem evidências.

## 1. Snapshot que NÃO deve ser refeito

| Já integrado no checkpoint | Prova do merge | Implicação |
|---|---|---|
| P0 — mapa de reorganização e gate; P1 — README, links, navegação; P2 — limpeza da raiz | PRs #287–#289 e spec #286 | Apenas revalidar contra HEAD; não recadastrar tudo |
| P2/P3 — resolvedor único do PDF e movimentação protegida | PRs #290 e #292 | `projects/planta_74/source/planta_74.pdf` e `core.project_sources` são o contrato |
| Decisões documentadas D-001…D-006 | PR #291 | Não simular que foram resolvidas |
| P3 — stdout MCP/preload, launcher isolado e escala física ancorada | PRs #293–#295 | Priorizar provas Windows e possíveis regressões, não recodificar sem repro |
| P3 — remoção de encerramento global em launchers legados identificados | PR #296 | Anti-regressão L1 verde, **smoke Windows ainda não feito** |

Estado de partida: nenhum PR aberto na verificação deste documento. A spec-mãe conserva
sua baseline inicial por rastreabilidade histórica. A execução desta spec **não**
invalida aceites P0–P2 e não substitui `FP-043_open_decisions.md`.

## 2. Dependências e ordem crítica

`P3a` (analisar/proteger falhas de gate e runtime) pode ocorrer em paralelo lógico
com `P4a/P4b` (migração de código que não altera comportamento). Entretanto:

- Sem segurança do launcher/processo/MCP (`P3b`) não liberar escrita nova em SketchUp.
- Sem plano validado/catalogado (`P5`) não liberar comando de gabinete (`P6/P7`).
- Sem L2 real de materialização (`P6`) não declarar a capacidade como `L2_PASS` nem sucesso E2E (`P7`).
- Ausência de decisão humana afeta só o item correspondente; continuar o resto.
- O objetivo final de `P8` pode ser `ENTREGA_PARCIAL_COM_BLOQUEIOS`, **nunca "FP-043 completamente pronta"** com critérios não satisfeitos.

Ordem recomendada: **P3a / P4a → P4b–P4d → P5a–P5c → P3b L2 Windows → P6a L1 → P6b L2 → P7 → P8**.
Quando P3 requer mudança de layout, separar a correção e o veredito visual.

## 3. P3 residual — estabilizar os defeitos reais

### P3a. Gates, contratos e falhas reproduzíveis (L1; sem SketchUp)

**P3a-01 — gates com `--report`.** Reproduzir `python -m tools.run_deterministic_gates --fixture planta_74 --report artifacts/planta_74/geometry_report.json` e o equivalente com `quadrado` + seu relatório. Se `railing_match` ou `position_fidelity` falharem sobre referência canônica, localizar a divergência exata entre schema, coordenadas, unidades, consensus e gate. Escrever teste de repro que falha antes, corrigir o *bug comprovado* sem suprimir achado real, sem alterar relatório/expected canônico, e testar casos negativos: deslocamento de abertura, omissão de grade, escala errada. `FAIL` real permanece `FAIL` até correção autorizada.

**P3a-02 — polígonos sintéticos.** Reproduzir o guarda-roupa 4,5 cm na parede oeste e o caso de circulação da varanda sintética. Identificar se o polígono de cada fixture indica eixo, face interna ou limite externo; comparar com o contrato do consensus. Criar **fixture sintética nova e não protegida** + teste de convenção e teste de input inválido; não sobrescrever `fixtures/quadrado`/`planta_74` nem "ajeitar" o planner para uma entrada incorreta. Se a semântica atual for ambígua, registrar o caso em `FP-043_open_decisions.md` e deixar apenas esse cenário bloqueado.

**P3a-03 — colisões por cômodo sobre a planta de produção.** Capturar antes/depois por geometria planejada e por inspeção L2, não apenas desenho 2D. Confirmar no HEAD:
- `LIVING`: tampo da mesa de jantar dentro do giro da porta `h_o000` (36 cm²) e painel TV 5 cm no retorno de parede.
- `SUITE 01`: segundo criado-mudo 6,3 cm dentro da parede por 42 cm.
- `BATHROOM` / lavabo: porta-escova dentro do giro de `h_o001` (65 cm²).
- `BANHO 01`: piso do box 4,1 cm sob parede; `BANHO 02`: ralo 2,6 cm na parede.
- Sintéticos: circulação da porta da varanda e armário em parede; não converter `WARN` de circulação em sucesso silencioso.

Para cada achado: fixture/repro, owner correto (`living`, `bedroom`, `bathroom`, ou shared se regra transversal), correção de planner mínima sem violar hidráulica, portas ou arquitetura, regressão por ambiente e teste integrado. Mudança de aparência abre revisão visual; **não promove modelo canônico por conta própria**. `SUITE 02`, cozinha e SERVICE atuais viram controles de não-regressão.

**P3a-04 — peitoril do quadrado (D-001).** Preservar a referência 0,90–2,10 m e registrar diferença do builder 1,50–2,10 m (além de piso e `WindowSash`). Manter os testes condicionais transparentes; não esconder a divergência por ausência de `runs/`. Preparar comparação/renders e alternativas A/B/C existentes; exigir decisão explícita antes de re-baseline, alteração de fixture ou mudança estética. Continuar P4–P7 independentemente.

**P3a-05 — health gate (D-006).** Diagnosticar `repo_health_gate` e as 4 ocorrências documentadas. Corrigir automaticamente apenas defeitos cuja autoridade está estabelecida; alterações em evidência protegida ou mudança de política continuam condicionadas à decisão. Nenhum teste falso para mascarar erros. O CI só é alterado depois de reproduzir comportamento desejado.

### P3b. Segurança do executor e L2 real (Windows)

**P3b-01 — processo e startup.** Testar launcher isolado com duas janelas simultâneas: (a) SketchUp humano aberto, (b) job pertencente ao MCP. Provar que job executa só em (b), que close/timeout só afeta (b), que janela (a) e arquivos não salvos sobrevivem, que não há `autorun_control.txt` global. Inspecionar as dez entradas alteradas no PR #296, incluindo PowerShell; qualquer encerramento por PID só vale para PID comprovadamente criado pelo próprio job. Medir saídas normais e erro/timeout; registrar log/trace. Verificar Job Object com cliente Python e Claude Code/Node e efeitos do encerramento do servidor.

**P3b-02 — MCP estrito e operações positivas.** Provar no Windows `su_status`, `su_build_shell`, `su_furnish`, `su_inspect`, `su_apply_edits`, `su_close`, `su_open` e `su_render` (preset válido) pelo cliente real. Revalidar `su_render_vray` se instalação/licença presente; falha de V-Ray por licença vira bloqueio específico, não bloqueia o renderer básico. Em `su_open` validar a semântica de janela intencionalmente mantida aberta (não fechar por side effect); em `su_render` verificar arquivo de saída e inspeção. Stdout não pode conter logs; preload não pode travar; retorno não pode indicar sucesso sem arquivo válido.

**P3b-03 — modelos regressivos.** Reconstruir sem substituir canônicos `quadrado` e `planta_74` com os ambientes corretos de escala (default vs `PT_TO_M=0.0259`), executar scale-anchor independente (inclusive modelo com fator errado), topologia, abertura 3D, porta, integridade/assinatura, save/reopen e medidas. Rodar ambientes afetados individualmente e integrados. Capturar versão SketchUp, PIDs, commits, hashes e parâmetros.

**Saída de P3:** defeitos determinísticos solucionados ou bloqueados por decisão documentada; protocolo/processo seguro medido no Windows; nenhuma colisão escondida por threshold novo; nenhuma aprovação visual automática.

## 4. P4 — migrar código ativo por responsabilidade, exaustivamente

**Fonte de execução:** `docs/specs/fp043_p0_map.v1.json`. Há **170 itens classificados para P4** no checkpoint; isso **não** significa 170 movimentos. Respeitar `disposition`, `destination`, `compat`, risco e decisões. Usar `python -m tools.navigation.consumers <caminho>` para cada movimento e auditar também strings, Ruby `require_relative`, PowerShell e `Path(__file__).parents[n]`.

**P4a — shared/cozinha:**
- Migrar implementações realmente reutilizáveis para `tools/rooms/shared/` ou `core/` conforme o mapa; apenas lógica de cozinha em `tools/rooms/kitchen/`.
- Consolidar layout/ergonomia/âncora hidráulica da cozinha em owner único; preservar teste de pia na parede oeste e compatibilidade de `tools/kitchen_layout.py`, `tools/kitchen_ergonomics.py` etc.
- Planejar a fronteira futura de `tools/rooms/shared/cabinet/`, sem mover `cabinet_plan` consultivo para um executor por engano.

**P4b — demais cômodos:**
- `living`: sofá, layout, decor, scripts Ruby aplicáveis, validações; preservar a linguagem visual do sofá aprovado.
- `bedroom`: bedroom, SUITE 01/02, cama, guarda-roupa e criado; compartilhados ficam em shared, não duplicados.
- `bathroom`: validadores de banheiro, V-Ray/renderes quando exclusivos do banheiro, sem mover runtime comum de SketchUp para cômodo.
- `service`: manter conjunto área de serviço/terraços; `balcony` é advisory no escopo atual, não promover brain independente.
- `closet` e `home_office` fazem reuse/advisory explícito, sem builder imaginário. `circulation` permanece validation-only.
- Migrar `interior/validators/` por owner (bed/nightstand/wardrobe → bedroom, sofa → living, checks transversais → validation) e preservar API pública de `interior` mediante facade quando necessária.

**P4c — camadas transversais:**
- `tools/sketchup/{shell,furnish,inspect,vray}/`: scripts de materialização, protocolo de processo, inspeção e rotas Ruby por resolvedor estável. A entrada MCP não muda.
- `tools/validation/`: gates globais e auditorias; regras locais ficam no cômodo.
- `tools/orchestration/`: pipelines de cômodos, variantes, promoção e loops; `tools/rendering/`: utilidades de imagem; `tools/knowledge/`: RAG/referências/PDF; `tools/oracle/`: consultas/juízes sem conceder aprovação visual.
- Conservar `tools/cli/` apenas quando houver entrypoints humanos concretos, mantendo aliases antigos `python -m tools.X` como fachadas.
- Não alterar as responsabilidades já corretas de `interior/`, `tools/mcp_server/`, `ops/` por arrumação estética.

**P4d — compatibilidade/gates da migração:**
- Para cada fatia: inventário FP-042 completo, mapa FP-043 com `status: done` **somente quando o destino verificável existe** e facade importa; links README/mapa, refs em YAML/JSON, testes, empacotamento e entradas externas.
- Provar import frio em ordens distintas, CLI antiga vs nova, comandos Ruby por path, start MCP, boundaries/ciclos, fixture hashes e comportamento idêntico antes/depois. Não deixar implementação duplicada escondida na facade.
- Decisões D-002…D-005 congelam **somente** seus arquivos. Registrar exceções nominadas; não mover para `legacy/` genérico nem excluir silenciosamente.
- Provar `python -m tools.navigation.p0_map --check`, `python -m tools.rooms.inventory_gate --strict` e `python -m tools.rooms.ownership_audit` em cada PR pertinente.

**Saída P4:** todo item de P4 do mapa concluído ou exceptionado por decisão rastreável; localização canônica real e verificável (não só doc); entrypoints antigos testados; nenhuma mudança funcional acidental; CI verde.

## 5. P5 — especialistas rastreáveis, sem execução arbitrária

**P5a — perfis e roteamento:** criar/adaptar `specialist.md`, `specialist.v1.json` e `knowledge/index.v1.json` em cada categoria relevante de `tools/rooms/<room>/`; perfil declara escopo, room IDs/aliases, sources/recipe IDs, tool allowlist, restrições, tipos de resultado, owner e estados. Kitchen primeiro; living, bedroom, bathroom, service depois; balcony, closet, home_office advisory/reuse e circulation validation-only. Resolver perfil pelo registry/manifest existentes, não criar um segundo dispatch dinâmico.

**P5b — catálogo único versionado:** definir schemas testáveis para vínculos `source → recipe → capability → símbolo Python/Ruby → fixture → teste → evidência` com IDs/versionamento; dimensão independente para (i) evidência de conhecimento, (ii) implementação, (iii) validação L1/L2, (iv) revisão visual. Incluir parâmetros/unidades/origem, precondições, invariantes, side effects, allowlist, compatibilidade da prova à versão do builder. Duplicatas, símbolo inexistente, source quebrada, evidência velha e ferramenta não autorizada reprovam o gate.

**P5c — fluxo fail-closed:** pedido → projeto/room → constraints do PDF/consensus → consulta recipes canônicas → seleção fundamentada → capacidade resolvida → plano estruturado com unidade/IDs/rollback → validador → executor **somente quando autorizado**. Capability ausente responde `BLOCKED_CAPABILITY_MISSING` com reason e próximo passo, não cria caixas genéricas/exec Ruby ad hoc. Plano consultivo `tools/sketchup/knowledge.py:cabinet_plan` conserva `execution_authorized=false` e API pública. Fonte maliciosa ou instrução em PDF/tutorial nunca altera allowlist ou direitos de execução.

**Testes P5:** todas as nove categorias de roteamento, ambiguidade/rejeição, source/recipe sem capacidade, Shaker advisory, tentativa de chamar ferramenta fora da allowlist, versões incompatíveis, inputs com medidas faltantes, consumo do catálogo após reload, ausência de execução real nos testes de planejamento. Inventários/link/docs gates verdes.

**Saída P5:** é possível descobrir por documentação o especialista, sua fonte, seu limite e a capacidade testada em até 3 links desde README. Não anunciar L2 de catálogo ainda sem P6.

## 6. P6 — gabinete paramétrico compartilhado REAL

**P6a — contrato/modelo L1:** implementar capacidade explícita em `tools/rooms/shared/cabinet/` (domínio/plano/parâmetros/validação) e adapter em `tools/rooms/kitchen/capabilities/`. Escopo aprovado:
- caixaria retangular: laterais, fundo, base, topo, prateleira opcional, frentes lisas separadas; geometria e convenção de montagem explícitas.
- entradas obrigatórias: largura/altura/profundidade, espessuras, folgas, peças, materiais por peça, orientação, posição+rotação e unidades com origem. Sem "medida padrão" inventada para o apartamento.
- checagem de não finito/negativo/inviável, colisão indevida, peças fora do envelope e referências de coordenação; materialização nunca executa se `validate` falhar.
- saída com schema/version, IDs de peças estáveis, material/pose/parte, plano de rollback e assinatura vinculando capacidade e parâmetros.
- componentes/definições compartilhadas só quando semanticamente equivalentes; `make_unique` para alteração local sem mudar instâncias alheias. Editabilidade real, não só bbox. Preservar o `cabinet_plan` consultivo separado.

**P6b — materializador SketchUp/Ruby L2:** adapter registrado e permitido constrói grupo/componente editável em SKP scratch, aplica materiais, tags e árvore sem tocar arquitetura, salva, fecha/reabre e usa inspeção + provas de dimensões/posição/topologia/IDs. Testar 0°, 90°, 30° não ortogonal, repetição/uniqueness, atualização local, reexecução controlada e ausência de objetos duplicados. Para madeira, testar orientation/UV no SketchUp se suportado; se não, estado `NOT_SUPPORTED` para veio (não declarar PASS).

**Micro-fixtures:** ao menos 3 dimensões válidas diferentes, incluindo caso reservado para avaliação pós-implementação; 1 geometria impossível, 1 entrada incompleta, 1 ferramenta não autorizada. Consenso/valores vêm de arquivos sintéticos **novos** ou projeto com origem documentada; não supor dimensões da cozinha. Provar que a cozinha só recebe a peça depois de passar âncora hidráulica, passagem e proteção arquitetônica.

**Não incluído no MVP:** ferragens/gavetas mecânicas, portas Shaker, recortes de bancada/cuba, certificação de fabricação, desenho executivo/corte. Isto deve permanecer como capacidade futura claramente não autorizada.

**Saída P6:** plano L1 testado **e** pelo menos 3 materializações reais L2 com SKP salvo/reaberto, inspeção, evidência versionada. Sem ambiente Windows: P6a pode ficar `DONE_L1`, P6b fica `BLOCKED_ENV`, nunca `L2_PASS`.

## 7. P7 — missão vertical: pedido inédito → SKP comprovado

**Cenário positivo:** usuário pede à cozinha um gabinete de frentes lisas com parâmetros fundamentados. Um único trace encadeia:
`request_id → project/room → consensus/requirements → source/recipe IDs → capability ID+version → parameters+provenance → plan validation → allowlist → SketchUp job PID → saved .skp → reopened inspection → validation/evidence`.

- Entrada concreta nova que não aparece literalmente nos testes de implementação; parâmetro faltante leva à pergunta/bloqueio apropriado antes de executar.
- Executar em cópia de trabalho, com idempotency key/identidade do job e rollback seguro; sem sobrescrever canônico, sem mutação cross-room/shell.
- Conferir L1 vs L2 dimensional e hierárquico, orientação de pose, clearance/circulação e ancoragem da cozinha. Emitir manifest com hashes, commit, versão de capacidade, versão SketchUp e resultado por gate.
- **Negativos obrigatórios:** recipe Shaker sem builder, comando fora da allowlist, geometria inviável, input sem unidade/origem, tentativa de alterar arquitetura e simulação de job interrompido. Rejeições deixam o input intacto e não marcam prova positiva.
- Não dar ao modelo autorização implícita para rodar script arbitrário. Julgar estrutura de ações/argumentos/efeitos, não a redação do LLM.

**Saída P7:** ao menos um novo gabinete de cozinha passa pelo percurso real e chega a SKP editável, salvo/reaberto/inspecionado; trace demonstra que é a capacidade catalogada, não placeholder renderizado.

## 8. P8 — auditoria final, handoff e cobertura completa

**P8a — navegação:** a partir de `README.md`, demonstrar em até 3 links: planner+pia da cozinha, builder shared+consumidores, Shaker sem capability, evidência L2 de uma capability, entrada MCP/executor/caminho SKP. Atualizar `docs/architecture/repository_map.md` e `migration_guide.md` conforme paths reais.

**P8b — inventário/dívida:** reconciliar `fp043_p0_map.v1.json`, `fp042_inventory.v1.json`, ownership, duplicatas de implementação e restrições externas. Todas as decisões D-001…D-006 precisam de uma linha final `RESOLVED` ou `BLOCKED_DECISION` com impacto restrito, sem selecionar a alternativa pelo usuário.

**P8c — matriz de testes final:**

| Matriz | Comando/ação | Gate |
|---|---|---|
| Inventory FP-042 | `python -m tools.rooms.inventory_gate --strict` | PASS |
| Scope FP-043 | `python -m tools.navigation.p0_map --check` | PASS |
| Boundaries | `python -m tools.rooms.ownership_audit` + ownership/P3 aplicáveis | PASS |
| Docs/links | `python -m tools.navigation.docs_check` (conferir CLI atual) | PASS |
| Python 3.11/3.12 | `python -m pytest tests/ -q -m "not planta74_scale"` | PASS |
| Planta real em processo próprio | `PT_TO_M=0.0259 python -m pytest tests/ -q -m planta74_scale` | PASS |
| Gates de fixtures | `python -m tools.run_deterministic_gates --fixture quadrado` e `--fixture planta_74` | PASS |
| Scale gate/report | `python -m tools.validation.scale_anchor_gate --consensus … --report …` + ``run_deterministic_gates --report`` | PASS ou blocker documentado por defeito canônico real; nunca ignore |
| MCP | `python -m tools.mcp_server.smoke` + `python -m tools.mcp_server.stdio_check` e testes com extra `[mcp]` | PASS |
| GitHub Actions | todos os checks obrigatórios no PR, sem skip indevido | PASS |
| Windows SketchUp 2026 | matrizes P3b/P6b/P7, vários cômodos, save/reopen/inspect, coexistência | PASS real + anexos |
| Integridade | hashes e comparação antes/depois de todos os canônicos afetados | INTACT ou promoção aprovada |
| Visual | comparação de imagens e decisão humana para mudanças de aparência | PENDING_VISUAL_REVIEW até revisão explícita |

**P8d — relatório final versionado:** criar `docs/reports/FP-043_final_validation.md` (ou caminho de relatórios aprovado pelo repo) contendo status **por subfase**, PR+merge SHA, testes executados, PIDs/SketchUp/versionamento, links de evidência, hashes/cotas, discrepâncias, regressões, decisões abertas, limitações e próxima ação. Organizar `artifacts/review/<project>/<cycle>/`: .skp de prova quando permitido, imagens top/iso, logs e relatório de inspeção, sidecars e manifests com commit/capability/params. `runs/` segue scratch, não fonte única da evidência.

**Definição de DONE global:** P3 sem defeito crítico residual escondido, P4 mapa executado/excepcionado de forma honesta, P5 fail-closed comprovado, P6 L2 aprovado, P7 E2E real, P8 CI+L2+relatório completos e mudanças visuais com veredito humano quando requeridas. Se faltar um requisito, entregar progresso verificável com status **PARTIAL/BLOCKED**, nunca `COMPLETED` global.

## 9. Repartição sugerida de PRs (ajustar ao HEAD/consumidores)

| Ordem | PR / fatia | Dependências | Testes/aceite próprios |
|---|---|---|---|
| 1 | `fp043-p3-gates-report` | nenhuma | repros de `railing_match`/`position_fidelity`, contraprova negativa, nenhuma fonte protegida alterada |
| 2 | `fp043-p3-synthetic-layout` | nenhuma | contrato polígono, regressões sintéticas novas |
| 3 | `fp043-p4-kitchen-shared` | P0 mapa | cozinha/shared, facades/imports/gates |
| 4 | `fp043-p4-living-bedroom` | 3 | sala/quartos e validações por owner |
| 5 | `fp043-p4-bathroom-service` | 3 | banheiros/SERVICE e advisory de outras rotas |
| 6 | `fp043-p4-sketchup-validation` | 3 | Ruby paths, process/tools/gates |
| 7 | `fp043-p4-render-orchestration-knowledge` | 6 | infra transversal; CLI e protocolo |
| 8 | `fp043-p5-specialist-registry` | 3–7 | profiles/index/allowlist/schema/negativos |
| 9 | `fp043-p6-cabinet-plan` | 8 | 3 positivos L1 + negativos/contratos |
| 10 | `fp043-p6-cabinet-sketchup` | 9 + P3b | micro-fixtures L2; save/reopen/edit/rotate |
| 11 | `fp043-p7-kitchen-vertical` | 10 | trace E2E + bloqueios reais |
| 12 | `fp043-p3-layout-l2` | P3a + P3b | antes/depois real; pendências de VISUAL_REVIEW isoladas |
| 13 | `fp043-p8-final-audit` | anteriores | inventário/gates/relatório/provas |

Esta lista é uma estratégia, **não** autorização para merges com CI vermelho.
Cada PR deve indicar explicitamente o que é L1, L2, VISUAL_REVIEW ou N/A,
impacto em fontes protegidas, mapa/inventário atualizado, comandos e rollback.
Se um item depender de decisão D-001…D-006, não abrir PR que silenciosamente
escolha por Felipe; seguir outra fatia independente.

## 10. Protocolo de handoff e retomada

Ao começar cada sessão:
1. Ler `CLAUDE.md` (e imports), FP-043 original, esta spec, decisões abertas, inventários/mapa, README L2 e PRs desde o último checkpoint.
2. Listar o estado **real** em `develop`, PRs abertos, commits e CI. Identificar primeira tarefa desbloqueada; não confiar cegamente neste documento.
3. Executar a fatia em branch isolada, reproduzir falha antes de corrigir, criar testes negativos e positivos, rodar gate local e CI, dar merge apenas com evidências suficientes.
4. Atualizar seção de progresso/relatório ou `.claude/plans/active_work.md` segundo o protocolo do repo; registrar exatamente próximo PR/arquivo/bloqueio/ação sem pedir que usuário repita contexto.
5. Seguir para a próxima fatia independente. Somente chamar o Felipe para revisão visual ou decisão que realmente lhe pertença. **Não perguntar autorização de merge técnico a cada fase.**

### Prompt de kickoff para o Claude

> Execute a [FP-043 — Spec de conclusão P3→P8](FP-043_remaining_execution_P3_P8.md).
> Confira `develop`, PRs e CI atuais. Preserve todos os merges #286–#296.
> Conclua todos os itens técnicos independentes em PRs pequenos com CI verde e merge
> sequencial para `develop`. Não peça permissão de rotina para cada etapa.
> Comece por P3a e P4a conforme dependências, documentando o que ainda requer
> SketchUp 2026 real. Faça L2 no Windows quando disponível. Não altere referência
> ou aparência aprovada, nem invente `VISUAL_REVIEW`. Entregue relatório final com
> links de PRs, commits, testes, SKPs/evidências e blockers honestos.
