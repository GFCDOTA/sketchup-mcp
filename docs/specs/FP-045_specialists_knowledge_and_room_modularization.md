# 📐 SPEC de Feature — FP-045: Especialistas executáveis, conhecimento verificável e fechamento da modularização
> Fluxo de Desenvolvimento Agêntico (SDD) · SketchUp MCP (Python, Ruby, Windows SketchUp, MCP stdio)

## 🏷️ BLOCO 1 — Metadata

```yaml
spec:
  feature: "FP-045 — Especialistas executáveis, conhecimento verificável e fechamento da modularização"
  escopo_versao: "Concluir pendências verificáveis das FP-041 a FP-044, promover técnicas consultivas a capacidades reproduzíveis e tornar auditável a modularização por cômodo, sem alterar canônicos sem aprovação."
  versao: "1.1.0"
  status: "RASCUNHO_VALIDADO_CONTRA_DEVELOP"
  classificacao:
    contexto_delimitado: "modelagem paramétrica e conhecimento especializado por cômodo"
    dominio: "SketchUp MCP / interior design / geometry orchestration"
    funcionalidade: "auditoria, conhecimento, capacidades, isolamento de módulos, provas L1/L2/L3"
  autor: "Auditoria assistida GPT-6; responsável pelas decisões de produto: Felipe"
  data_criacao: "2026-10-21"
  ultima_atualizacao: "2026-10-21"
  validacao: "2026-10-21 contra develop@2af60b0: 7 gates L1 e specialists.plan reais executados; correcoes em 3.2 (v1.1.0)"
  integracao_alvo: "develop, via PR e CI"
  baseline_develop_sha: "2af60b0274356292f2b7f6dc7d869b9858f35e2b"
  janela_auditada: "2026-09-21 a 2026-10-21"
  especificacao_predecessora:
    - "docs/specs/FP-041_video_knowledge_consultation.md"
    - "docs/specs/FP-041_room_knowledge_expansion.md"
    - "docs/specs/FP-042_final_validation.md"
    - "docs/specs/FP-043_repository_navigation_and_room_specialists.md"
    - "docs/specs/FP-044_root_and_tools_consolidation.md"
  estado_inicial: "FP-043=PARTIAL_BLOCKED; FP-044=PARTIAL"
```

**Nota de escopo.** É uma SPEC de fechamento com incrementos técnicos explícitos, NÃO autorização para migrar ou redesenhar o apartamento inteiro. Cada fase tem diff mínimo, provas e retorno seguro. A implementação desta SPEC não começa com mudança de geometria. Texto e tabelas são contratos de entrega; caminhos de código citados correspondem à árvore auditada, salvo itens marcados **PROPOSTO**.

**Dentro do escopo:** reconciliação de inventários e relatórios; fronteiras reais entre módulos; consumidor externo `harness-app`; regras de proveniência de aulas; seleção de receitas por especialista; implementação progressiva de capacidades ausentes, começando por marcenaria; provas reais no SketchUp; fechamento condicionado de decisões e revisão visual.

**Fora do escopo nesta versão:** reescrever os brains já funcionais; alterar PDF/consensus/fixtures protegidas; mudar canônicos `*.skp`; aceitar revisão estética por IA; extrair um novo PDF→consensus; criar nove ambientes físicos artificiais; declarar que vídeos foram assistidos quando houve apenas descrição pública; implementar todos os tutoriais de uma só vez; instituir Kafka/SQS/mensageria inexistente; editar o repositório `GFCDOTA/harness-app` sem PR independente e permissão apropriada; apagar arquivos legados retidos por decisão.

## 📐 BLOCO 2 — Especificação Técnica

### 2.1 Resumo da Feature

**Objetivo único:** fechar a distância verificável entre *conhecimento catalogado*, *especialista que recomenda* e *capacidade que produz um SKP editável seguro*, preservando arquitetura modular e resultados aprovados. Esta SPEC não duplica a FP-043 ou a FP-044.

**Handoff auditado, com referência de origem:**

| Área | Resultado já obtido (NÃO refazer) | Evidência / limite |
|---|---|---|
| FP-041 | 8 recipes de vídeos, 11 recipes de ambientes e 9 categorias de roteamento | `references/sketchup/knowledge/{video_recipes,environment_recipes}.v1.json`; descrição de vídeo NÃO prova inspeção |
| FP-042 | Ownership e modularização inicial, verificação de referências e binários, testes de fronteira | `docs/specs/FP-042_final_validation.md`: 1.808 entradas naquele baseline, 707 binários e 1.060 referências; números históricos, não totais atuais |
| FP-043/P0–P4 | Mapa P0, documentação navegável, fontes protegidas, módulos de cômodos, shared, execução e tooling | `docs/reports/FP-043_final_validation.md` |
| FP-043/P5 | 9 perfis, índices por IDs, `tools.rooms.specialists.plan` fail-closed e catálogo | 16 capabilities no `capability_catalog.v1.json`; 3 L2_PASS, 12 L1_PASS, 1 UNTESTED; 16 NOT_REVIEWED no eixo visual |
| FP-043/P6 | Gabinete paramétrico `tools/rooms/shared/cabinet/` e materialização real | 13 micro-fixtures L2, geometria e reabertura; sem gavetas completas, ferragens, Shaker, recortes ou veio |
| FP-043/P7 | Fluxo vertical `tools.rooms.kitchen.capabilities.cabinet_flow.run_request` | 42 checks no teste documentado; piloto cozinha, não generalização automática |
| FP-043/P8 | `su_build_shell` → `su_furnish` → `su_inspect` reais; 402/402 caixas, erro máx. 0,05 mm; 0 móvel em parede/giro | SketchUp 26.0.429; L3 humano para reparos pendente |
| FP-044/F0–F7 | Guard da raiz, baseline, documentação, mover ativos de sofá/schema e retirar fachadas | 123 `tools/*.py` da F0 → **14 agora**: 109 removidas, 8 públicas, 4 bloqueadas por harness e 2 por decisão; F4/F5 pendentes |
| Estado CI | Workflow `ci` #234 em `develop` para SHA `2af60b0` concluído `success` (4 jobs: pytest 3.11, pytest 3.12, deterministic fidelity gates, mcp server smoke+stdio) | https://github.com/GFCDOTA/sketchup-mcp/actions/runs/39415240475 ; CI Linux não representa L2/L3 |
| Estado GitHub | Nenhuma issue aberta; único PR aberto é o #339 (esta própria SPEC, draft). Seus 3 checks de teste falharam na v1.0.0 por R-11: o arquivo não estava em `docs/specs/fp042_inventory.v1.json` (`UNREGISTERED_FILES`). Corrigido na v1.1.0 | Leitura remota pontual; reconsultar antes de implementar |

**Reconciliação importante:** o `FP-044_final_validation.md` foi produzido quando existiam 15 fachadas e D-012 ainda aberta. O PR #337 moveu `_grid_sheet` para `tools/rooms/shared/contact_sheet.py` e removeu `tools/sofa_class_matrix.py`. A D-012 agora está **resolvida**; o relatório histórico NÃO deve ser falsificado. Criar complemento datado/novo snapshot para os 14 atuais.

**Objetivo de aprendizagem:** “um especialista conhece uma técnica” só atinge `L1` após contrato/cálculo testado; `L2` requer SketchUp real e inspeção; `L3` requer veredito humano quando a aparência mudar. Uma recipe nunca concede permissão de execução.

**Objetivo de arquitetura:** cada comportamento ativo tem exatamente um dono (cômodo, `shared`, `core` ou infra). Fachada de compatibilidade não é implementação adicional, mas deve ter consumidor explícito, contrato e data/condição de remoção. Não inventar novo brain para um cômodo que hoje apenas reutiliza outro.

**Fases ordenadas:**

| Fase | Entrega | Pré-requisito / gate de saída |
|---|---|---|
| F0 | Snapshot, baseline reproduzível, relatório de gaps e decisões | arquivos por hash; CI atual; manifesto sem lacunas silenciosas |
| F1 | Governança documental e grafo de owners/consumidores | D-012 sincronizada; decisões pendentes visíveis; guards verdes |
| F2 | Fronteira do `harness-app` (D-011) | PR independente no harness, checks; remover 4 fachadas SÓ após prova do consumidor |
| F3 | Plano e repro de D-007, isolado por cômodo | suíte sintética reproduz bug; comparação SUITE 02; requer L3 se aparência muda |
| F4 | Ingestão, evidência e avaliação de conhecimento | recipes com origem verificável e score/rótulo honestos; negativos |
| F5 | Contrato comum de especialistas/capabilities e roteador de execução | `plan` puro; gate fail-closed; sem elevar execução automaticamente |
| F6 | Piloto de marcenaria avançada por capacidade atômica | L1 → L2 → inspeção → L3 se visual; receita e código ligados |
| F7 | Aplicação progressiva nos demais cômodos existentes | 1 vertical slice por ambiente, sem regressão cross-room |
| F8 | Consolidação residual de raiz/infra conforme decisões | D-002–D-005, D-008/D-009: somente com decisão registrada |
| F9 | Prova integrada Windows real + visual + governança de hashes | matriz de evidências por cômodo, commit e SketchUp version |
| F10 | Relatório de fechamento e handoff executável | TAAC e checklist integral; exceções abertas impedem COMPLETE |

**Fases independentes podem ter PRs separados**, mas um passo que muda aparência não ultrapassa L3 silenciosamente. Desbloquear D-011 exige coordenar outro repositório, não quebrar contratos locais.

### 2.2 Arquitetura de Solução

**Topologia atual a preservar:**

```text
PDF + consensus + fixtures protegidas
  └─ core.domain / core.scale / core.schemas / core.project_sources
      └─ tools.rooms.registry / specialists.plan / capability_catalog
          ├─ tools.rooms.{living,bedroom,kitchen,bathroom,service}
          ├─ tools.rooms.{balcony,closet,home_office,circulation} (advisory/reuse/validation)
          ├─ tools.rooms.shared (geometria, móveis, material, gabinete)
          └─ tools.{validation,orchestration,rendering,knowledge,oracle}
               └─ tools.sketchup.{jobs,process,shell,furnish,inspect,vray}
                    └─ tools.mcp_server.server (18 tools já existentes)
                         └─ SketchUp real / artefato .skp de trabalho / inspeção
```

**Regra de camada:** conhecimento é read-only; especialista escolhe `binding` e valida capacidades; builder produz *plano*; job explícito materializa cópia; gates julgam aspectos determinísticos; humano julga aparência. `shared` possui comportamento comprovadamente usado por mais de um cômodo ou primitiva neutra. Não permitir dependências `bedroom → living`, `kitchen → bathroom` etc. `orchestration` pode depender dos cômodos; o contrário não.

#### 2.2.1 Pipeline obrigatório (ordem observável e testável)

1. **Receber pedido:** `request_id`, `project_id`, texto/`room`, técnica, entradas com `value/unit/origin`; gerar SHA-256 canônico.
2. **Resolver projeto/ambiente:** `core.domain.room_registry` + `tools.rooms.registry`; traduzir `service ↔ laundry` apenas como alias de conhecimento, não criar room ID físico.
3. **Carregar fontes:** PDF/consensus e recipe com `source_id`, URL/localizador, modo de acesso, evidência, hash e versão.
4. **Aplicar política de proveniência:** separar documentação oficial lida, transcrição inspecionada, descrição pública e adaptação própria. Sem fonte suficiente: `BLOCKED_KNOWLEDGE_EVIDENCE` (PROPOSTO).
5. **Rotear especialista:** `tools.rooms.specialists.plan`; checar âmbito, `tool_allowlist` e ausência de alteração arquitetônica.
6. **Resolver técnica:** `binding` → `recipe_ids` → `capability_id` → versão e símbolos reais; na ausência: `BLOCKED_CAPABILITY_MISSING`.
7. **Validar entrada:** medidas finitas/positivas e com valor/unidade/origem; constraints de PDF/consensus + regras de segurança por cômodo; evidência não stale.
8. **Planejar antes de executar:** API pura retorna plano tipado, envelopes geométricos e gates necessários, ou falha fechada sem abrir SketchUp.
9. **Autorizar job explícito somente no executor:** nunca derivar permissão do texto da receita ou do `execution_authorized=false` declarativo do perfil.
10. **Materializar em cópia:** job SketchUp sob PID próprio, com idempotency key e destinação em `runs/` (ou diretório de prova), nunca em canônico.
11. **Reabrir e inspecionar:** conferir componentes editáveis, hierarquia, bbox, IDs, tags, materiais, operações geométricas, arquitetura e portas.
12. **Executar L1/L2:** gates por cômodo + regressão de cômodos-controle e hashes de fontes.
13. **Revisão visual condicional:** diferença de aparência gera `PENDING_VISION` e pacote antes/depois para o Felipe, não PASS automático.
14. **Promover capability:** somente quando símbolos, recipe, testes e evidências atuais satisfazem nível declarado; caso contrário preservar estado inferior.
15. **Persistir trilha:** JSON de execução com input/source/capability/commit/SketchUp version/hashes/testes/decisão, mais relatório humano legível.

#### 2.2.2 Comportamento obrigatório — regras numeradas

| Regra | Condição | Efeito testável |
|---|---|---|
| R-01 | Pedido toca parede, porta, janela, abertura | Retornar `BLOCKED_ARCHITECTURE_CHANGE` antes de qualquer job |
| R-02 | `room` desconhecido, ambíguo ou contraditório | `BLOCKED_ROOM_UNRESOLVED` / `BLOCKED_ROOM_MISMATCH`, sem mutação |
| R-03 | Fonte com `evidence` ∈ {`PUBLIC_DESCRIPTION_ONLY`, `TRANSCRIPT_AND_DESCRIPTION_ONLY`} (vocabulário real, ver 2.6.1) | Só consultiva; não alegar visualização, transcrição completa ou “aprendido integralmente” |
| R-04 | Fonte declarada indisponível/sem locator/hash quando exigível | Bloquear promoção; registrar lacuna, sem inventar timestamp |
| R-05 | `binding` sem `capability_id` implementado | `BLOCKED_CAPABILITY_MISSING`, próximo passo e fonte |
| R-06 | Capability `IMPLEMENTED` mas prova L2 ausente | Não declarar `L2_PASS` nem capability demonstrada no SketchUp |
| R-07 | Digest de símbolo diverge de evidência | `BLOCKED_EVIDENCE_STALE`; revalidar antes de usar a prova |
| R-08 | Ferramenta fora da allowlist do perfil | `BLOCKED_TOOL_NOT_ALLOWED`; zero jobs |
| R-09 | Entrada sem `value`, `unit` ou `origin` | `BLOCKED_INPUT_INCOMPLETE`; não inferir medida do tutorial |
| R-10 | Módulo A importa implementação ativa de outro cômodo B | Falha `CROSS_ROOM_DEPENDENCY`; extrair para `shared` somente se neutro |
| R-11 | Novo arquivo/mudança estrutural | Declarar owner, mapa, consumidores e hashes, mantendo `inventory_gate --strict` |
| R-12 | Fachada tem consumidor externo confirmado | Não remover antes de migrar consumidor e provar ambas versões |
| R-13 | Builder altera caixa do cômodo de controle | Exigir comparação geométrica e `VISUAL_REVIEW` se aparência mudar |
| R-14 | Build executado | Criar cópia sob `runs/`; não sobrescrever `artifacts/planta_74/` aprovado |
| R-15 | Retrigger com mesma chave e mesmos hashes | Reusar resultado validado/idempotente ou recusar inconsistência; nunca duplicar grupo |
| R-16 | SketchUp iniciado por job | Fechar exclusivamente PIDs próprios; jamais `taskkill /IM` ou matar janela humana |
| R-17 | L1/CI verde, sem SketchUp real | Estado no máximo `L1_PASS` ou `PENDING_SKETCHUP` |
| R-18 | L2 geométrico verde, com aparência alterada | Estado `PENDING_VISION`; resultado visual `NOT_REVIEWED` |
| R-19 | Receita descreve Shaker/gaveta/recorte não implementado | Recusar com gap específico; não substituir por caixa genérica marcada como sucesso |
| R-20 | Precisa de ferragem/folga de fabricante sem fonte | `BLOCKED_INPUT_INCOMPLETE` ou `NOT_SUPPORTED`, não fabricar norma |
| R-21 | `PT_TO_M` alterna para planta_74 | Executar processo isolado com `PT_TO_M=0.0259`; não misturar escalas no mesmo Python |
| R-22 | Erro, timeout ou violação de gate | Manifesto `FAILED/BLOCKED` e cópia preservada para diagnóstico; canônicos idênticos |
| R-23 | Aprovação estética humana inexistente | Proibido marcar `VISUAL_REVIEW=PASS` ou `COMPLETE` |
| R-24 | F4/F5 da FP-044 dependem D-009/D-008 | Permanecem `BLOCKED_DECISION` até registro do Felipe |
| R-25 | F2 depende do `harness-app` | Mudança fica fora do repo e bloqueia somente as 4 fachadas D-011 |
| R-26 | D-007 resolvida na sintética, mas SUITE 02 muda | Não aplicar correção global; exige teste/snapshot e veredito visual da suíte |
| R-27 | Revisão de relatório factual após #337/#338 | Preservar registro histórico e anexar snapshot novo, sem reescrever evidência do passado |
| R-28 | Todo PR com mudança de comportamento | Regra → teste → CA → evidência → rollback citados no PR, sem concluir fase por etiqueta |

**Tabela de decisão — promoção de capacidade**

| Implementação | L1 | L2 real | L3 se visual mudou | Estado publicável |
|---|---|---|---|---|
| ausente | qualquer | qualquer | qualquer | `BLOCKED_CAPABILITY_MISSING` |
| existe | falha | qualquer | qualquer | `FAILED` |
| existe | PASS | não executado | qualquer | `L1_PASS / PENDING_SKETCHUP` |
| existe | PASS | PASS | não requerido (sem mudança visual) | `L2_PASS`, visual `NOT_REVIEWED` |
| existe | PASS | PASS | pendente | `L2_PASS + PENDING_VISION` (não aceite estético) |
| existe | PASS | PASS | aprovado pelo Felipe | `L2_PASS + VISUAL_APPROVED` para versão/hash exatos |
| existe | PASS | falha | qualquer | `FAILED_L2`; não publicar êxito |

**Tabela de decisão — localização de código**

| Critério | Dono |
|---|---|
| Regra exclusiva de sala/quarto/cozinha/banheiro/serviço | `tools/rooms/<room>/` |
| Primitiva geométrica/material sem regra de cômodo e ≥2 consumidores reais | `tools/rooms/shared/` |
| Schema, IDs, escala ou origem de verdade global | `core/` |
| Agregação multi-cômodos e pipeline | `tools/orchestration/` |
| Processo, Ruby, inspeção, V-Ray | `tools/sketchup/` ou `tools/rendering/` |
| Gates globais/CI | `tools/validation/` |
| Fonte, retrieval, recipes, memória | `tools/knowledge/` e `references/sketchup/knowledge/` |
| Compatibilidade com app externa comprovada | Fachada mínima documentada em `tools/PUBLIC_API.md`, não nova implementação |

**Matriz de responsabilidade — fonte × derivado**

| Dado | Fonte autoritativa | Derivado permitido |
|---|---|---|
| Contornos, paredes, vãos e hidráulica | PDF + consensus/fixture humana | footprint e envelope; nunca novas paredes |
| Dimensões do pedido | `inputs.value/unit/origin` | conversão explícita de unidade |
| Técnica | Recipe com ID/proveniência | seleção de capability se implementada |
| Capacidade executável | catálogo + código + L1/L2 | plano e job dentro da allowlist |
| Posição de móveis | planner + geometria + gates | caixas e SKP em cópia |
| Sucesso estético | Felipe via `VISUAL_REVIEW` | registro versionado da decisão; nunca IA |
| Veracidade do teste | runner/log/artefato com SHA-256 | relatório resumido ligado à evidência |

**Contrato transversal FP-052 — alvo específico antes de executar:** o especialista não pode deduzir um produto final apenas da recipe ou do estilo do cômodo. Deve consultar o manifesto `reference_target.v1` (ponteiros para `artifacts/reference_lab/`, PDF/consensus, decisão visual, anatomia/aceites por peça). Ele mantém a responsabilidade de escolher **capabilities**, mas não pode anunciar `FURNITURE_COMPLETE` sem target de instância no estado aprovado e relatório `TARGET_MATCH`. Uma aprovação do golden de cozinha não representa aprovação de cada peça; tutorial só descreve técnica revisada no segmento correspondente. O gate de target ainda é read-only no primeiro PR; a integração à execução é FP-052/T4, sem alteração retroativa de L2 válido.

### 2.3 Componentes Impactados

| Componente real | Tipo | Detalhe |
|---|---|---|
| `tools/rooms/specialists.py` | EVOLUIR | entrada/saída estáveis; provar links e bloqueios; sem execução implícita |
| `tools/rooms/capability_catalog.py` + `.v1.json` | EVOLUIR | integridade, stale digest, prova L1/L2, ligação fonte/recipe |
| `tools/rooms/*/specialist.v1.json` e `knowledge/index.v1.json` | EVOLUIR | nove perfis, limites e matriz de maturidade |
| `references/sketchup/knowledge/*.v1.json` | EVOLUIR | 8 + 11 recipes existentes; proveniência sem promoção falsa |
| `tools/sketchup/knowledge.py` | PRESERVAR/ESTENDER | consulta read-only e advisory `cabinet-plan` |
| `tools/rooms/shared/cabinet/{model,assembly,plan,validation,sketchup}.py` | EVOLUIR POR FATIA | tipos/planejamento/materialização paramétrica |
| `tools/rooms/shared/cabinet/ruby/*.rb` | EVOLUIR POR FATIA | hierarquia de componentes editáveis e reabertura |
| `tools/rooms/kitchen/capabilities/{cabinet,cabinet_flow}.py` | ESTENDER | piloto vertical real, não executor genérico imaginário |
| `tools/rooms/{living,bedroom,bathroom,service}/` | AMPLIAR PROGRESSIVAMENTE | uma capability faltante por PR; preservar brains |
| `tools/rooms/{balcony,closet,home_office,circulation}/` | GOVERNAR | papel advisory/reuse/validation, sem exigir brain artificial |
| `tools/rooms/shared/contact_sheet.py` | PRESERVAR | D-012 já resolvida no PR #337 |
| `tools/rooms/ownership_audit.py`, `inventory_gate.py` | REFORÇAR | dependências reais, owners, import frio e aliases |
| `tools/navigation/{p0_map,docs_check}.py` | REFORÇAR | relatório navegável, raízes e destinos reais |
| `tools/validation/fp044_baseline.py` | PRESERVAR | diferença de caixas por cômodo e hashes canônicos |
| `tools/sketchup/{jobs,process,runner_safety}.py` | PRESERVAR | PID próprio, Job Object, cópia de trabalho |
| `tools/mcp_server/server.py` | EXTENSÃO CONDICIONAL | 18 ferramentas atuais; novas tools só em PR/contrato separado |
| `tools/PUBLIC_API.md` + 14 arquivos `tools/*.py` | GOVERNAR | 8 públicos, 4 D-011, 2 D-003/D-004 |
| `docs/specs/FP-043_open_decisions.md` | ATUALIZAR FATO NOVO | D-012 resolvida; D-007 continua; D-008/D-009 pendentes |
| `docs/reports/FP-043_final_validation.md`, `FP-044_final_validation.md` | COMPLEMENTAR | preservar snapshots históricos, adicionar relatório FP-045 atual |
| `GFCDOTA/harness-app` (`SourceVerifier` / catálogo Java) | EXTERNO / CONDICIONAL | PR coordenado para 4 caminhos D-011; não tocar nesta SPEC |

### 2.4 Contratos de API

**Não há API REST nova obrigatória.** As interfaces existentes são Python, JSON, CLI, MCP stdio e job Ruby.

| Interface | Entrada | Saída / erro | Observação |
|---|---|---|---|
| `tools.rooms.specialists.plan(request)` | `{text, room?, technique?, tool?, inputs?, touches?}` | `PLAN_READY_NOT_EXECUTED` ou `BLOCKED_*` | pura; nunca executa |
| `tools.rooms.capability_catalog.verify()` | catálogo/profiles/código local | `PASS` ou erros tipados | gate local |
| `tools.sketchup.knowledge` CLI | `list --q`; `cabinet-plan --case` | JSON advisory / erro de validação | sem SKP |
| `tools.rooms.kitchen.capabilities.cabinet_flow.run_request` | `request, out_dir, base_skp, consensus_path` | trace, hashes, `state`, `pids` | piloto que já existe |
| `tools.mcp_server.server` | MCP `initialize`, `tools/list`, `tools/call` | 18 tools, respostas estruturadas | não inventar HTTP |
| `su_status/su_build_shell/su_furnish/su_inspect` | inputs existentes no servidor | estado/job/inspeção | validar em L2 após qualquer alteração |
| `su_apply_edits` | SKP, ops, caminho de cópia | SKP editado ou bloqueio | preservar original |

**Endpoint GET/POST:** `N/A`. Não criar `/api/specialists` sem ADR e consumidor. Para futura exposição MCP de `specialists.plan`: contrato versionado e apenas consulta, isolado de um comando explícito de execução; sem habilitar mutações por route textual.

**Taxonomia — estados que JÁ existem no código** (`tools/rooms/specialists.py`, `capability_catalog.py`, `tools/sketchup/knowledge.py`, verificado em `2af60b0`): `PLAN_READY_NOT_EXECUTED`, `BLOCKED_ARCHITECTURE_CHANGE`, `BLOCKED_ROOM_UNRESOLVED`, `BLOCKED_ROOM_MISMATCH`, `BLOCKED_TECHNIQUE_UNRESOLVED`, `BLOCKED_CAPABILITY_MISSING`, `BLOCKED_CAPABILITY_NOT_IN_PROFILE`, `BLOCKED_TOOL_NOT_ALLOWED`, `BLOCKED_INPUT_INCOMPLETE`, `BLOCKED_EVIDENCE_STALE`, `CROSS_ROOM_DEPENDENCY` (ownership), `EVIDENCE_STALE` (catálogo), `PENDING_SKETCHUP` (L2) e `PENDING_HUMAN` (L3) em `knowledge.py`, `NOT_SUPPORTED` (veio).

**Taxonomia PROPOSTA (não existe; mapear antes de introduzir no schema):** `BLOCKED_KNOWLEDGE_EVIDENCE`, `FAILED_L2`, `BLOCKED_EXTERNAL_CONSUMER`. **`PENDING_VISION` (R-18, tabela de promoção, CA-18) é sinônimo proposto do `PENDING_HUMAN` já existente: usar `PENDING_HUMAN` e não criar estado novo.**

#### 2.4.1 Pré-requisitos de infra

| Item | Necessidade |
|---|---|
| Python 3.11 / 3.12 | CI existente em ambientes separados |
| SketchUp Windows 26.0.429 | L2 de referência histórica; registrar versão real usada, sem fixar version forever |
| MCP stdio | `tools.mcp_server.stdio_check`; isolamento de stdout |
| `PT_TO_M=0.0259` | processo isolado para `planta_74` |
| Permissões e PIDs | escrita só em cópia; fechar somente processos próprios |
| V-Ray | condicional para capacidade visual que exija render |
| Qdrant/Ollama | opcionais e claramente `SKIPPED/UNAVAILABLE`, jamais prova de RAG |
| GitHub CI | 4 checks: pytest 3.11/3.12, fidelity gates, MCP smoke+stdio |
| `harness-app` | PR e validação próprios para D-011, sem dependência de deploy no restante |
| Feature flag | sem nova flag global obrigatória; capacidade é gated por catálogo + allowlist + prova; `INSPECTOR=1` existente é opcional |
| Backup/sync | snapshot SHA-256 e backup antes de cada edição estrutural; sincronização para Downloads é operação local do executor Windows e deve reportar falha se indisponível |

### 2.5 Eventos e Mensageria

**Aplicabilidade:** Kafka, Avro, SQS, DLQ e ACK de broker são **N/A** neste repositório para esta feature. Não inserir mensageria apenas para preencher template. O análogo real é o *trace* de jobs e evidências em arquivos; não confundir emissão de JSON com tópico.

#### 2.5.1 Evento de entrada

**Contrato proposto `specialist_request.v1`**, transportado por chamada Python/CLI (não tópico Kafka). Os campos `text`, `room`, `technique`, `tool`, `inputs`, `touches` são os que `specialists.plan` lê hoje; `request_id`, `inputs`, `materials` e `grain?` são os de `cabinet_flow.run_request`. **`project_id` e `execution_requested` NÃO são campos do pedido atual** (`base_skp`, `consensus_path`, `out_dir` e `project` são kwargs de `run_request`). Campos desconhecidos são ignorados e não ampliam direitos.

```json
{
  "schema_version": "specialist_request.v1",
  "request_id": "fp045-kitchen-cabinet-001",
  "project_id": "planta_74",
  "text": "gabinete de cozinha com frentes lisas",
  "room": "kitchen",
  "technique": "bind.kitchen.cabinet",
  "inputs": {
    "dimensions.width":  {"value": 480, "unit": "mm", "origin": "user_request"},
    "dimensions.depth":  {"value": 545, "unit": "mm", "origin": "user_request"},
    "dimensions.height": {"value": 780, "unit": "mm", "origin": "user_request"},
    "OMITIDO": "demais 15 chaves exigidas pela capability: panels.{side,top_bottom,back,front}, gaps.{front_clearance,front_reveal}, fronts.count, shelf.count, materials.{carcass,back,front}, pose.{x,y,z,rotation_deg}"
  },
  "touches": [],
  "execution_requested": false
}
```

**Validado contra o código (2026-10-21):** a v1.0.0 desta SPEC usava `technique: "cabinet-assemblies"` e `inputs.width/height/depth`; `specialists.plan` devolve `BLOCKED_TECHNIQUE_UNRESOLVED` para isso (`technique` só casa com `binding.id` ou um `recipe_id` do binding — `_select_binding`). Com `technique: "bind.kitchen.cabinet"` e o conjunto completo de `inputs` do pedido real `artifacts/review/fp043/p7_kitchen_cabinet/request.json` o estado é `PLAN_READY_NOT_EXECUTED`; com o texto e sem inputs, `BLOCKED_INPUT_INCOMPLETE`. Valores são sintéticos de estudo, não ordem de fabricação. `project_id`/`execution_requested` são adições PROPOSTAS: o adapter normaliza para o schema real da capability `kitchen.cabinet.plain-fronts` (parâmetros `dimensions.*`).

#### 2.5.2 Evento de saída

**Envelope proposto `specialist_result.v1`** (declarativo, compatível conceitualmente com `plan`/trace atuais):

```json
{
  "schema_version": "specialist_result.v1",
  "request_id": "fp045-kitchen-cabinet-001",
  "project_id": "planta_74",
  "room": "kitchen",
  "state": "PLAN_READY_NOT_EXECUTED",
  "execution_authorized": false,
  "capability": {
    "id": "kitchen.cabinet.plain-fronts",
    "version": "1.0.0",
    "implementation": "IMPLEMENTED",
    "validation": "L2_PASS",
    "visual": "NOT_REVIEWED"
  },
  "recipe_ids": ["room.kitchen.cabinet-assemblies"],
  "input_sha256": "to_be_computed_at_runtime",
  "code_commit": "2af60b0274356292f2b7f6dc7d869b9858f35e2b",
  "steps": [],
  "evidence": [],
  "output_skp": null,
  "visual_review": "NOT_APPLICABLE_PLAN_ONLY",
  "reason": null
}
```

Valores `to_be_computed_at_runtime` não são digests reais. Resultado é **exemplo de contrato proposto**, não execução registrada.

#### 2.5.3 Fluxo de retry

1. Falha antes do job: retorno `BLOCKED_*` sem retry automático, resolver insumos/capability.
2. Timeout/job transiente: preservar manifesto de tentativa e cópia; novo retry **explícito**, com mesmo request/idempotency key e limite configurado no executor existente.
3. Resultado já validado com hashes iguais: reuso idempotente; jamais segunda instância de `Cabinet_<request_id>`.
4. Mudança em código, source, consensus ou base: nova prova / nova chave; não reaproveitar `L2_PASS` stale.

#### 2.5.4 Mensagens SQS e DLQ

`N/A`. Falhas documentadas em `runs/<job>/manifest.json`/relatório JSONL quando aplicável; **não** criar DLQ fictícia. Adoção futura exige ADR, schema e testes específicos.

#### 2.5.5 ACK manual / zero perda

`N/A` no transporte atual. Equivalente local de durabilidade: resultado e hashes persistidos após sucesso; falha de persistência não é `PASS`, e promoção de canônico é operação separada, proibida sem revisão apropriada.

### 2.6 Modelo de Dados

**Existentes:** `core.domain.room_registry`; `core.schemas.specialist_profile.v1.schema.json`; `tools/rooms/manifest.v1.json`; `tools/rooms/capability_catalog.v1.json`; `tools/rooms/*/knowledge/index.v1.json`; `references/sketchup/knowledge/*_recipes.v1.json`; `cabinet_assembly_plan.v1` e trace de `cabinet_flow`.

**DTOs propostos, versionados somente quando implementação justificar:**

| DTO | Campos mínimos | Invariante |
|---|---|---|
| `KnowledgeEvidenceV1` | source_id, URL/locator, access_kind, retrieved_at?, sha256?, claims, review_state | nunca ampliar `PUBLIC_DESCRIPTION_ONLY` para inspecionado |
| `SpecialistRequestV1` | request_id, project_id, room, text, technique?, inputs, touches | medidas com value/unit/origin |
| `SpecialistPlanV1` | state, profile, binding, recipe_ids, capability(version), steps, missing | `execution_authorized=false` no plano |
| `CapabilityProofV1` | capability_id, symbol_digests, fixture_hashes, L1/L2/L3, sketchup_version?, commit | prova expira se digest mudar |
| `JobEvidenceV1` | job_id, idempotency_key, input/source/base SHA, output SKP SHA, own_pids, gates, state | jamais creditar janela não pertencente |
| `RoomRegressionV1` | room_id, before/after boxes hash, wall/door/circulation findings, visual_required | zero alterações de controle sem rastreio |

#### 2.6.1 Vocabulário real de proveniência e lacunas medidas (develop@2af60b0)

| Catálogo | Campo de evidência (fonte) | Valores existentes | Observação |
|---|---|---|---|
| `video_recipes.v1.json` (3 fontes, 8 recipes) | `sources[].evidence` | `TRANSCRIPT_AND_VISUAL_WALKTHROUGH` (2), `TRANSCRIPT_AND_DESCRIPTION_ONLY` (1) | estado da recipe em `proof_state` |
| `environment_recipes.v1.json` (10 fontes, 11 recipes) | `sources[].evidence` | `OFFICIAL_DOCUMENTATION_READ` (7), `PUBLIC_DESCRIPTION_ONLY` (3: `yt-laundry-basic`, `yt-pergola`, `yt-sliding-wardrobe`) | estado da recipe em `knowledge_state`; as 11 estão `KNOWLEDGE_ONLY_UNTESTED_IN_SKETCHUP` |

Lacunas para a F4: (a) o campo de estado da recipe tem nomes diferentes nos dois catálogos (`proof_state` × `knowledge_state`); (b) nenhuma fonte tem `sha256`/`retrieved_at`, então R-04 hoje só consegue exigir `locator`; (c) `PUBLIC_DESCRIPTION_ONLY` existe como dado e em `tests/test_sketchup_room_knowledge.py`, mas não como estado de bloqueio no `plan`. Nada disso é falha atual: são os alvos reais da F4.

**Bindings sem capability (alvos reais de F6/F7):** 7 de 15 — `bind.kitchen.{shaker,drawer,countertop,sink-cutout}`, `bind.balcony.pergola`, `bind.closet.sliding`, `bind.home_office.desk`. `plan` já devolve `BLOCKED_CAPABILITY_MISSING` com o `gap` textual (verificado para gaveta e Shaker).

**Compatibilidade:** novos schemas devem usar `core/schemas/` e manter readers atuais; migration tests antes de mudar `.v1` existente. Campos ausentes não podem dar `PASS` por default.

### 2.7 Requisitos Não Funcionais

| ID | Requisito / métrica | Critério |
|---|---|---|
| RNF-01 | Determinismo | mesmas entradas+versões produzem mesma assinatura lógica e hash normalizado, salvo campos de tempo/PID |
| RNF-02 | Integridade | SHA-256 de canônicos, fixtures e fontes antes/depois; divergência não autorizada = FAIL |
| RNF-03 | Disponibilidade da interface | CLI/MCP retornam erro tipado, sem stacktrace em stdout MCP e sem travar stdin |
| RNF-04 | Resiliência de processo | nenhum `taskkill /IM SketchUp.exe`; PID próprio; janela humana preservada |
| RNF-05 | Observabilidade | logs estruturados sem dados sensíveis; `request_id`/room/capability/version/recipe/state/reason/elapsed_ms/job_id |
| RNF-06 | Métricas propostas | `specialist_plan_total{room,state}`, `capability_proof_total{room,level,state}`, `sketchup_job_total{operation,state}`, `room_regression_total{room,result}`; implementar apenas em sink existente ou ADR de métricas |
| RNF-07 | Segurança do agente | nenhuma recipe/markdown concede execução, modifica política ou executa Ruby arbitrário |
| RNF-08 | Performance | coletar baseline p50/p95 antes de fixar SLO; regressão relativa de tempo/custo deve ser reportada, não ocultada |
| RNF-09 | Portabilidade | L1 em Linux CI; L2 Windows local; `SKIPPED` e `PENDING` não se tornam sucesso |
| RNF-10 | Revisibilidade | cada mudança liga commit, PR, CA, teste, before/after, hash e decisão visual |
| RNF-11 | Retenção | snapshots históricos imutáveis; relatórios atuais datados, vinculados a commit |
| RNF-12 | Modularidade | ciclo/import cross-room e fachada sem owner reprovam no gate |

### 2.8 Estratégia de Testes

#### 2.8.1 Unitários obrigatórios

| Arquivo/classe | Cenários mínimos |
|---|---|
| `tests/test_fp043_specialists.py` | route explícito/ambíguo, input incompleto, arquitetura, allowlist, capability ausente, evidência stale |
| `tests/test_fp043_capability_catalog.py` | IDs duplicados, source/recipe quebrado, símbolo inexistente, digest stale, L2 sem prova |
| `tests/test_sketchup_video_knowledge.py` e `test_sketchup_room_knowledge.py` | descrição pública permanece descrição; locator, claims, versão e prevenção de transcrição inventada |
| `tests/test_fp042_ownership_audit.py` | import absoluto/relativo, re-export/fachada, ciclo e `bedroom→living` negativo |
| `tests/test_fp044_tools_facades.py` | exatamente 14 atuais; 8 estáveis, 4 externos, 2 decisões; nunca remover sem consumidor migrado |
| `tests/test_fp044_baseline.py` | mesma geometria por cômodo e mesmo canônico quando alteração é estrutural |
| `tests/test_fp043_room_collisions.py` + `tests/test_synthetic_polygon_convention.py` | reproduzir D-007, `xfail(strict)` honesto, teste SUITE 02 de controle |
| `tests/test_fp043_no_global_taskkill.py` | nenhum kill por nome no caminho real, inclusive runners/fachadas |
| **PROPOSTOS** `tests/test_fp045_knowledge_provenance.py` | negativos de acesso, fontes falsas, nível de prova e SHA |
| **PROPOSTOS** `tests/test_fp045_specialist_vertical.py` | receita→binding→capability→planner, bloqueio sem nova mutação |
| **PROPOSTOS** `tests/test_fp045_module_graph.py` | dono único, consumidor real, sem ciclo/alias órfão |

#### 2.8.2 Integração/E2E obrigatórios

**L1 (sem SketchUp):** dois processos de escala diferentes; `inventory_gate --strict`, `ownership_audit`, `capability_catalog`, `p0_map --check`, `docs_check`, `asset_provenance`, `reference_provenance`, deterministic gates dos dois fixtures, suíte pytest 3.11/3.12, smoke e stdio MCP.

**L2 (Windows real):** micro-fixtures de cada capability alterada com 0°/90°/30° quando relevante; abrir, gerar cópia, salvar, fechar PID próprio, reabrir, inspecionar objetos, comparar plan→bbox/peças/tags/materiais; rodar build completo da planta_74 e medir controles. A cozinha tem precedente P6b 13/13 e P7 42 checks: novos testes devem somar cobertura, nunca substituir registro antigo por novo PASS implícito. Evidência da sessão inclui versão e PIDs.

**L3 (humano):** pacote antes/depois top/iso/vistas de peça, medições, impactos em SUITE 02/sala/banhos e decisão explícita, versionada por hash. Sem veredito = `PENDING_VISION`.

**WireMock/Testcontainers:** `N/A`, não há serviço HTTP/broker requerido. Adicionar somente se futura dependência exigir.

#### 2.8.3 Critérios de aceite (TAAC)

| CA | Given | When | Then |
|---|---|---|---|
| CA-01 | `develop` no SHA de baseline | gerar snapshot F0 | 2.128 blobs rastreados em `2af60b0` = 2.124 registrados em `fp042_inventory.v1.json` + 4 `CONTROL_PATHS` do gate; contagem recalculada no HEAD corrente; `inventory_gate --strict` PASS; nenhum path sem owner |
| CA-02 | 9 perfis e 19 recipes | rodar gate de referências | IDs, fontes e ligações consistentes; nenhuma origem inventada |
| CA-03 | 16 capacidades atuais | computar matriz | 3 L2, 12 L1, 1 UNTESTED, 16 NOT_REVIEWED neste baseline; sem promoção automática |
| CA-04 | pedido a cômodo errado | route | retorna erro tipado sem SKP |
| CA-05 | tutorial só por descrição pública | ingerir | `PUBLIC_DESCRIPTION_ONLY` preservado |
| CA-06 | recipe sem capability | planejar | `BLOCKED_CAPABILITY_MISSING` e gap acionável |
| CA-07 | capability com código alterado | validar digest | `BLOCKED_EVIDENCE_STALE` |
| CA-08 | ferramenta fora allowlist | executar plano | bloqueia antes do processo SketchUp |
| CA-09 | medida sem origem | validar | falha fechada, sem tolerância inferida |
| CA-10 | alteração `bedroom` importa `living` | rodar ownership | `CROSS_ROOM_DEPENDENCY` |
| CA-11 | quatro caminhos D-011 usados no harness | tentar removê-los antes do PR externo | bloqueio; API estável intacta |
| CA-12 | PR externo do harness integrado e testado | retirar quatro fachadas | todos os checks do harness e do MCP verdes; 14→10 se nenhuma outra condição mudar |
| CA-13 | tentativa de corrigir D-007 | comparar controle SUITE 02 | mudança geométrica dispara `VISUAL_REVIEW` e não promove canônico |
| CA-14 | job repetido com mesma chave | executar novamente | grupo não duplica, saída coerente com hash |
| CA-15 | janela humana aberta/não salva | executar L2 | janela humana permanece; apenas PIDs próprios fecham |
| CA-16 | job falha no meio | consultar manifestos | falha registrada e canônicos preservados |
| CA-17 | L1 passa e L2 não executou | publicar estado | fica `PENDING_SKETCHUP` |
| CA-18 | L2 passa e aparência mudou | publicar resultado | fica `PENDING_VISION` até Felipe decidir |
| **CA-19** | todas as fases elegíveis concluídas | executar suíte E2E completa Windows + CI | 4 checks verdes, provas L1/L2 rastreáveis, hashes canônicos íntegros, nenhum FAIL mascarado; relatório com PR/commit/versão; caso contrário `PARTIAL/BLOCKED` |
| CA-20 | D-008 e D-009 ainda não decididas | executar F8 | não apagar `.impeccable` nem mover `ops/estudio-front` |
| CA-21 | quarto e cozinha usam primitiva compartilhada | comparar owners | primitiva neutra em `shared` e nenhuma cópia divergente |
| CA-22 | receita de Shaker/gaveta sem ferragem/código | pedir criação | bloqueio específico, sem caixa “equivalente” enganosa |
| CA-23 | PR altera uma capability | gerar pacote de entrega | recipe/source→símbolo→fixture→L1/L2→visual documentados |
| CA-24 | README/relatório antigo mostra 15 fachadas | atualizar navegação | suplemento informa 14 atuais e PR #337, sem reescrever baseline F7 |

**CA-19 é o juiz de entrega, não um comentário:** checkout e SHA definidos; matriz de testes publicada; links a CI, L2 real e decisões; comando exit 0 para gates; fechamento somente se itens obrigatórios alcançam o nível requerido.

### 2.9 Estratégia de Lançamento

**Rollout phaseado, 1 PR por capacidade ou decisão:**

- **R0 — docs/snapshot:** incorporar SPEC e baseline; sem runtime/SKP.
- **R1 — guards e conhecimento:** ampliar validação sem executar novas operações; `BLOCKED_*` permanece contrato.
- **R2 — vertical slice de gabinete:** apenas nova micro-fixture isolada → L1 → Windows L2 → inspeção e comparação.
- **R3 — outros cômodos:** uma capability por ambiente com guardas/controles, reutilizando `shared` quando aplicável.
- **R4 — consumidores externos/limpeza:** remove quatro fachadas D-011 após PR do harness; decisões D-008/D-009 separadas.
- **R5 — fechamento:** relatório, checklist e visual revisado; nunca promover canônico por CI Linux apenas.

**Rollback:** cada PR de comportamento deve ser reversível por `git revert` na `develop`, sem mutar canônicos. Resultados experimentais vão para `runs/`, sem promoção. Em mudança de caminhos, usar `git mv`/proteção de blobs; no rollback restaurar referências e verificar SHA. Mudança do harness requer rollback coordenado, primeiro restaurando o contrato de consumo. Snapshot de backup antes de alterações estruturais; cópia para Downloads somente quando executor Windows puder realizá-la e confirmar digest.

**Política Git:** PRs pequenos direcionados a `develop`; branch sempre criada a partir da `develop` atual; merges após 4 checks do CI. Não enviar alterações diretamente para `main`. Alteração de aparência não será autoaprovada.

### 2.10 ADRs Vinculados

- `docs/adr/0001-semantic-geometry-contract.md` — contrato semântico de geometria e políticas de modelagem.
- `docs/specs/FP-041_video_knowledge_consultation.md` — separação consulta/execução.
- `docs/specs/FP-041_room_knowledge_expansion.md` — nove categorias e proveniência.
- `docs/specs/FP-042_exhaustive_modularization.md` + `FP-042_final_validation.md` — ownership/provas.
- `docs/specs/FP-043_repository_navigation_and_room_specialists.md` — P0–P8 e Hard Rules.
- `docs/specs/FP-043_open_decisions.md` — D-001 a D-012.
- `docs/specs/FP-044_root_and_tools_consolidation.md` — F0–F7, guards, API pública.
- **ADR-PROPOSTO FP-045/01:** taxonomia de prova e promoção de conhecimento/capabilities.
- **ADR-PROPOSTO FP-045/02:** contrato entre `sketchup-mcp` e `harness-app` para descontinuação de fachadas.
- **ADR-PROPOSTO FP-045/03:** API opt-in para execução genérica de especialista, somente se houver caso real e gate.

## 🔄 BLOCO 3 — Governança

### 3.1 Dúvidas resolvidas e decisões pendentes

**Resolvidas/verificadas:**

| ID | Decisão / fato |
|---|---|
| G-001 | A documentação consultiva não autoriza execução; confirmação no código `specialists.plan` |
| G-002 | Nove perfis ≠ nove brains independentes; `service` implementa lavanderia/terraços conforme consensus |
| G-003 | D-012 já resolvida no #337; `shared/contact_sheet.py` é o dono |
| G-004 | A árvore da `develop` no snapshot possui 14 `tools/*.py`; F7 histórico registrava 15 |
| G-005 | 16 capabilities: 3 L2, 12 L1, 1 UNTESTED e nenhuma revisão visual catalogada |
| G-006 | 8 recipes de vídeo + 11 recipes de ambientes; não declarar 19 tutoriais vistos |
| G-007 | P7 gabinete no SketchUp prova piloto cozinha; não prova marcenaria avançada geral |
| G-008 | Kafka/SQS/Avro/ACK de broker são `N/A`; traces locais são o contrato atual |
| G-009 | CI do último head observado concluiu com sucesso; sem alegar execução L2 nesta auditoria |

**Pendências explícitas — não inventar aprovação:**

| ID | Dono da decisão | Estado e consequência |
|---|---|---|
| D-001 | Felipe | referência protegida de `quadrado`; opções A/B/C já documentadas |
| D-002 | Felipe | Dockerfile/dashboard antigo, decidir destino |
| D-003 | Felipe | `furnish_plan` legado, decidir vigência |
| D-004 | Felipe | `trace_view`, decidir owner da CLI |
| D-005 | Felipe | `set_clipboard_image.ps1`, decidir retenção |
| D-007 | técnico + Felipe se muda visual | guarda-roupa sintético ~4,5 cm na parede; correção afeta SUITE 02 |
| D-008 | Felipe | apagar/manter `.impeccable/`; não executar F5 sem decisão |
| D-009 | Felipe | mover ou arquivar `ops/estudio-front`; não executar F4 sem decisão |
| D-010 | decisão vigente | manter oito fachadas públicas até migração externa futura |
| D-011 | técnico + PR `harness-app` | quatro consumidores externos a repontar |
| L3-001 | Felipe | revisão visual da sala, suítes, lavabo e banho 02 após correções FP-043 |
| K-001 | técnico | promoção de novas capacidades de gaveta/Shaker/ferragens/recortes depende de micro-fixtures e fontes adequadas |

**Governança de conteúdo obrigatória:** manifesto com caminho, owner, tamanho, git blob SHA e SHA-256 para arquivos protegidos; backup antes de edição estrutural; verificação antes/depois; cópia sincronizada em Downloads no ambiente Windows quando acessível; arquivos de prova append-only com commit/versão; texto histórico nunca reescrito para fabricar status atual. Não anexar segredos ou dados de máquina em logs.

### 3.2 Histórico de Versões

| Versão | Data | Autor | Descrição |
|---|---|---|---|
| 1.0.0 | 2026-10-21 | GPT-6 (auditoria) | Handoff consolidado FP-041–044; baseline real `develop@2af60b0`; faseamento F0–F10; R-01..R-28 e CA-01..CA-24 |
| 1.1.0 | 2026-10-21 | Claude (validação contra o código) | Executados `inventory_gate --strict`, `ownership_audit`, `capability_catalog`, `p0_map --check`, `docs_check`, `asset_provenance`, `reference_provenance` e `specialists.plan` reais. Correções: (1) a própria SPEC violava R-11 (fora do inventário FP-042 → 3 checks do #339 vermelhos) — registrada; (2) payload de exemplo 2.5.1 retornava `BLOCKED_TECHNIQUE_UNRESOLVED` — corrigido; (3) estados existentes separados dos propostos, `PENDING_VISION` → `PENDING_HUMAN`; (4) vocabulário real de evidência e 7 bindings sem capability (2.6.1); (5) CA-01 com a conta 2.124 + 4; (6) estado GitHub (#339) e CI (#234); (7) nome exato do ADR 0001. Prova: os 13 comandos de reprodução de 3.3 saem com exit 0 em `develop@2af60b0` (pytest 2.288 passed + 111 `planta74_scale`; L2/L3 não executados) |

### 3.3 Handoff para agentes implementadores

Antes do primeiro PR de código:

1. `git fetch origin` e comparar `origin/develop` com `2af60b0`; se divergir, produzir novo snapshot (não assumir que este documento é o estado atual).
2. Ler `CLAUDE.md`, `docs/architecture/repository_map.md`, `docs/specs/FP-043_open_decisions.md` e relatórios FP-043/044.
3. Recontar árvore, fachadas, recipes, capabilities, PRs e checks; produzir inventário de `path→owner→consumidores→hash→migrar/manter`.
4. Executar gates já existentes, em processos de escala separados; registrar preexistentes sem relativizar falhas novas.
5. Escolher **uma** fase e **uma** lacuna, com teste que falha antes, regra R-XX e CA-XX.
6. Implementar no dono real, não na fachada; registrar symbol digest e evidência; não improvisar L2 nem mudança arquitetônica.
7. Se Windows SU inacessível, fechar apenas L1 e deixar `PENDING_SKETCHUP`; jamais simular CI como prova real.
8. Abrir PR pequeno contra `develop`, associar R/CA, matriz e rollback, esperar os quatro checks.
9. Fazer merge apenas após checks verdes e nenhuma decisão visual obrigatória pendente para o escopo; atualizar inventário/relatório.
10. Repetir para próxima fatia, mantendo decisões do Felipe bloqueadas sem “resolver” por conta própria.

**Comandos mínimos de reprodução:**

```bash
python -m tools.rooms.inventory_gate --strict
python -m tools.rooms.ownership_audit
python -m tools.rooms.capability_catalog
python -m tools.navigation.p0_map --check
python -m tools.navigation.docs_check
python -m tools.rooms.asset_provenance
python -m tools.rooms.reference_provenance
python -m tools.validation.run_deterministic_gates --fixture quadrado
python -m tools.validation.run_deterministic_gates --fixture planta_74
python -m tools.mcp_server.smoke
python -m tools.mcp_server.stdio_check
python -m pytest tests/ -q -m "not planta74_scale"
PT_TO_M=0.0259 python -m pytest tests/ -q -m planta74_scale
```

## ✅ Checklist de Completude (estado da SPEC ≠ estado da implementação)

**Checklist de especificação:**

- [x] Metadata, escopo e fora de escopo explícitos
- [x] Baseline git, links e evidências com limites conhecidos
- [x] Arquitetura e pipeline numerado
- [x] Regras R-01..R-28 testáveis
- [x] Tabelas de decisão e matriz de responsabilidades
- [x] Componentes reais, interfaces e pré-requisitos
- [x] Eventos/payloads distinguidos de contratos propostos; mensageria N/A
- [x] Modelo de dados e requisitos não funcionais
- [x] Unitários, E2E, L1/L2/L3, TAAC e CA-19
- [x] Rollout, rollback, ADRs e governança de conteúdo
- [x] Handoff independente de sessão para Claude/implementadores
- [ ] Aprovação das decisões de produto pelo Felipe

**Checklist de implementação — NÃO marcar antes das provas:**

- [ ] F0 snapshot recalculado na `develop` corrente e manifestos íntegros
- [ ] F1 relatórios atuais reconciliados, D-012 e 14 fachadas refletidas
- [ ] F2 D-011 encerrada **após** validação no harness (sem quebrar API)
- [ ] F3 D-007 resolvida com teste negativo + controle SUITE 02 + visual aplicável
- [ ] F4 proveniência de aulas com negativos e rastreabilidade real
- [ ] F5 fluxo de especialista robusto sem ampliar permissão textual
- [ ] F6 pelo menos uma nova técnica avançada completamente L1/L2 (L3 quando aplicável)
- [ ] F7 vertical slices por cômodo selecionado com evidência (não contar categoria consultiva como executável)
- [ ] F8 F4/F5 antigas e arquivos retidos resolvidos conforme decisões, sem apagar unilateralmente
- [ ] F9 L2 Windows/SketchUp, checks CI, hashes e vereditos humanos necessários
- [ ] F10 relatório final, CA-19 executado, zero FAIL mascarado
- [ ] Status `COMPLETE` somente quando todos os itens obrigatórios e decisões bloqueantes estiverem satisfeitos

**Estado formal no momento de criação:** `RASCUNHO` / **IMPLEMENTAÇÃO NÃO INICIADA**. Esta SPEC registra fatos e trabalho proposto; não representa consentimento para alteração de canônicos ou aprovação visual.
