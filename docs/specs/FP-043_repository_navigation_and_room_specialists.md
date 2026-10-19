# FP-043 — Organização navegável e especialistas por cômodo

**Estado:** SPEC PROPOSTA; implementação não iniciada por este documento.
**Data:** 2026-10-19. **Baseline observada:** develop `07959bfdd153031de13190e883583c7e8acb5c70` (PR #285).
**Solicitante:** Felipe. **Executor previsto:** Claude no Windows com SketchUp.

## 1. Problema e resultado esperado

Felipe não consegue localizar responsabilidades navegando pelas pastas. A FP-042
fechou ownership, mas manteve muitos entrypoints históricos e arquivos dispersos.
Classificação completa não é uma arquitetura fácil de descobrir.

No baseline há 1.912 arquivos versionados, 1.908 entradas do inventário (quatro
paths administrativos excluídos), 15 arquivos diretamente na raiz e 142 diretamente
em tools/. Esses números são diagnóstico, não metas artificiais de redução.

Esta fase deve permitir a um humano ou agente novo localizar o responsável por uma
mudança, entender o fluxo e chegar às provas sem conhecer a história do projeto.
Ao mesmo tempo, deve conectar conhecimento de aulas a capacidades reais, começando
por um especialista de cozinha com um gabinete compartilhado comprovado.

**Entregas:** organização física incremental + mapa de navegação + contratos dos
especialistas + catálogo rastreável de capacidades + um fluxo vertical de cozinha
executado no SketchUp. Novos READMEs sozinhos não concluem esta spec.

A publicação desta spec não executa migrações, não altera capacidades existentes e
não aprova aparência ou fabricação. A execução começa quando esta missão for
encaminhada ao executor; conferir o HEAD real antes de cada fase.

## 2. Fontes de verdade e situação técnica

Ler a constituição/instruções aplicáveis e:

- [FP-042 — modularização](FP-042_exhaustive_modularization.md).
- [FP-042 — auditoria automatizada](FP-042_final_validation.md).
- [Bateria real L2](../../artifacts/review/l2_fp042_20261019/README.md), incluindo
  resultados e bloqueios: evidências registradas, não aprovação L2 universal.
- [Manifesto dos cômodos](../../tools/rooms/manifest.v1.json).
- [Conhecimento por ambiente](../../references/sketchup/knowledge/environment_recipes.v1.json).
- [Conhecimento de marcenaria](../../references/sketchup/knowledge/video_recipes.v1.json).

A bateria L2 reporta 402 peças materializadas e defeitos corrigidos nos PRs
#281–#284. Permanecem colisões de layout, divergência do contrato do quadrado,
problemas de execução e técnicas consultivas sem materializador. Revalidar o estado
antes de corrigir: não repetir fixes já integrados nem declarar nova prova usando
somente evidências históricas.

O README raiz também contém afirmações desatualizadas: nega a existência de servidor
MCP, informa 85 suites e descreve o cockpit antigo em :8765 como ativo. P1 deve
confrontar essas instruções com código/execução e separar histórico de orientação
vigente; mover arquivos sem corrigir os pontos de entrada perpetua a confusão.

PDF/consensus e decisões aprovadas do projeto vencem receitas ou inferências.
Dimensões de tutoriais nunca viram cotas do apartamento por default.

## 3. Limites de escopo

Incluído: estabilização dos achados relevantes, organização da raiz/tools e dos
módulos, compatibilidade, navegação, roteamento do especialista, conhecimento,
execução controlada e gabinete paramétrico inicial com testes contínuos.

Fora da primeira entrega funcional: todos os cômodos com autonomia plena,
marcenaria pronta para fabricação, engenharia estrutural/MEP certificada,
materializador universal, treinamento de modelos e ingestão autônoma irrestrita de
vídeos. Ferragens, portas articuladas, gavetas completas e recortes de bancada
entram em incrementos posteriores com fontes e testes próprios.

Não trocar toda a estrutura por src/ nem renomear tudo numa única PR. Não criar
pacotes vazios para parecer modular. Não introduzir outro dashboard ou framework
multiagente como pré-requisito. Um mesmo modelo de IA pode assumir os perfis.

## 4. Decisões de organização

### 4.1 Raiz e documentação

A raiz deve conter pontos de entrada curtos, configuração e diretórios com papel
explícito. A lista final de arquivos permitidos deve ser versionada e validada.

| Caminho atual | Destino/decisão proposta | Condição |
|---|---|---|
| README.md | Manter na raiz, com entrada para o mapa | Explicar por onde começar e executar |
| CLAUDE.md | Manter como bootloader curto | Apontar para instruções/mapa sem duplicar políticas |
| CLAUDE_COGNITIVE_ARCHITECTURE.md | docs/architecture/agent_architecture.md | Conferir conteúdo atual, imports documentais e links |
| HANDOFF.md | docs/handoffs/current.md ou arquivo histórico datado | Separar estado vigente de histórico; não declarar atual por nome |
| KICKOFF.md | docs/handoffs/ | Nome pelo assunto/data após ler o conteúdo |
| HISTORICO_SOFA.json | references/sofas/history/ | Preservar conteúdo, proveniência e consumidores |
| planta_74.pdf | projects/planta_74/source/planta_74.pdf | Migração protegida e explícita; manter o original se houver bloqueio real |
| vray_pipeline_proof.png | artifacts/review/ em pasta de evidência identificada | Manter contexto e hash; não confundir com render canônico |
| pyproject.toml, uv.lock | Manter | Instalação, empacotamento e CI |
| docker-compose*.yml | Manter inicialmente | Evitar mudar resolução de caminhos junto com a navegação |
| Configurações de Git, CI e agentes | Manter onde a ferramenta exige | Toda exceção deve ter motivo verificável |

Não mover um arquivo só pelo nome: confirmar referências, finalidade e políticas.
Nomes de destino acima são decisões propostas; P0 resolve colisões de nomes e
registra o mapa exato antes de qualquer movimento.

### 4.2 Responsabilidade dos diretórios

| Diretório | Responsabilidade canônica |
|---|---|
| core/ | IDs, unidades, contratos fundamentais e políticas de domínio comuns |
| interior/ | Semântica e composição de cenas/intenção; adapters de render existentes, sem duplicar planners já em rooms |
| tools/rooms/<room>/ | Decisão/planning/validação específicos do cômodo e seu perfil de especialista |
| tools/rooms/shared/ | Geometria, materiais e builders reutilizáveis entre cômodos |
| tools/sketchup/ | Processo, jobs e materialização/inspeção no SketchUp; sem decisões de decoração |
| tools/mcp_server/ | Protocolo MCP e registro explícito das ferramentas |
| tools/orchestration/ | Sequenciamento dos pipelines entre cômodos/executores, sem propriedade de algoritmos de um cômodo |
| tools/validation/ | Gates transversais; regras exclusivas ficam no cômodo |
| tools/cli/ | Entrypoints humanos novos; fachadas públicas antigas preservadas durante a transição |
| tools/rendering/ | Utilidades comuns de imagem/pós-processamento; processo SketchUp continua no executor e intenção de render em interior |
| projects/<project>/ | Configuração e fontes identificadas do projeto; referências aos inputs/outputs canônicos |
| fixtures/ | Inputs canônicos e fixtures sintéticas; não são outputs |
| artifacts/<project>/ | Entregáveis canônicos aprovados conforme política existente |
| artifacts/review/ | Evidências identificadas por mudança, versão e cenário |
| references/ | Fontes, recipes e referências de design canônicas |
| assets/ | Recursos reutilizáveis de entrada, com origem/licença |
| textures/ | Texturas existentes; manter path inicialmente, documentar fronteira com assets |
| renders/ | Classificar conteúdo existente como canônico, evidência ou histórico; não criar mais um destino de output sem regra |
| runs/ | Scratch ignorado, nunca única evidência final |
| tests/ | Regressões organizadas por responsabilidade, sem perder descoberta ou fixtures |
| scripts/ e ops/ | Automação operacional e ambiente; migrar lógica de produto para seu owner |

Esses destinos não autorizam mover todos os arquivos automaticamente. P0 deve
classificar cada item de tools/, scripts/, ops/ e interior/ por consumidores e
responsabilidade. Fronteiras ambíguas exigem decisão registrada, não uma nova pasta
"misc", "utils" ou "legacy" contendo código ainda ativo sem dono.

### 4.3 Módulo de cômodo previsível

Aplicar a convenção primeiro em kitchen e depois aos demais, aproveitando os
módulos existentes. Não manter arquivos com a mesma responsabilidade em paralelo.

| Caminho relativo ao módulo | Conteúdo |
|---|---|
| README.md | Comece aqui: entradas, fluxo, dependências, capacidades, testes, provas e limites |
| specialist.md | Papel, decisões, fontes, ferramentas permitidas e condições de parada |
| specialist.v1.json | IDs do perfil, roteamento, recipe/capability IDs e estados; sem autorização implícita |
| planning/ | Planner e regras exclusivas do cômodo |
| validation/ | Validações exclusivas, inclusive hidráulica quando aplicável |
| capabilities/ | Adapters específicos de capacidades; builders genéricos ficam em shared |
| knowledge/index.v1.json | Referências por ID às fontes/recipes canônicas, sem copiá-las |

Evitar colisão arquivo/pacote ao transformar validation.py em validation/;
re-exportar os símbolos públicos e testar imports/CLI existentes. Não introduzir
subdiretório se não houver responsabilidade concreta para ele.

Os testes podem ser agrupados em tests/rooms/<room>/ e tests/rooms/shared/ quando
isso melhorar a descoberta; primeiro auditar conftest, caminhos relativos, markers
e comandos de CI. Não mover toda a suíte por estética.

## 5. Como os especialistas aplicam o conhecimento

Um módulo Python não é, sozinho, um especialista. O especialista é o agente usando
um perfil delimitado, contexto do projeto, fontes consultáveis, ferramentas
registradas e critérios de avaliação. Python/Ruby executam contratos verificáveis.

### 5.1 Fluxo obrigatório

1. Resolver projeto, room ID e perfil pelo registry existente.
2. Ler requisitos, cotas e restrições do projeto; registrar o que falta.
3. Recuperar recipes pertinentes, origem, alcance e limitações de evidência.
4. Escolher técnica e explicar a relação com o pedido; comparar alternativas quando
   houver uma escolha real, sem impor quantidade artificial de alternativas.
5. Resolver a capacidade executável, versão e evidências compatíveis com a tarefa.
6. Produzir plano estruturado: parâmetros fundamentados, entidades afetadas,
   precondições, invariantes, validação e rollback.
7. Validar o plano e executar apenas ferramentas da allowlist em cópia de trabalho.
8. Inspecionar medidas, hierarquia, materiais e limites; salvar, reabrir e conferir.
9. Emitir resultado, provas, limitações e necessidade de revisão visual.

Para técnica ausente, devolver BLOCKED_CAPABILITY_MISSING e a lacuna específica.
Não improvisar caixas nem gerar/rodar Ruby arbitrário para contornar o catálogo.
O registro declarativo não autoriza execução, e o plano consultivo do gabinete
existente não pode ser convertido silenciosamente em plano de operação.

Exemplo: pedido de porta Shaker seleciona a recipe correspondente. Sem builder e
fixture comprovados de perfil/rebaixo, continua bloqueado para essa técnica,
mesmo que já exista um gabinete de frentes lisas.

### 5.2 Estados e rastreabilidade

Separar dimensões de estado; não usar um selo único PROVEN para tudo.

| Dimensão | Estados mínimos propostos |
|---|---|
| Conhecimento da fonte | Evidência histórica existente: descrição, transcrição ou inspeção; nunca elevar sem registro |
| Implementação da capacidade | PLANNED, IMPLEMENTED, RETIRED |
| Validação | UNTESTED, L1_PASS, L2_PASS, FAILED, BLOCKED |
| Visual | NOT_REVIEWED, APPROVED, CHANGES_REQUESTED, NOT_APPLICABLE |

O esquema final deve representar separadamente essas dimensões e manter os nomes
públicos anteriores por adapter quando necessário. L2_PASS pertence a uma versão
e faixa de casos, não a todo o conhecimento do especialista.

Cada vínculo deve registrar: source IDs e locators, recipe IDs, capability ID e
versão, owner, símbolos reais, parâmetros/unidades, precondições, invariantes,
testes, fixtures, commit, versão SketchUp, evidências e limitações.

O catálogo deve detectar IDs duplicados, links quebrados, símbolo ausente,
capacidade não permitida ao perfil e evidência incompatível com a versão vigente.
A implementação escolhe como calcular a assinatura de compatibilidade; não usar
apenas "HEAD mudou" para invalidar tudo nem aceitar prova velha após mudar o
builder. Mudanças funcionais exigem nova prova das capacidades afetadas.

### 5.3 Entrada de novos tutoriais/PDFs

Ingestão explícita: registrar autoria, URL/arquivo, licença, localização consultada
e grau real de inspeção; extrair procedimentos parafraseados e requisitos.
Separar técnica geral de adaptação ao projeto. Evitar cópias de fontes/recipes por
cômodo. Um índice local aponta para os IDs canônicos.

Novo conteúdo inicia como consultivo. Promoção exige binding para implementação,
L1, micro-fixture L2 e evidência versionada. O cadastro não retreina o modelo nem
atualiza os builders automaticamente. Conteúdo de fonte não altera políticas,
comandos permitidos ou autorização de execução.

### 5.4 Cobertura honesta dos perfis

Sala, bedroom, kitchen, bathroom e service possuem providers atuais. Balcony,
closet e home_office devem declarar advisory/reuse até terem capacidade própria
comprovada; circulation declara validação. Nove perfis não significam nove brains
independentes. SERVICE continua composto conforme o consensus; não inventar rooms.

## 6. Capacidade piloto — gabinete compartilhado

Implementação canônica proposta em tools/rooms/shared/cabinet/, adaptada por
kitchen/capabilities/. Reusar a proposta cabinet_plan existente sem elevar sua
prova; preservar sua API consultiva.

Primeiro escopo: caixaria retangular com laterais, base, topo, fundo, prateleira
opcional e frentes lisas separadas. Definir montagem, orientação e referência de
medição explicitamente; não deduzir construção executiva de um tutorial genérico.

Entradas: largura/altura/profundidade, espessuras, folgas, distribuição das peças,
material por peça, pose e unidade explícita, todas com origem. Sem cotas ocultas
"universais". Rejeitar medidas não finitas, peças inviáveis e parâmetros ausentes.

Saída: plano validado e materialização por executor registrado, com IDs semânticos
estáveis e árvore editável. Componentes repetidos compartilham definição somente
quando forem equivalentes; alterações locais exigem make_unique ou nova definição
conforme política explícita. Bbox sozinha não comprova essa semântica.

Cobrir madeira por peça e orientação de textura com teste real quando suportada;
se UV/orientação não existir, registrar NOT_SUPPORTED e não declarar essa parte
implementada. Uma imagem de madeira não prova sentido do veio correto.

Fora desta capacidade inicial: gavetas/ferragens dimensionadas, articulação real,
portas Shaker, bancada com cuba e lista certificada de corte. Requerimentos do
fabricante e de fabricação entram em capacidades separadas.

## 7. Execução faseada e critérios de saída

| Fase | Entrega | Gate de saída |
|---|---|---|
| P0 — mapa | Inventário atual, mapa exato origem/destino/consumidores/risco, fronteiras, exceções e decisões | Todos os arquivos da raiz e tools/scripts/ops/interior têm destino ou retenção justificada; nenhuma mudança física ainda |
| P1 — navegação | README raiz + docs/architecture/repository_map.md + guia de migração + cozinha como referência | Exercícios de navegação abaixo passam; links válidos; docs não declaram capacidade inexistente |
| P2 — raiz | Movimentos seguros dos arquivos soltos aprovados pelo mapa | Allowlist de raiz, consumidores atualizados, hashes preservados e nenhuma cópia divergente |
| P3 — estabilização L2 | Corrigir riscos e colisões confirmados conforme seção 8 | Repros negativos, regressões e execução real dos caminhos afetados; bloqueios segregados |
| P4 — módulos | Agrupar código ativo por responsabilidade; cozinha/shared primeiro, depois demais cômodos e tooling | Não basta ownership: mapa implementado; fachadas compatíveis; zero novo acoplamento cruzado/ciclo de carregamento |
| P5 — especialistas | Perfis, índices, catálogo e roteamento consulta→plano→validação | IDs/símbolos/fontes íntegros, plano fail-closed, ausência de capacidade corretamente bloqueada |
| P6 — gabinete | Builder shared e adapter da cozinha materializados no SU | Micro-fixtures novas, edição/salvamento/reabertura e invariantes aprovados em casos diferentes |
| P7 — fluxo vertical | Pedido novo ao especialista de cozinha gera gabinete via fluxo registrado | Trace fonte→decisão→capacidade→tool→SKP→inspeção; limites respeitados e caso impossível recusado |
| P8 — entrega | Relatório, navegação final e backlog técnico fundamentado | CI verde, evidências acessíveis, nenhum FAIL oculto sob conclusão geral |

P1/P2 começam sem esperar por capacidades novas. P3 pode resolver bloqueios antes
de completar toda a reorganização; nenhum novo fluxo de escrita do piloto é
liberado sobre um caminho de execução inseguro. Separar PRs de movimentação,
correção e novas capacidades para conseguir revisar comportamento.

Cada PR termina com seu gate aplicável. Não executar P0–P8 como um commit gigante.
Não deixar uma fase declarada concluída porque o inventário recebeu um status.

## 8. Estabilização necessária antes do piloto

Reproduzir e conferir no HEAD atual os itens do README L2:

- Gate de escala baseado em âncora verificável; modelo errado não pode passar só
  por consistência interna. Escalas de quadrado/sintéticas e planta_74 separadas.
- Divergência do peitoril: identificar contrato canônico vigente e decisão original.
  Não mudar expected para fazer o teste passar; se a fonte não resolver, registrar
  a decisão de produto pendente e continuar tarefas independentes.
- Autorun global: impedir que instância concorrente execute job de outra sessão.
- Encerramento por nome ainda existente: remover dos caminhos utilizados.
- stdout do MCP reservado ao protocolo; logs em stderr/sink, teste com cliente estrito.
- Ciclo de vida do servidor/Job Object: testar comportamento documentado em Python
  e Claude Code/Node, sem matar sessão humana ou deixar arquivo sem salvar.
- Colisões reais de sala, SUITE 01, lavabo e banhos: corrigir na camada do planner
  quando violarem contratos existentes; medir o modelo real após a correção.
- Convenção de polígono das sintéticas: não alterar fixtures protegidas implicitamente;
  distinguir erro de input de erro de planner, criar repro novo e registrar decisão.
- Fechar cobertura de preload no job MCP e caminhos positivos de render/open.

Correção determinística com contrato estabelecido não precisa virar uma escolha
estética do Felipe. Mudança de aparência aprovada exige before/after e
VISUAL_REVIEW antes de promoção canônica. Arquitetura/fixtures congeladas continuam
sob as regras de autorização existentes.

## 9. Migração física, compatibilidade e proveniência

Para cada movimento, mapear imports Python, carregamentos Ruby, paths relativos,
CLI, MCP, prompts/skills, README, testes, build/package, automação e referências
externas documentadas. Dependências podem estar em strings e configs, não só AST.

Regras obrigatórias:

1. Uma implementação canônica por responsabilidade; facade antiga somente delega.
2. CLI pública anterior continua funcionando na janela de compatibilidade; publicar
   caminho moderno e critério de descontinuação, sem removê-la nesta primeira fase.
3. Não recriar outro monólito em shared; nada específico de kitchen em shared só
   para contornar o gate de dependências.
4. Atualizar inventário e owner tables no mesmo PR, sem marcar PENDING como completo.
5. Assets protegidos: registrar old_path/new_path, blob/SHA256 antes/depois, owner,
   consumidores e justificativa. Gate deve aceitar somente o rename autorizado,
   mantendo a lista completa; nunca regenerar o manifesto inteiro para apagar diffs.
6. Manter fixtures e artefatos canônicos nos paths atuais por padrão. O PDF da raiz
   é candidato explícito de migração de path, não autorização para mudar seus bytes.
   Resolver qualquer restrição aplicável antes do movimento, documentando a exceção.
7. Detectar `Path(...).parents[n]` e bootstrap Ruby que dependam da profundidade.
   Usar resolvedor estável existente ou introduzir um único contrato, sem cópias.
8. Imports frios em ordens distintas e smoke de CLI/MCP; instalação em ambiente
   limpo deve encontrar dados/recursos conforme o contrato de distribuição atual.
9. Rollback por PR/commit com mapa reverso; preservar históricos e arquivos locais
   de outras sessões. Nunca apagar artefatos para "limpar" a árvore.

As fachadas temporárias em tools/ são exceções nominadas e têm destino canônico.
Meta final desta fase: nenhum arquivo direto em tools/ sem responsabilidade e
status de implementação/facade/infra explícitos; código ativo disperso deve ser
movido conforme mapa, não simplesmente receber comentários.

## 10. Testes e aceitação

### 10.1 Navegação verificável

Registrar a rota de descoberta a partir do README, sem depender de busca ampla ou
memória do agente, para cinco tarefas:

- Encontrar o planner da cozinha e a regra que protege a pia.
- Encontrar o builder compartilhado de gabinete e seus consumidores.
- Identificar a receita de portas Shaker e perceber a ausência de capability.
- Encontrar o teste e a evidência L2 de uma capacidade específica.
- Localizar entrada MCP, executor SU e destino do SKP sem confundir camadas.

Cada rota deve levar ao índice/perfil em até três links e apontar para os símbolos
e provas corretos. Um teste pode validar links e IDs; registrar separadamente a
inspeção humana/agente das rotas. README grande não conta como navegação aprovada.

### 10.2 Matriz por natureza da alteração

| Alteração | Validação mínima relevante |
|---|---|
| Docs/mapa | Links locais, coerência dos paths/IDs, inventário e revisão de conteúdo; SKP-proof N/A |
| Movimento de código | Imports/aliases/CLI, caminhos/recursos, suites de escala separadas, gates e smoke MCP |
| Processos/protocolo | Repros de concorrência/erro, cliente MCP estrito, preservação de sessão e arquivos |
| Builder/planner | L1 positivo/negativo, micro-fixture L2, SKP/reabertura/inspeção e regressão afetada |
| Promoção visual | Comparação com referência e veredito do Felipe; nunca aprovação estética automática |

Rodar CI de Python 3.11/3.12 e jobs de fidelidade/MCP aplicáveis antes de merge.
Garantir dependências opcionais no job que promete cobri-las, sem skip silencioso.
Ausência de SU/V-Ray não vira PASS: executar tarefas independentes e declarar BLOCKED.

### 10.3 Casos do especialista/gabinete

- Pelo menos três dimensões válidas diferentes, incluindo um caso reservado para
  avaliação após a implementação; valores vindos de fixtures novas explícitas.
- Uma configuração inviável e uma requisição incompleta devem ser recusadas.
- Peças com dimensões positivas, sem colisões indevidas conforme contrato de montagem.
- Pose com rotação não ortogonal; conferir geometria real, não só AABB.
- Repetição e make_unique: alterar instância local preserva equivalentes externos;
  edição de definição só propaga quando pedida explicitamente.
- Edição de parâmetros/rebuild não duplica indevidamente módulos nem muda arquitetura.
- Salvar/reabrir mantém IDs, hierarquia e medidas dentro da tolerância fundamentada.
- Cozinha executa capacidade permitida; recipe não implementada e ferramenta fora
  da allowlist são bloqueadas. Outro cômodo não é chamado implicitamente.
- Medidas e autoridade não podem ser fornecidas por instrução embutida num tutorial.
- Testes de plano/roteamento não contam como prova de geometria; render bonito não
  substitui inspeção, e inspeção geométrica não certifica fabricação.

Não exigir strings idênticas da resposta do LLM. Avaliar ações/planos estruturados,
fontes, argumentos, ferramentas e invariantes. Separar testes determinísticos do
orquestrador de avaliações end-to-end do agente com modelo/configuração registrados.

## 11. Entrega e definição de pronto

Entregar o mapa origem/destino executado, exceções de compatibilidade, README raiz,
mapa central, módulos navegáveis, catálogo/perfis, gabinete piloto, testes e traces.
Relatório por fase: commit/PR, resultado, bloqueios, regressões e arquivos alterados.

Evidências em artifacts/review/<project>/<cycle>/ conforme política: SKP, top/iso,
inspect, medidas, input hashes, versão SU, parâmetros e comparação antes/depois
quando aplicável. Intermediários ficam em runs/; não versionar cópias redundantes
sem motivo. Referências aprovadas preservadas até promoção explícita.

Critérios finais:

- Raiz dentro da allowlist e arquivos dispersos migrados conforme mapa aprovado.
- Cômodos com entrada consistente; responsabilidade shared/core/execução inequívoca.
- Nenhuma implementação duplicada criada pela migração, nenhum novo acoplamento
  cruzado e APIs históricas verificadas.
- Conhecimento rastreável; estados consultivo, implementação, L2 e visual distintos.
- Um pedido novo de gabinete passa pelo especialista e produz artefato inspecionável.
- Técnicas não implementadas continuam bloqueadas, sem afirmação de fabricação.
- CI e gates verdes; nenhuma fase com FAIL ou NOT_RUN rotulada como concluída.

## 12. Encaminhamento ao Claude

Leia esta FP-043 e o README L2 indicado. Confira develop/PRs/CI e instruções do repo.
Comece pelo P0, registre o mapa exato e implemente P1/P2 em fatias verificáveis.
Continue pelas fases autorizadas da missão, corrigindo os bloqueios reproduzidos
antes de novas operações de escrita. Teste a cada incremento, não apenas no final.
Preserve as APIs e artefatos aprovados; não promova estados de prova por declaração.
Cada PR deve ter CI verde antes de merge. Falta de SketchUp bloqueia só L2 e tarefas
que dele dependem. Não substitua capacidades ausentes por mock no resultado final.
Esta criação de spec não realiza sua implementação; a execução é uma missão própria.
