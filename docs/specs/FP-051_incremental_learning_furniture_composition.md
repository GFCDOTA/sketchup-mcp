# 📐 SPEC de Feature — FP-051: Aprendizado Incremental, Composição de Móveis e Mobiliamento Progressivo
> Fluxo de Desenvolvimento Agêntico (SDD) · GFCDOTA/sketchup-mcp · Python + Ruby + SketchUp Windows

## 🏷️ BLOCO 1 — Metadata

```yaml
spec:
  feature: "FP-051 — Aprender capacidades pequenas, compor móveis e mobiliar cômodos"
  escopo_versao: "Comprovar em um fluxo ponta a ponta como uma técnica rastreável vira capacidade executável, é reutilizada em um móvel e passa pelos gates de posicionamento na cozinha real."
  versao: "1.1.0"
  status: RASCUNHO_VALIDADO_CONTRA_DEVELOP
  classificacao:
    contexto_delimitado: "Aprendizado técnico verificável e mobiliamento"
    dominio: "SketchUp MCP / Marcenaria paramétrica / Especialistas por cômodo"
    funcionalidade: "Gap → Recipe → Capability → Assembly → Placement → SKP → Review"
  data: "2026-10-21"
  baseline_auditada: "develop@f41673520e1ec58efa6d6611a189c64678811588 (merge do #354); na validação v1.1.0 o develop era 13b1372 (só o #356, docs)"
  validacao: "2026-10-21: afirmações sobre o código verificadas por tools/navigation/fp051_baseline.py (spec_claims, docs/reports/fp051/fp051_baseline.json); 4 correções em 3.5"
  integracao: "PRs pequenos contra develop; sem alterações automáticas em arquivos canônicos"
  specs_relacionadas:
    - "FP-045 — especialistas, conhecimento e modularização (existente)"
    - "FP-046 — porta Shaker (capability L2 no catálogo atual)"
    - "FP-047 — contrato de regressão visual/geométrica (existente)"
    - "FP-048 — transformações/capabilities compartilhadas (PR #346 draft)"
    - "FP-049 — guarda-roupa componível (PR #347 draft)"
    - "FP-050 — posicionamento de gabinete na parede (PR #355 draft)"
  artefato_final_alvo: "1 gabinete completo, editável, adequadamente posicionado em CÓPIA de planta_74, com provas L1/L2 e decisão L3"
```

**Estado observado em 21/10/2026 (não confundir plano com entrega):** `tools/rooms/capability_catalog.v1.json` registra `shared.cabinet.parametric`, `kitchen.cabinet.shaker-door` e `shared.cabinet.front.shaker` como implementadas com L2_PASS; a dimensão visual permanece `NOT_REVIEWED`. Bindings de gaveta, tampo separado e recorte de pia ainda não têm `capability_id`. O `tools.rooms.specialists.plan` já roteia receitas e devolve bloqueios; `tools.rooms.kitchen.capabilities.cabinet_flow.run_request` já salva e reinspeciona a cópia do modelo. Essas bases **devem ser reutilizadas**, nunca substituídas por um novo framework de agentes.

### 1.1 Problema

O projeto possui conhecimento de tutoriais, especialistas consultivos e builders, mas não existe um ciclo de produto único que obrigue o agente a: (i) identificar precisamente uma capacidade faltante; (ii) aprender/implementar apenas aquela operação; (iii) provar o resultado com variações e SketchUp real; (iv) compor um móvel utilizável; (v) escolher e validar sua posição no ambiente real; (vi) registrar a entrega sem confundir execução geométrica com qualidade arquitetônica.

**Falha a eliminar:** `build OK` não significa `móvel corretamente colocado`. Um gabinete no corredor não pode ser aprovado só porque coube e não colidiu.

### 1.2 Definição de sucesso

Uma pessoa pede um móvel ou um cômodo. O sistema produz um plano auditável com os pré-requisitos ordenados, reutiliza capacidades existentes, aprende somente as ausentes, e **não executa** o que não consegue provar. Ao final do piloto, existe um **gabinete composto no `.skp` real de trabalho**, editável e inspecionado, com posição vinculada à parede/âncora e com aprovação humana pendente ou registrada. Não afirmar que a cozinha toda ficou pronta após um gabinete.

### 1.3 Escopo

**Dentro:** decomposição de móvel em capacidades atômicas, DAG de dependências, priorização de gaps, vínculo a recipes verificadas, contratos/execução dos incrementos faltantes, composição e posicionamento, testes L1/L2, inspeção SKP e pacote de revisão L3, rastreabilidade e reuso cross-room.

**Fora:** treinar pesos do LLM; criar agentes adicionais apenas por especialidade; trocar Python/Ruby; adicionar RAG/vector DB ou OR-Tools como requisito inicial; inventar medidas; substituir o catálogo ou os especialistas existentes; redigir dezenas de recipes sem execução; executar Ruby arbitrário; afirmar funcionalidade física de corrediça/dobradiça sem prova; alterar PDF, consensus, planta canônica, suíte aprovada ou qualquer outra área; render bonito como único critério; aceitar fontes de tutoriais não inspecionadas como demonstração visual assistida.

---

## 📐 BLOCO 2 — Especificação Técnica

### 2.1 Princípio central: aprender em cinco camadas

| Camada | Responsabilidade | Exemplo | Aprovação |
|---|---|---|---|
| **Operação geométrica** | Executar transformação mínima e mensurável, sem negócio do cômodo | painel, perfil, furo/recorte, rotação, material, componente | testes unitários determinísticos |
| **Capability** | Construir parte funcional reutilizável com contrato e provenance | frente Shaker, prateleira, caixa de gaveta | L1 + L2 de componente |
| **Assembly** | Compor capabilities em um móvel editável | gabinete com corpo, frente, prateleira e puxador | L1/L2 do móvel completo |
| **Placement** | Escolher instalação a partir da intenção e restrições do cômodo | gabinete na parede permitida, com acesso frontal | L1 geométrico + integração L2 |
| **Room furnishing** | Planejar e instalar um conjunto coerente de móveis no cômodo | pia, geladeira, bancada, armários | gates do cômodo + inspeção + L3 humano |

Uma capability não deve implementar regras de cozinha; um especialista de cozinha não deve reconstruir uma peça shared. Toda habilidade repetida entre ambientes pertence ao módulo `shared`, com adapters para restrições particulares. Reuso exige compatibilidade de frame/normal (+Y cabinet versus -Y wardrobe; FP-048), não apenas coordenadas que por acaso coincidam.

### 2.2 Fluxo obrigatório

```text
Pedido / DesignIntent do cômodo
  ↓
Room specialist existente → propósito e restrições
  ↓
FurnitureSpec (o móvel que precisa existir) + lista de partes
  ↓
Capability DAG (implementado/provado/ausente, com origem)
  ├── capacidade comprovada → reuso com versão/hash
  └── capacidade ausente → LearningTask pequena e bloqueante
                                   ↓
                         Recipe + fonte/locator confiável
                                   ↓
                         algoritmo geométrico + testes L1
                                   ↓
                         materialização em SKP micro + inspector L2
                                   ↓
                         catálogo/binding atualizado sob prova
  ↓ (somente com DAG satisfeito)
Assembly plan assinado → validar envelope, peças, colisões, editabilidade
  ↓
Placement plan (parede, âncora, frente, circulação, porta, acesso)
  ↓
Gates integrados e autorização tipada, explícita, por artefato
  ↓
CÓPIA .skp → salvar → fechar somente PID próprio → reabrir → inspecionar
  ↓
FP-047: regressão geométrica e isolamento por cômodo
  ↓
Evidências: planta 2D + frontal/topo/isométrica + trace + hashes
  ↓
L3: revisão humana de aparência e adequação arquitetônica
  ↓
Capacidade reutilizável / móvel entregue / próximo cômodo
```

**A IA decide qual habilidade vale investigar e propõe código.** Cálculo, dimensões, interseções e provas ficam no Python/Shapely/testes e na inspeção do SketchUp; IA não declara PASS por narrativa.

### 2.3 Estados: conhecimento não é execução

Não introduzir catálogo paralelo de status. Utilizar as dimensões independentes já mantidas em `capability_catalog.v1.json`: `knowledge`, `implementation`, `validation`, `visual` (respeitando exatamente o schema e vocabulários existentes). O relatório do ciclo traduz esses estados em decisões para o usuário:

| Condição observada | Decisão de produto |
|---|---|
| Técnica sem fonte com trecho/locator rastreável, **ou** fonte rotulada inspecionada **sem `human_review`** sustentando uma promoção | `BLOCKED_KNOWLEDGE_EVIDENCE` (**já existe** em `shaker_flow`; vocabulário FP-045) — não criar `BLOCKED_SOURCE_UNVERIFIED` |
| Recipe conhecida, mas binding sem capability | `BLOCKED_CAPABILITY_MISSING` existente no especialista |
| Código de capability existe, mas falta L1 vigente | `BLOCKED_L1_UNPROVEN` proposto no relatório |
| L1 passou, mas faltou SketchUp real ou prova está stale | `PENDING_SKETCHUP` (**já existe**: `tools/sketchup/knowledge.py`, FP-047 v1.1.0) — não criar `PENDING_L2`; sem usar L2_PASS |
| Modelo L2 passou; visual não revisado | `PENDING_HUMAN` para aceitação estética/posicionamento |
| Movimento, ferragem, hidráulica ou recorte não implementados | Bloqueio específico, nunca substituir por cubo ou simulação declarada como funcional |
| Todos os critérios obrigatórios com evidência vigente | `READY_FOR_NEXT_STEP`; ainda não autoriza execução automática |

Vocabulário: **reutilizar** os estados que já existem no código (`BLOCKED_CAPABILITY_MISSING`, `BLOCKED_KNOWLEDGE_EVIDENCE`, `PENDING_SKETCHUP`, `PENDING_HUMAN`, `BLOCKED_EVIDENCE_STALE`, `BLOCKED_INPUT_INCOMPLETE`…). Só `BLOCKED_L1_UNPROVEN` e `READY_FOR_NEXT_STEP` são novos, e são `cycle_status` de um relatório novo, **não** enumerações a inserir cegamente no schema atual. Qualquer extensão deve ter migração, compatibilidade e testes de schema.

### 2.4 Contratos de dados propostos (não existem hoje)

**A. `furniture_goal.v1`** — intenção antes do algoritmo:

```json
{
  "schema_version": "furniture_goal.v1",
  "project_id": "planta_74",
  "room_id": "r004",
  "furniture_id": "kitchen_base_001",
  "kind": "base_cabinet",
  "function": "storage_under_counter",
  "required_components": ["carcass", "front", "shelf"],
  "optional_components": ["handle"],
  "required_capabilities": ["shared.cabinet.parametric"],
  "dimension_inputs": "referências tipadas value/unit/origin do pedido ou do consensus",
  "installation": {
    "anchor_id": "OBRIGATORIO: ID existente no PDF/consensus ou declarado pelo usuário",
    "wall_id": "OBRIGATORIO: ID de parede válida",
    "front_normal": "OBRIGATORIO: orientação validada",
    "front_access_clearance": "medida tipada com origem e regra"
  },
  "execution_authorized": false
}
```

O exemplo acima é **ilustrativo**: strings descritivas não são medidas nem IDs reais. Um request real com esses placeholders **deve ser recusado**, não normalizado. O parser só aceita campos completos com unidades/proveniência e IDs encontrados no modelo; pode incorporar o `cabinet_request.v1` já existente por referência em vez de copiá-lo.

**B. `learning_task.v1`** — exatamente uma lacuna por trabalho:

```json
{
  "schema_version": "learning_task.v1",
  "task_id": "learn-drawer-box-001",
  "requested_by_furniture_id": "kitchen_base_001",
  "capability_id": "PROPOSED:shared.drawer.box",
  "dependency_ids": ["shared.cabinet.parametric"],
  "recipe_id": "cabinet.drawer-box-and-hardware",
  "source_locator": "OBRIGATORIO: referência real, identificável e verificável",
  "expected_geometry": ["left", "right", "back", "front", "bottom"],
  "functional_claims": ["assembled_drawer_box_only"],
  "verification": ["L1_parts", "L1_envelope", "L2_skp_editable"],
  "execution_authorized": false
}
```

`shared.drawer.box` é **nome candidato**, não capability existente. Não chamar a peça de *gaveta funcional com corrediça* sem modelar, instalar e validar a corrediça e o vão de movimento. Se a origem da técnica não for comprovada, aprender primeiro uma operação respaldada por documentação oficial ou especificação humana, nunca atribuir a um vídeo passos não observados.

**C. `learning_cycle_report.v1`** — registro agregado por incremento:

```json
{
  "schema_version": "learning_cycle_report.v1",
  "goal_id": "kitchen_base_001",
  "cycle_status": "BLOCKED_CAPABILITY_MISSING",
  "capability_dag": [],
  "missing_capabilities": [],
  "learned_capabilities": [],
  "assembled_objects": [],
  "placement_evidence": null,
  "l1": {"result": "NOT_RUN", "report_path": null},
  "l2": {"result": "NOT_RUN", "skp_copy": null, "inspection_path": null},
  "l3": {"result": "NOT_REVIEWED", "review_path": null},
  "source_digests": {},
  "artifact_sha256": {},
  "execution_authorized": false
}
```

O relatório final deve vincular `request_digest`, `code_digest`, versão da capability, `consensus_digest`, `base_skp_digest`, evidência, CI, versão real do SketchUp, resultado dos gates e decisão humana. Nunca publicar resultados como `L2_PASS` apenas porque um teste com FakeSystem passou.

### 2.5 Invariantes e decisões obrigatórias

**R-01 — Uma capacidade por incremento.** O agente não implementa ao mesmo tempo gaveta, trilho, puxador, recorte de pia e gaveta de guarda-roupa. Seleciona um gap de maior impacto no próximo móvel; fecha tests/PR/prova antes de abrir o seguinte.

**R-02 — Reutilização por identidade.** Consultar símbolo+assinatura+versão+prova no catálogo antes de criar novo builder. Não duplicar `cabinet` para `wardrobe`; usar FP-048 para adaptar coordenadas.

**R-03 — Fonte antes de implementação atribuída.** Recipe aponta para source, locator e classe real de evidência. Transcrição não é inspeção visual. Vídeos ensinam procedimentos, não fornecem automaticamente medidas do apartamento. **Um rótulo `TRANSCRIPT_AND_VISUAL_WALKTHROUGH` dado por uma sessão anterior, sem revisor, não basta para promover uma capability:** exige `human_review` na fonte (quem, quando, trecho, itens confirmados), como na D46-09. Hoje só `yt-cabinet-tips-2021` tem — e a revisão vale **só para a recipe `cabinet.front-gaps-and-profiles` e o trecho 03:13–04:29** que registrou: outra recipe da mesma fonte (ex.: `cabinet.countertop-separate-and-bevel`, 07:09–08:53) **não herda** a revisão. A fonte da recipe de gaveta (`yt-kitchen-joinery-2024`, 21:20–39:23, ~18 min) **não** tem.

**R-04 — Zero dimensão mágica.** Medida, unidade e origem obrigatórias (`value`, `unit`, `origin`), inclusive folga funcional. Valores default só quando contrato versionado os declara explicitamente e não violam a política de origem do projeto.

**R-05 — DAG sem buracos.** Sem capacidade obrigatória implementada e provada, `BLOCKED`; sem substituição silenciosa por box ou frente lisa. Componentes opcionais podem ser omitidos somente quando a solicitação autoriza omissão.

**R-06 — Parte ≠ móvel.** Micro-fixture valida uma técnica; não comprova montagem de móveis nem posicionamento. Assembly exige raiz de móvel, filhos semânticos, materiais/IDs, assinaturas, e edição por instância sem afetar outras inadvertidamente.

**R-07 — Móvel ≠ cômodo.** O layout depende de parede, função, abertura, hidráulica, porta, circulação e outras peças. A FP-050 (quando integrada) será um gate de seleção/posicionamento, não simples sugestão bypassável.

**R-08 — Sem falso 3D.** Shapely verifica envelopes 2D; alturas, volumes e trajetórias de portas/gavetas exigem validação adicional 3D ou por estados geométricos adequados. Sem modelo dessas condições, registrar limitação e bloquear alegação funcional.

**R-09 — Execução só com assinatura.** `require_valid` do plano de gabinete e gates de assembly/placement precisam validar versões e assinatura imediatamente antes do SketchUp. Bloqueios não podem ser pulados por chamadas Ruby diretas nem pelo fluxo antigo de `cabinet_flow`.

**R-10 — Somente cópia.** Snapshot/assinatura dos canônicos antes e depois; nunca editar `.skp` original/PDF/consensus/fixtures protegidas. Salvar no diretório `runs/` e descartar cópia em falha.

**R-11 — L2 real.** Salvar, fechar processo iniciado pelo job, reabrir no SketchUp Windows, inspecionar partes e transforms, comparar com plano, comparar elementos não alvo por FP-047. FakeSystem é teste de integração de harness, não prova L2.

**R-12 — L3 humano.** O sistema gera views top/front/iso e análise de problemas, mas nunca autoaprova estética/adequação arquitetônica. Mudança visual significativa = `PENDING_HUMAN`.

**R-13 — Evidência revogável.** Mudança no símbolo, fonte, recipe, transformação ou esquema que afete a prova invalida `L2_PASS` até revalidação. Preservar o histórico sem apagar a falha.

**R-14 — Sem loops infinitos.** Uma unidade de trabalho fecha com `DONE`, `BLOCKED` específico ou `FAILED` reproduzível, com próximo comando/PR. Não deixar agente “tentando até ficar bom” sem critério de parada.

**R-15 — Progresso do produto.** Métrica útil é quantidade de móveis completos, bem posicionados e aprovados, além de quantidade de capabilities reutilizadas. Número de recipes, commits ou testes verdes isoladamente não significa progresso do apartamento.

### 2.6 Plano faseado com entregas pequenas

| Fase / PR | Entrega concreta | Evidência e saída | Dependência |
|---|---|---|---|
| **P0 — reconciliar baseline** | Classificar FP-045/046/047, #346/#347/#355; medir gaps e escolher primeiro móvel do piloto; fixar IDs existentes e estados reais | `fp051_baseline.json` e matriz capability→móvel→cômodo; zero alteração geométrica | nenhuma |
| **P1 — gap planner mínimo** | Função pura `plan_furniture_goal()` reutilizando `specialists.plan` e `capability_catalog`, que retorna DAG/next gap e recusa componentes ausentes | unitários para reuso, missing, ciclo, stale evidence, fonte fraca, schema e nenhuma execução | P0 |
| **P2 — primeiro aprendizado executável** | Escolher **uma** capacidade faltante que seja necessária ao próximo móvel, preferencialmente `drawer_box` **só a caixa montada, sem corrediça nem ferragem**; a recipe atual (`cabinet.drawer-box-and-hardware`, rota `PARAMETRIC_DRAWER_ASSEMBLY_MISSING`) mistura caixa e ferragem: **dividir antes de aprender**. Implementar recipe→capability compartilhada | teste vermelho→verde, L1 com dimensões variadas e propriedades (Hypothesis **só se declarada como dependência de dev**: hoje só o PR #355 a declara; sem isso o P2 declara em `pyproject.toml` e o CI já instala `.[dev]`), micro SKP editável, L2 Windows real, registro com proveniência | P1 + fonte com `human_review` (trecho da caixa, o mais curto possível) |
| **P3 — composição de móvel** | Gerar o **primeiro gabinete completo**, reutilizando `shared.cabinet.parametric`, Shaker/frente quando requisitada, prateleira existente e nova capacidade P2 se pedida. Não duplicar assembly da FP-049 | raiz e partes semânticas no `.skp`, assinatura, materiais/IDs estáveis; L1/L2 do móvel completo | P1 e capacidades requeridas |
| **P4 — conectar posicionamento** | Reconciliar/mergear FP-050 após CI e revisar no contrato de `cabinet_flow` como gate obrigatório; obter parede/âncora reais do consensus e envelope dos móveis/portas. **Aplicar o gate nos DOIS fluxos** (`cabinet_flow.run_request` e `shaker_flow.run_request`/`plan_kitchen_shaker`): senão o gate tem bypass (R-09) | posicionado em planta real, bloqueio para normal invertida/gaveta sem abertura/corredor, nenhum bypass pelo executor. **Custo previsto (R-13/R-18):** mudar esses símbolos invalida o L2 vigente de `kitchen.cabinet.plain-fronts` e `kitchen.cabinet.shaker-door` — o P4 inclui **refazer o L2 dos dois fluxos** em commit limpo, como na promoção da Shaker | P0/P3; FP-050 (#355, draft com CI verde) |
| **P5 — prova vertical real** | Materializar gabinete no `.skp` **de trabalho** da cozinha, reabrir/inspecionar e comparar FP-047 | antes/depois, report L1/L2, partes editáveis, delta restrito ao gabinete, `PENDING_HUMAN` | P3/P4; FP-047 |
| **P6 — concluir módulo útil de cozinha** | Estender somente o que for necessário para a composição da bancada e gabinete na parede aprovada, respeitando pia fixa e eletrodomésticos | um conjunto coerente da cozinha aprovado; nada de “cozinha concluída” se houver lacunas | P5 + aprovação |
| **P7 — comprovar reuso real** | Consumidor **diferente** usa a mesma capability compartilhada, preferencialmente quarto/guarda-roupa após FP-048/049 | mesmo símbolo+versão em 2 consumidores, transforms corretos (+Y/-Y), inspeção L2 de ambos | FP-048/049 + P2/P5 |
| **P8 — operação contínua** | Checklist CLI e documentação: selecionar próximo gap, executar pequena prova, atualizar inventário e avaliar próximo móvel/cômodo | guia de uso pelo ChatGPT/Claude sem Astra obrigatório; nenhuma tarefa sem saída audível | P0–P7 |

**Política de PRs:** não empilhar todas as fases num PR; `P0`, `P1`, `P2` etc. são gates separáveis. Fases podem caminhar em paralelo somente se suas interfaces já são estáveis e sem tocar os mesmos arquivos protegidos. CI verde não autoriza merge automático de mudança visual.

### 2.7 Estratégia de implementação (reuso antes de novidade)

| Área | Código existente / dono | Mudança permitida |
|---|---|---|
| Recipes e fontes | `references/sketchup/knowledge/`, `tools/rooms/kitchen/knowledge/index.v1.json` | referenciar fontes verificadas; não duplicar transcrições |
| Catálogo e perfis | `tools/rooms/capability_catalog.py`, `capability_catalog.v1.json`, `specialists.py`, `specialist.v1.json` | estender registros com provas reais e sem quebrar schemas |
| Gabinete compartilhado | `tools/rooms/shared/cabinet/{model,assembly,plan,validation,sketchup}.py` | reutilizar contratos/assinatura existentes |
| Shaker | `tools/rooms/shared/cabinet/shaker/` | consumir sem reimplementar; preservar frente lisa |
| Composição compartilhada | `tools/rooms/shared/assembly/` **proposto na FP-049** | não criar segunda implementação: coordenar a FP-049 ou compor com interfaces existentes |
| Placement de cozinha | `tools/rooms/kitchen/planning/` **no PR #355 (não em develop)** | aproveitar a FP-050 e tornar o gate não contornável, após CI |
| Executor de cozinha | `tools/rooms/kitchen/capabilities/cabinet_flow.py` | inserir validação de placement antes do job, sem bypass |
| Regressão | FP-047 + `tools/validation/` | comparar célula, arquitetura, objetos fora do escopo e hashes |
| **NOVO, somente se necessário** | `tools/rooms/learning/{planner,report}.py` | orquestração pura dos gaps/DAG; **nunca** duplicar `specialists.plan` ou um executor |
| Testes | `tests/test_fp051_*.py` | negativos, propriedades, FakeSystem e L2 Windows separado |
| Documentação de progresso | `docs/reports/FP-051_*.md`, `runs/fp051/` | hashes, traces, relatório e provas geradas |

Toda inclusão de arquivo versionado deve atualizar `docs/specs/fp042_inventory.v1.json` no mesmo PR e preservar o gate estrito de ownership.

### 2.8 Testes e critérios de aceite Given / When / Then

| ID | Given / When | Then / resultado obrigatório |
|---|---|---|
| **CA-01** | Dado um componente que já possui capability válida, ao decompor o móvel | gera dependência do símbolo atual, **não** um builder duplicado |
| **CA-02** | Dada uma recipe `drawer-box` sem binding executável | `BLOCKED_CAPABILITY_MISSING`, sem job nem componente fake |
| **CA-03** | Dada fonte apenas transcrita/descrita, ao gerar plano de aprendizado | evidência classificada corretamente; não afirmar vídeo inspecionado |
| **CA-04** | Dados parâmetros sem unidade, origem, IDs válidos ou dimensões finitas | plano recusado antes de abrir SketchUp |
| **CA-05** | Dados dependência cíclica e símbolo stale | ambos bloqueiam com códigos reproduzíveis; sem loop infinito |
| **CA-06** | Dada capability recém-criada | deve ter teste vermelho→verde e variações de dimensões/orientações; geometria válida |
| **CA-07** | Dada capability que só passou no CI Linux | permanece sem L2_PASS; exige SketchUp Windows salvo/reaberto |
| **CA-08** | Dado gabinete composto | todas as partes têm IDs estáveis, grupo selecionável, componentes editáveis e materiais por papel |
| **CA-09** | Dadas frentes Shaker e lisa | prova separada, sem sobreposição, sem reescrever o comportamento legado |
| **CA-10** | Dado placement sem parede ou âncora comprovada | BLOQUEADO; não escolher centro do cômodo como fallback |
| **CA-11** | Dado gabinete que invade circulação ou bloqueia acesso frontal | posição rejeitada, sem Ruby job |
| **CA-12** | Dado gabinete sem posições válidas | `NO_VALID_POSITION` com motivos, sem criar posição arbitrária |
| **CA-13** | Dada pose aprovada mas adulterada depois do gate | falha por assinatura/versão antes da materialização |
| **CA-14** | Dada execução válida em cópia | salvar, fechar PID próprio, reabrir e inspecionar transforms/partes e conteúdo não alvo |
| **CA-15** | Dado delta num cômodo não autorizado ou no canônico | FAIL e rollback da cópia; FP-047 sinaliza a regressão |
| **CA-16** | Dado SKP real e aparência não revisada | L2 pode passar, **L3 permanece PENDING_HUMAN** |
| **CA-17** | Dadas duas consumers (kitchen e bedroom) | mesma capability compartilhada, frames convertidos corretamente, sem cópia da geometria |
| **CA-18** | Dado custo de token alto/indisponibilidade de agente | cada fase opera por handoff textual + JSON, com comandos e próxima ação reproduzível |
| **CA-19 E2E** | Pedido real de 1 gabinete na `planta_74`, com fontes/medidas e posição válidas | gabinete completo em **cópia SKP**, reinspecionado, posição correta, isolado por FP-047, relatório L1/L2 e status visual honesto; caso contrário BLOCKED com motivos |

**Negativos obrigatórios:** medidas 0/NaN/inf, normal de frente invertida, wall ID inexistente, âncora fora da parede, gabinete impossível, abertura invadindo móvel, colisão em altura relevante, caixa genérica substituindo gaveta, profile/allowlist inválidos, capability com hash alterado, diffs não autorizados e L2 falso (apenas fake). 

**Execução de testes, sem inventar comandos inexistentes:** integrar os `tests/test_fp051_*.py` à separação já usada no CI: `pytest -m 'not planta74_scale'` e `PT_TO_M=0.0259 pytest -m planta74_scale`. Executar `python -m tools.rooms.capability_catalog` e os gates de inventory, ownership e fidelity existentes. Testes SketchUp reais **somente no Windows** com registro da versão instalada, cópia de trabalho e relatório de inspector.

### 2.9 Requisitos não funcionais, segurança e confiabilidade

- **Determinismo:** mesma entrada, versões e contexto produzem os mesmos IDs lógicos, ranking e assinatura (fora de campos de diagnóstico não assinados).
- **Performance e custo:** planejamento L1 headless sem SketchUp; render/inspeção L2 só depois de gates; nenhum solver, novo agente ou serviço externo no primeiro piloto.
- **Observabilidade:** etapa, motivo de rejeição, source ID/locator, capability/version/digest, contagem de alternativas, paths/hashes, versão do SketchUp, PID próprio, cobertura de teste.
- **Segurança:** sem execução livre de scripts de terceiros; allowlist tipada e isolamento de processo; alterações apenas em cópias e branches; decisões explícitas para mudança visual.
- **Compatibilidade:** consumidores antigos `cabinet_request.v1` e `cabinet_assembly_plan.v1` permanecem válidos sem delta; versões novas precisam de adapters sem reinterpretar contratos históricos.
- **Falha fechada:** dado crítico ausente implica `BLOCKED`, não escolha criativa. CI skipped ou tests dublês não autorizam alegação de L2.
- **Reprodutibilidade:** comandos, input JSON, source commit e hashes registrados por incremento. Handoff em texto simples para ChatGPT sem longas sessões de agente.

### 2.10 Definição de pronto: critérios de produto

**A primeira entrega da FP-051 não é “todas as receitas aprendidas”.** É **um caminho vertical demonstrável** com:

1. Uma técnica ausente **identificada por causa de um móvel real**, com dependência documentada.
2. Uma capability implementada (ou bloqueada honestamente por falta de fonte), com L1/L2 quando possível.
3. Um gabinete composto exclusivamente de capabilities autorizadas, com peças reais, não caixas ilustrativas.
4. Uma posição admissível na cozinha `r004`, escolhida a partir do `consensus` real, jamais por coordenadas aleatórias.
5. Um `.skp` de trabalho salvo, reaberto e inspecionado com regressão FP-047.
6. Um pacote visual para decisão humana e a lista explícita de lacunas remanescentes da cozinha.
7. Uma segunda consumer comprovada **antes de afirmar reuso cross-room**; se a FP-048/049 não estiver pronta, manter P7 como BLOCKED, sem barrar a entrega honesta de P5.

---

## 🔄 BLOCO 3 — Governança e Sequenciamento

### 3.1 ADRs

| ID | Decisão | Justificativa |
|---|---|---|
| D51-01 | Manter Python para planejamento e Ruby para adapter SketchUp | Linguagem não é o gargalo provado; preservar código e gates |
| D51-02 | Reusar catálogo, perfis, receitas e flow existentes | Evitar orquestrador/agentes e banco de conhecimento duplicados |
| D51-03 | Ensinar **somente o próximo gap bloqueante** | Capacidade comprovada supera dezenas de tutoriais catalogados |
| D51-04 | Composição por DAG, não templates isolados de cômodo | Permite reuse e falha precisa quando falta peça |
| D51-05 | Sem OR-Tools no MVP | Gerador determinístico de posições e regras já basta para testar hipótese; introduzir solver se aparecer complexidade combinatória real |
| D51-06 | Reconciliar FP-048/049/050, não duplicá-las | Ownership, frames, montagem e placement já possuem propostas separadas |
| D51-07 | Distinguir montagem, colocação e qualidade final | Elimina falso PASS de gabinete bem feito e mal colocado |
| D51-08 | Evidência L2 é revogada por mudança de símbolo: toda fase que altera um fluxo já provado inclui o rerun L2 dele | Visto na promoção da Shaker (o guard no `cabinet_flow` invalidou a P7) |
| D51-09 | Reutilizar o vocabulário de estados existente | Evita `PENDING_L2`/`BLOCKED_SOURCE_UNVERIFIED` paralelos aos que o código já tem |

### 3.2 Dependências e bloqueios

- #346 (FP-048) e #347 (FP-049): **draft** no baseline auditado; não assumir API pronta nem merge realizado.
- #355 (FP-050): **draft** no baseline auditado; algoritmo L1 do piloto não prova integração à planta real.
- FP-046 Shaker: código/catálogo marcados L2_PASS; **não** equivale a L3 aprovado.
- Para `drawer_box`, validar origem técnica e real necessidade no móvel antes de abrir PR. A fonte da recipe atual (`yt-kitchen-joinery-2024`, 21:20–39:23) está rotulada como inspecionada **mas não tem `human_review`**: antes do P2 o Felipe revisa o trecho da CAIXA (o mais curto possível) ou a troca por outra capability é justificada. Se não houver fonte suficiente, escolher outra capability de menor risco com fonte oficial; nunca inventar evidência.
- Permissão de merge e de alteração de arquivo de referência **não** substitui revisão visual humana quando houver mudança de aparência.

### 3.3 Revisão e rollback

Cada PR traz: diff de arquivos, owner, baseline SHA, teste falhando antes/verde depois, inputs/outputs, resultados CI, evidência L2 se necessário, estado L3, e instrução de rollback. Em erro: abortar materialização, preservar log de falha, descartar cópia e deixar canônico intacto. Nunca desabilitar gate de inventário ou elevar tolerância sem prova.

### 3.4 Métrica semanal de progresso (sem autoengano)

Reportar quatro contagens separadas: `capabilities_L2_com_prova_vigente`, `furniture_assemblies_L2`, `furniture_placed_in_correct_room_L2` e `rooms_approved_L3`. Acrescentar `blocked_gaps` e `reused_capabilities_cross_room`. Não chamar uma receita escrita de uma habilidade aprendida nem um móvel isolado de um cômodo mobiliado.

---

## 🚀 BLOCO 4 — Handoff para ChatGPT/Claude (copiar e executar por fases)

> Você está implementando a **FP-051** no repositório `GFCDOTA/sketchup-mcp`, branch `develop`.
>
> 1. Confira o SHA atual e reconcilie FP-045, 046, 047 e PRs #346, #347, #355 antes de editar. O baseline documentado é histórico, não assuma que permanece atual.
> 2. Execute **somente P0**, produza um inventário factual das capabilities já implementadas, provas L1/L2/L3, recipes e bindings sem capability. Escolha um primeiro gabinete útil da cozinha r004 e registre exatamente que capacidades faltam; não invente dimensões ou posições.
> 3. Em seguida execute P1 com testes vermelhos→verdes, reaproveitando `specialists.plan` e `capability_catalog`. Nenhum Ruby ou `.skp` nessa fase.
> 4. Proponha o primeiro gap de P2 com contrato pequeno. Use a fonte real da recipe e o símbolo shared; implemente só uma técnica por PR. Se faltar fonte/locator **ou `human_review`**, reporte `BLOCKED_KNOWLEDGE_EVIDENCE` e não alegue ter assistido ao vídeo.
> 5. Em P3–P5 componha o gabinete com peças reais; selecione posição via restrições da cozinha e FP-050 (após integração); execute somente em cópia; salve/reabra/inspecione no SketchUp Windows; rode FP-047 e registre revisão visual humana pendente.
> 6. Em toda fase atualize testes, inventário FP-042 e evidências. CI verde sozinho não é L2. Não marque como concluída etapa que não conseguiu executar. Faça PRs pequenos e não deixe qualquer fluxo pular um gate.
> 7. Entregue após cada fase um handoff curto: SHA, PR, testes, arquivos alterados, L1/L2/L3 reais, bloqueios e próximo comando reproduzível. Nada de progresso inventado ou “tentar novamente indefinidamente”.

### Checklist de aceite final

- [x] Código baseline inspecionado e PRs em andamento reconciliados (P0: `docs/reports/FP-051_P0_baseline.md`, `docs/reports/fp051/fp051_baseline.json`).
- [ ] GAP planner reproduzível conectado ao catálogo existente.
- [ ] Ao menos uma capacidade antes ausente teve aprendizado/implementação com fonte real e teste L1/L2 (ou bloqueio técnico documentado, sem afirmar entrega total).
- [ ] Assembly de um móvel completo com partes semanticamente editáveis.
- [ ] Placement obrigatório ligado à intenção da cozinha real, sem bypass.
- [ ] Nenhuma alteração canônica, e comparação FP-047 sem regressão não autorizada.
- [ ] SKP de trabalho salvo/reaberto/inspecionado em Windows; FakeSystem não conta como L2.
- [ ] Evidência de decisão L3 ou estado `PENDING_HUMAN` explícito.
- [ ] Reuso cross-room afirmado somente com segundo consumidor executado e testado.
- [ ] Relatório indica corretamente o que foi aprendido, fabricado, posicionado e aprovado.

---

### 3.5 Histórico de versões e validação contra o código

| Versão | Data | Autor | Descrição |
|---|---|---|---|
| 1.0.0 | 2026-10-21 | ChatGPT/Felipe | SPEC SDD P0–P8, D51-01..07, CA-01..19 |
| 1.1.0 | 2026-10-21 | Claude (validação contra o código) | Afirmações da spec verificadas por `tools/navigation/fp051_baseline.py` (`spec_claims`): capabilities L2, bindings sem capability, módulos propostos ausentes em `develop`, frames `+Y` (gabinete) × `-Y` (guarda-roupa), `human_review` só no `tips-2021`. **Cinco correções:** (1) vocabulário de estados — reutilizar `PENDING_SKETCHUP` e `BLOCKED_KNOWLEDGE_EVIDENCE` (D51-09); (2) fonte rotulada inspecionada **sem `human_review`** não promove capability (R-03; gaveta: `yt-kitchen-joinery-2024` sem revisão, recipe mistura caixa e ferragem); (3) custo do P4: gate nos dois fluxos + rerun L2 de ambos (D51-08); (4) `hypothesis` não está declarada em `develop` (só no #355); (5) o escopo da `human_review` (uma recipe, um trecho) agora é explícito no R-03 e no baseline (`human_review_other_scope`). Baseline reconciliado: ver P0. |

**Achado fora do escopo do P0 — CORRIGIDO depois (2026-10-21, follow-up do #357; o texto abaixo é o achado original):** `shaker_flow.run_request` confere que a fonte do pedido tem *alguma* `human_review`, mas não que ela cobre a **recipe** do pedido (`origin_context.recipe_id`); um `source_verified=true` apontando para outra recipe do mesmo vídeo passaria. Corrigir muda o símbolo e exige refazer o L2 do fluxo (D51-08). Estava medido em `spec_claims` (`flow:source_verified-checks-review-scope`, hoje `ok: true`); evidência do L2 refeito: `artifacts/review/fp046/review_scope_l2/README.md`.

**Não corrigido de propósito:** o exemplo de `furniture_goal.v1` com placeholders é ilustrativo e já diz que deve ser recusado; os PRs #346/#347/#355 seguem em draft (a spec já os trata como bloqueios, não como API pronta).
