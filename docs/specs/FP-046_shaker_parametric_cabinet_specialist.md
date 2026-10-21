# 📐 SPEC de Feature — FP-046: Porta Shaker Paramétrica e Especialista de Marcenaria
> Fluxo de Desenvolvimento Agêntico (SDD) · sketchup-mcp · Python / Ruby / SketchUp Windows / MCP stdio

## 🏷️ BLOCO 1 — Metadata

```yaml
spec:
  feature: "FP-046 — Porta Shaker paramétrica e execução comprovada"
  escopo_versao: "Acrescentar uma capability de porta Shaker com moldura e painel realmente rebaixado ao gabinete compartilhado, comprovada do plano à inspeção no SketchUp."
  versao: "1.1.0"
  status: "RASCUNHO_VALIDADO_CONTRA_DEVELOP"
  classificacao:
    contexto_delimitado: "Marcenaria Paramétrica"
    dominio: "SketchUp MCP / Especialistas por Cômodo"
    funcionalidade: "Conhecimento → porta Shaker editável → L1/L2/L3"
  autor: "GPT-6 (proposta SDD); decisão estética e de produto: Felipe"
  data_criacao: "2026-10-21"
  ultima_atualizacao: "2026-10-21"
  baseline_develop: "23939d9"
  baseline_develop_original: "214d73e3c38c8bae9a3dc16f0fc579b64a017ac7"
  validacao: "2026-10-21: assinaturas de assembly/model/plan conferidas; P0 entregue em #345; correcoes em 3.2 (v1.1.0)"
  status_reconciliacao: "Em 2026-10-21, develop avancou para 029f9685 (PR #343); 4 fachadas D-011 removidas, nao pertencem ao escopo desta SPEC."
  spec_mae: "docs/specs/FP-045_specialists_knowledge_and_room_modularization.md"
  specs_dependentes: ["FP-047 (regressão geométrica e visual, contrato complementar)"]
  pr_alvo: "develop"
```

**Nota de escopo da versão:** implementar **uma técnica avançada completa**, porta Shaker de moldura + painel rebaixado, como incremento opcional no programa de gabinete, garantindo regressão zero para frentes lisas já aprovadas. “Capacidade implementada” e “aparência aprovada” são provas distintas.

**Dentro:** fonte/receita e binding corretos; contrato parametrizado e versionado; geometria de componentes; materialização Ruby numa cópia; edição local com `make_unique`; validação matemática e inspeção no SketchUp; micro-fixtures, evidências e controles; documentação e registro no capability catalog.

**Fora:** gavetas, corrediças, dobradiças, sistema de portas de correr, ferragens, venezianas, entalhes industriais, plano de corte, tolerâncias normativas ou certificação de fabricação, UV/veio de madeira (permanece `NOT_SUPPORTED`), qualquer alteração no apartamento real antes do veredito; nenhuma nova API REST, Kafka, SQS, ou permissão de Ruby arbitrário.

## 📐 BLOCO 2 — Especificação Técnica

### 2.1 Resumo da Feature

O código atual **já** planeja gabinetes `cabinet_request.v1` → `cabinet_assembly_plan.v1`, constrói painéis retangulares + frentes lisas, valida plano, escreve somente uma cópia `.skp` com instâncias de componentes editáveis, reabre e confere. A execução vertical de cozinha existe em `tools.rooms.kitchen.capabilities.cabinet_flow.run_request`. As receitas Shaker existem, **mas** `bind.kitchen.shaker` não possui capability e deve responder `BLOCKED_CAPABILITY_MISSING`.

**Motivo:** transformar uma receita consultiva em uma técnica de modelagem reproduzível, sem promover conhecimento/execução por mera transcrição de vídeo. A entrega terá peças reais: montantes laterais, travessas superior/inferior e painel central recuado, semanticamente identificáveis e editáveis.

**P0 resolvido em #345 (2026-10-21).** `capability_catalog.verify` ganhou `BINDING_SOURCE_MISMATCH` (fontes do binding == união das fontes das suas recipes) e os 4 bindings foram corrigidos *derivando das recipes*, sem criar fonte, locator ou evidência. Medido: `shaker` → `yt-cabinet-styles-2024`; `drawer`/`sink-cutout` → `yt-kitchen-joinery-2024`; `cabinet` passou a citar também `yt-cabinet-styles-2024` (a recipe `front-gaps-and-profiles` o cita).

**Consequência que a v1.0.0 não previu (D46-09, PENDENTE):** `yt-cabinet-styles-2024` é `TRANSCRIPT_AND_DESCRIPTION_ONLY`. O teste `test_implemented_binding_is_not_backed_only_by_description_only_sources` (#340) exige ≥1 fonte *inspecionada* em todo binding com capability — logo `bind.kitchen.shaker` **não pode receber `capability_id` enquanto só citar essa fonte**, e acrescentar uma fonte ao binding sem a recipe citá-la reprova `BINDING_SOURCE_MISMATCH`. Caminhos legítimos (decisão técnica + Felipe, sem inventar evidência): (a) a recipe Shaker passar a citar uma documentação oficial já lida (`official-components`/`official-groups`, `OFFICIAL_DOCUMENTATION_READ`) com `locator` real e relação declarada; ou (b) alguém inspecionar o vídeo e elevar a evidência da fonte. Até lá o P4 (ligar o binding) fica `BLOCKED_DECISION`; P1–P3 (plano puro, builder, L2 em micro-fixture) não dependem disso.

**Gap observado em 2026-10-21 (pré-condição, histórico — fechado pelo P0 acima):** `bind.kitchen.shaker` indica `yt-cabinet-tips-2021`, enquanto a recipe `cabinet.recessed-shaker-and-louvers` referencia `yt-cabinet-styles-2024`. O catálogo atual testa se IDs existem, mas não se o binding cita uma fonte efetivamente referenciada pela recipe. **Não resolver alterando uma fonte no chute.** Abrir primeiro micro-PR da FP-045/F4 com teste `binding.source_ids ↔ recipe.sources/source_refs` e correção após inspeção da origem. Os mesmos negativos se aplicam a `bind.kitchen.drawer` e `bind.kitchen.sink-cutout` (ambos apontam `yt-cabinet-tips-2021`, ao passo que suas recipes apontam `yt-kitchen-joinery-2024`). Não elevar `TRANSCRIPT_AND_DESCRIPTION_ONLY` para inspeção visual sem prova.

**Estado inicial real:** `tools.rooms.shared.cabinet.assembly.build_parts` retorna frentes retangulares `front`/`front_1`/`front_2` e `tools.rooms.shared.cabinet.sketchup.GRAIN_SUPPORT = NOT_SUPPORTED`; `cabinet_build.rb` cria componentes e `Cabinet_<request_id>` e só aceita `shared.cabinet.parametric`. Qualquer nova capability deve respeitar essa fronteira ou criar contrato versionado explícito.

**Fases:**

| Fase | Entrega | Saída exigida |
|---|---|---|
| P0 | **ENTREGUE (#345, 2026-10-21):** prova de origem e negativa dos bindings inconsistentes (eram 4, não 3: `shaker`, `drawer`, `sink-cutout` **e** `cabinet`) | fonte correta, receita rastreável; CI do PR independente |
| P1 | Contrato `shaker_door_request.v1` + plano puro e fixtures | validação rígida, geometria sem overlap, assinatura |
| P2 | Builders shared de moldura, travessas e painel recuado | teste de propriedades, identidade e editabilidade; sem SU |
| P3 | Driver Ruby/SketchUp da capacidade e inspector | L2 Windows em 0°/90°/30° e 1/2 portas; salvar/reabrir |
| P4 | Adapter e roteamento do especialista `kitchen` | request → recipe/binding/capability → gates → job em cópia → trace |
| P5 | Regresso de frentes lisas + controles do apartamento | saída anterior idêntica para fluxo antigo; nenhuma mudança canônica |
| P6 | Prova visual e documentação/rollout | `PENDING_HUMAN` até Felipe revisar; atualizar catálogo por commit/digest |

**Estratégia:** primeiro implementar a técnica no módulo `shared`, depois a cozinha apenas como adapter; reutilização futura em quarto/closet é potencial, não prova deste MVP.

### 2.2 Arquitetura de Solução

```text
references/sketchup/knowledge/video_recipes.v1.json
  -> tools.rooms.kitchen.knowledge/index.v1.json + capability_catalog.bindings
  -> tools.rooms.specialists.plan (advisory; execution_authorized=false)
  -> PROPOSTO: tools.rooms.shared.cabinet.shaker.plan_shaker_door
     -> PROPOSTO: tools.rooms.shared.cabinet.shaker.validate_shaker
     -> capability + assinatura determinística + require_valid equivalente
  -> tools.rooms.kitchen.capabilities.cabinet (4 gates existentes)
  -> tools.rooms.shared.cabinet.sketchup.materialize OU novo adapter tipado
  -> PROPOSTO: tools/rooms/shared/cabinet/ruby/shaker_build.rb
  -> SketchUp (apenas SKP de trabalho) -> inspeção -> métricas -> L3 humano
```

**Regra arquitetural:** planejar/montar peças neutramente em `tools/rooms/shared/cabinet/`. Não inserir regra hidráulica da cozinha em shared. Não chamar `cabinet_build.rb` com plano de outra capability esperando que aceite: ele checa `shared.cabinet.parametric`. A estratégia de compatibilidade (extensão versionada do plano antigo **ou** materializador Shaker específico) é uma ADR a ser tomada em P1 e validada por fixture negativa. Manter `cabinet_request.v1` e `cabinet_assembly_plan.v1` antigos funcionando sem mudança nos outputs atuais.

#### 2.2.1 Pipeline obrigatório

1. Ler a recipe `cabinet.recessed-shaker-and-louvers` e as fontes efetivas; bloquear se fonte/binding sem correspondência.
2. Receber request de porta Shaker com `request_id`, medidas `value/unit/origin`, material da moldura/painel, espessuras, recuo e pose, referenciando a frente do gabinete.
3. Resolver `kitchen` via `tools.rooms.specialists.plan` e binding `bind.kitchen.shaker`; até existir capability, devolver bloqueio específico, sem job.
4. Validar entradas por `tools.rooms.shared.cabinet.model.quantity` ou contrato equivalente, sem defaults de fabricante não registrados.
5. Derivar quadro local conforme `assembly.py`: +x largura; +y traseira→frente; +z altura; `pose.rotation_deg` em torno de +z.
6. Planejar uma **submontagem Shaker** para cada frente selecionada: montantes esquerdo/direito, travessas entre montantes, painel central com face visível realmente atrás das faces frontais das travessas.
7. Validar envelopes, espessura, folgas, peças com volumes positivos e sem interseção volumétrica positiva; provar recuo por coordenadas, não por material/ilusão.
8. Gerar `plan_signature`/`idempotency_key` com versão, medidas, source recipe e digests de código; não assinar dados incompletos.
9. Executar adapter cozinha: âncora pia oeste, arquitetura, sobreposição de mobília, circulação (mesma ordem dos gates já existentes).
10. Autorizar explicitamente job da capability somente após `require_valid` tipado; recusar qualquer ferramenta fora da allowlist.
11. Criar a submontagem em uma cópia nova `runs/`: grupo `Cabinet_<request_id>` ou subgrupo aninhado explícito; partes como componentes editáveis; sem duplicação.
12. Salvar, fechar PID próprio, reabrir e inspecionar `part_id`, role, material, geometria, transformações, tags, definição e assinatura.
13. Comparar plano×inspeção e estado prévio dos objetos fora do gabinete; resultado L2 somente se todas as invariantes passam.
14. Gerar pacote visual top/iso/frente e folha-contato; rotular `PENDING_HUMAN` se aparência mudou; Felipe decide.
15. Promover catálogo no nível efetivamente validado, com hash dos símbolos, fixtures, commit, versão SketchUp e evidência; nunca mascarar skipped.

#### 2.2.2 Regras numeradas e tabelas de decisão

| Regra | Condição | Resultado observável |
|---|---|---|
| R-01 | `bind.kitchen.shaker` sem capability | `BLOCKED_CAPABILITY_MISSING`, zero jobs |
| R-02 | Fonte do binding não pertence à lista de fontes da recipe | falha da proveniência FP-045/F4; não promover |
| R-03 | Campo de medida sem `value/unit/origin` | `REFUSED/MISSING_*` antes do SketchUp |
| R-04 | Espessura/recuo inviáveis, NaN, infinito, zero ou negativo quando proibido | `REFUSED` com campo/código |
| R-05 | Largura/altura interna de painel não positiva | `INFEASIBLE_PANEL_OPENING` (PROPOSTO) |
| R-06 | Porta Shaker solicitada | nenhuma frente lisa sobreposta sob a Shaker; substituição no plano é explícita |
| R-07 | Painel central | geometria visível recuada fisicamente; não apenas material/cor |
| R-08 | Montantes/travessas | faces tocam sem volume compartilhado; travessas ficam entre montantes |
| R-09 | Mesmo pedido e entradas | mesmos IDs semânticos e assinatura lógica; mesma quantidade de peças |
| R-10 | Duas portas equivalentes | definições compartilhadas só se `role + dimensions + material + grain + geometry_signature` equivalentes |
| R-11 | Edição local de componente | `make_unique` antes de mudar geometria/definição; só propaga se pedido explícito |
| R-12 | Geometria/assinatura do plano adulterada | `require_valid` falha antes de qualquer job |
| R-13 | Material por peça | atribuição legível em inspector e consistente com plano |
| R-14 | `grain` sem UV comprovado | registrar `NOT_SUPPORTED`; não afirmar veio aplicado |
| R-15 | Fora de `runs/` ou saída já existe | negar ou reutilizar idempotentemente, nunca sobrescrever canônicos |
| R-16 | Reexecução com mesmo `request_id` | exatamente 1 gabinete raiz por request; nenhum componente duplicado |
| R-17 | Mudança visual sem Felipe | `PENDING_HUMAN`, sem veredito estético da IA |
| R-18 | Código/materializador alterado após L2 | evidência stale; reexecutar prova |
| R-19 | Frentes lisas existentes | mesmas caixas e assinatura da implementação antiga, para entradas antigas |
| R-20 | Pedido de ferragem, gaveta, UV, plano de corte | capability não coberta; bloqueio específico, nunca Shaker “equivalente” |
| R-21 | Alteração de arquitetura/âncora/porta ou colisão | bloquear via gates existentes |
| R-22 | Job SU falha / versão indisponível | status falha/`PENDING_SKETCHUP`, não L2_PASS |
| R-23 | Evidência de tutorial é transcrição/descrição sem inspeção | não afirmar que tutorial foi reproduzido visualmente |
| R-24 | Apenas CI Linux passou | no máximo L1_PASS; exigir Windows/SketchUp real para L2 |

**Decisão — estratégia do plano:**

| Caso | Resultado |
|---|---|
| Request `cabinet_request.v1` sem estilo | rota legada de frentes lisas, output antigo byte/semântica preservado |
| Request `shaker_door_request.v1` com geometria válida e capability ainda não implementada | `BLOCKED_CAPABILITY_MISSING` |
| Request Shaker com capability implementada mas sem validação L2 vigente | plano L1 permitido, execução/prova ficam bloqueadas ou explicitamente pendentes conforme gate da FP-045 |
| Request Shaker com capability+provas e gates verdes | materializar somente em cópia; inspeção L2 obrigatória |
| Request Shaker que também exige ferragens/UV/corte industrial não comprovados | bloquear necessidade específica, sem declarar completo |

**Matriz de responsabilidade:**

| Fonte de dado | Papel |
|---|---|
| Tutorial com provenance verificada | técnica/terminologia; **não** substitui dimensão do projeto |
| Pedido `value/unit/origin` | espessura, recuo, largura de montante, altura de travessa e materiais |
| `cabinet_request.v1` / moldura Shaker | envelope existente, convenção local, frente alvo |
| `shared.shaker` (PROPOSTO) | calcular geometria e atributos de peças |
| `kitchen.cabinet` | testar âncora hidráulica e restrições do cômodo |
| `sketchup`/Ruby | construir no SketchUp e permitir edição verificável |
| Felipe | aprovação estética L3 sobre renders da nova porta |

### 2.3 Componentes Impactados

| Caminho | Impacto | Detalhe |
|---|---|---|
| `references/sketchup/knowledge/video_recipes.v1.json` | AUDITAR, não elevar prova sem fonte | recipe Shaker e locator |
| `tools/rooms/capability_catalog.v1.json` | ADICIONAR sob prova | capability proposta `shared.cabinet.front.shaker`, binding `bind.kitchen.shaker` |
| `tools/rooms/capability_catalog.py` | VALIDAR | digests e vínculos de provas |
| `tools/rooms/kitchen/knowledge/index.v1.json` / `specialist.v1.json` | ATUALIZAR APÓS IMPLEMENTAÇÃO | recipe, capability e tool allowlist |
| `tools/rooms/shared/cabinet/model.py` | PRESERVAR | input legada sem defaults |
| `tools/rooms/shared/cabinet/assembly.py` | REUTILIZAR | quadro local, definições equivalentes |
| `tools/rooms/shared/cabinet/plan.py` | COMPATIBILIDADE | `cabinet_assembly_plan.v1` legado não deve aceitar plano de Shaker sem contrato |
| `tools/rooms/shared/cabinet/validation.py` | REUTILIZAR/COMPOR | colisões, envelopes, provas de recuo |
| `tools/rooms/shared/cabinet/sketchup.py` | ADAPTER VERSIONADO | job tipado + inspeção de vértices |
| `tools/rooms/shared/cabinet/ruby/cabinet_build.rb` | PROTEGER | aceita apenas `shared.cabinet.parametric` |
| **PROPOSTO** `tools/rooms/shared/cabinet/shaker/{model,plan,validation}.py` | CRIAR | capability parametrizada sem room dependency |
| **PROPOSTO** `tools/rooms/shared/cabinet/ruby/shaker_build.rb` | CRIAR | componente real e editável |
| `tools/rooms/kitchen/capabilities/{cabinet,cabinet_flow}.py` | INTEGRAR POR FASE | gates já existentes e proveniência |
| `tests/test_cabinet_plan.py`, `test_cabinet_sketchup_driver.py`, `test_kitchen_cabinet_flow.py` | MANTER | negativos e não regressão |
| **PROPOSTO** `tests/test_fp046_shaker_plan.py`, `tests/test_fp046_shaker_sketchup.py`, `tests/test_fp046_kitchen_flow.py` | CRIAR | TAAC completos |
| `docs/specs/fp042_inventory.v1.json` + `tools/rooms/ownership_audit.py` | ATUALIZAR/RODAR | owners e fronteiras |
| `tools/mcp_server/server.py` | NÃO ALTERAR NO MVP | 18 ferramentas existentes; tool nova exige spec/ADR própria |

### 2.4 Contratos de API

**Interfaces reais existentes**:
- `tools.rooms.shared.cabinet.plan.plan_cabinet(request)` → `cabinet_assembly_plan.v1` com `status=OK/REFUSED`.
- `tools.rooms.shared.cabinet.plan.require_valid(plan)` → plano íntegro ou `PlanRefused`.
- `tools.rooms.shared.cabinet.sketchup.materialize(plan,out_skp,base_skp=...,su=...)`; `inspect`; `verify`.
- `tools.rooms.kitchen.capabilities.cabinet.plan_kitchen_cabinet(consensus,room_id,request)` → quatro gates.
- `tools.rooms.kitchen.capabilities.cabinet_flow.run_request` → trace de request/job/idempotência.
- `tools.rooms.specialists.plan(request)` → `PLAN_READY_NOT_EXECUTED` ou `BLOCKED_*`, sem executar.
- `tools.mcp_server.server` → MCP stdio, não HTTP.

**Contrato NOVO proposto: `shaker_door_request.v1`**, independente dos campos de `cabinet_request.v1` para não quebrar a API antiga. Na P1 deve ser criado JSON Schema em `core/schemas/` e testes de compatibilidade. Exemplos de dimensões **sintéticas**, não padrão de fabricante:

```json
{
  "schema_version": "shaker_door_request.v1",
  "request_id": "shaker-fixture-001",
  "parent_cabinet_request_id": "synthetic-a",
  "target_front": "front",
  "style": "recessed_shaker",
  "frame": {
    "stile_width": {"value": 60, "unit": "mm", "origin": "user_request"},
    "rail_height": {"value": 60, "unit": "mm", "origin": "user_request"},
    "frame_thickness": {"value": 18, "unit": "mm", "origin": "user_request"}
  },
  "panel": {
    "thickness": {"value": 6, "unit": "mm", "origin": "user_request"},
    "recess_from_frame_front": {"value": 4, "unit": "mm", "origin": "user_request"}
  },
  "materials": {
    "frame": "mdf_branco",
    "panel": "mdf_branco"
  },
  "grain": {"frame": "none", "panel": "none"},
  "origin_context": {
    "recipe_id": "cabinet.recessed-shaker-and-louvers",
    "source_id": "yt-cabinet-styles-2024",
    "source_verified": false
  }
}
```

**Nota de implementação:** `source_verified=false` impede promoção pela evidência de vídeo; valores do exemplo nunca entram como defaults. A frente alvo vem do plano `synthetic-a` existente; não inventar largura/altura sem ele. `target_front` é ID semântico resolvido, não ponteiro Ruby livre. P1 decide se o schema de plano é `shaker_door_plan.v1` ou extensão explicitamente versionada de `cabinet_assembly_plan`; **não** converter silenciosamente o plano antigo.

**Saída planejada `shaker_door_plan.v1` (EXEMPLO DE PROPOSTA, não código existente):**

```json
{
  "schema_version": "shaker_door_plan.v1",
  "status": "OK",
  "request_id": "shaker-fixture-001",
  "capability": {"id": "shared.cabinet.front.shaker", "version": "1.0.0"},
  "parent_cabinet_request_id": "synthetic-a",
  "target_front": "front",
  "parts": [
    {"id": "shaker-fixture-001/stile_left", "role": "frame"},
    {"id": "shaker-fixture-001/stile_right", "role": "frame"},
    {"id": "shaker-fixture-001/rail_top", "role": "frame"},
    {"id": "shaker-fixture-001/rail_bottom", "role": "frame"},
    {"id": "shaker-fixture-001/recessed_panel", "role": "panel"}
  ],
  "geometry_reference": "local +x/+y/+z in meters",
  "frame_panel_recess_m": 0.004,
  "signature": "sha256_calculado_em_runtime",
  "execution_authorized": false,
  "visual": "NOT_REVIEWED"
}
```

O plano real exige `min_m/max_m`, material, grão, definição e assinatura verificável por peça; payload acima é ilustrativo e não pode ser aceito pelo materializador existente sem adaptação tipada.

#### 2.4.1 Pré-requisitos de infraestrutura

Python 3.11/3.12 (CI), SketchUp Windows local (L2, registrar versão real, baseline histórico 26.0.429), Ruby job seguro por PID, ambiente `interactive` de desenvolvimento, `PT_TO_M=0.0259` apenas no processo da planta real, fontes/recipes e catálogo, check `inventory_gate --strict`, quatro jobs de CI verdes. V-Ray para pacote visual somente se necessário; render simples suficiente para verificação L3 inicial. Sem fila, tópico, feature flag global nova ou serviço externo obrigatório.

### 2.5 Eventos e Mensageria

**N/A para Kafka, Avro, SQS, retry de broker e ACK manual.** O contrato vigente é execução local com trace JSON e manifesto. Não criar mensagens SQS fictícias.

#### 2.5.1 Entrada
`shaker_door_request.v1` acima chega por API Python interna / adapter validado, **não** por tópico. Para futuro MCP deve haver ADR separada.

#### 2.5.2 Saída
`shaker_door_plan.v1` proposta + `JobEvidence` derivado do trace real; exemplo de resultado de job futuro:

```json
{
  "schema_version": "shaker_job_evidence.v1",
  "request_id": "shaker-fixture-001",
  "state": "PENDING_SKETCHUP",
  "input_sha256": "calcular_no_runner",
  "capability_id": "shared.cabinet.front.shaker",
  "recipe_ids": ["cabinet.recessed-shaker-and-louvers"],
  "source_ids": ["yt-cabinet-styles-2024"],
  "base_skp_sha256": "calcular_no_runner",
  "output_skp": null,
  "output_skp_sha256": null,
  "validation": {"l1": "NOT_RUN", "l2": "PENDING_SKETCHUP", "l3": "NOT_REVIEWED"},
  "sketchup_version": null,
  "visual_review": "PENDING_HUMAN_IF_APPEARANCE_CHANGES"
}
```

**Todos os SHA em string são placeholders de schema de exemplo, não hashes certificados.**

#### 2.5.3 Retry
Mesma request/mesmos hashes → mesmo plano e resultado idempotente verificado; job interrompido → manifesto FAILED, nova tentativa explícita; código/source/fixture divergente → reexecutar validação, não reutilizar L2.

#### 2.5.4 Mensagens SQS
`N/A`. Manifesto local registra tentativa/erro; sem DLQ.

#### 2.5.5 ACK manual
`N/A`. “Sucesso” apenas após gravação, reabertura, inspeção e validação de output; falha em persistir manifesto impede estado final positivo.

### 2.6 Modelo de Dados

**Propostos:** `ShakerDoorRequest`, `ShakerDoorParams`, `ShakerPart`, `ShakerDoorPlan`, `ShakerProof`. Devem ser tipados e versionados; geometria canônica interna em metros, orientação de mundo pela pose existente; valores originais e unidades preservados para auditoria.

**Invariantes da submontagem (não transformar em desenho aproximado):**
- Envelope W×H da **frente existente** permanece; parte externa de montantes/travessas ocupa o envelope, com folga da porta preservada.
- Montantes laterais possuem largura `stile_width`; travessas entre montantes possuem altura `rail_height`; painel central cobre vão restante com espessura e recuo declarados.
- **Restrições de profundidade que a v1.0.0 omitia (conferidas em `assembly.build_parts`):** a frente lisa atual ocupa `y ∈ [D − front, D]` (`front` = `panels.front`) e `z ∈ [reveal, H − reveal]`; logo `frame_thickness` deve ser **igual** à espessura de frente do gabinete pai (`panels.front`) — maior invade a `front_clearance`/carcaça, menor deixa vão — e `recess_from_frame_front + panel.thickness ≤ frame_thickness`. No exemplo (18 mm / 4 mm / 6 mm) vale 4+6=10 ≤ 18. O plano da Shaker deve citar a **assinatura do plano pai** (`parent_plan_signature`) para não substituir uma frente de um plano já alterado (R-12).
- `frame_thickness > recess_from_frame_front >= 0` e painel atrás da face externa, dentro do envelope autorizado; condições exatas de profundidade derivadas de `panel.thickness`, sem intersectar ilicitamente outros sólidos.
- Contato de face é permitido; interseção volumétrica positiva entre partes não previstas é FAIL.
- Os papéis e chaves de material atuais são `ROLE_OF_PART`/`materials[role]` do gabinete pai (frente = `front`); `frame` e `panel` são papéis **novos** — o contrato deve declará-los (e `definitions()` já agrupa por `(role, size, material, grain)`), sem alterar `ROLE_OF_PART` das frentes lisas (R-19).
- `role`/`id`/`material`/`grain`/`geometry_signature` determinam compartilhamento; `make_unique` protege edição local.
- Assinatura liga schema, versão, frente alvo, materiais, espessuras, transforms e todos os bounds. Não incluir PID/timestamp no hash lógico.

### 2.7 Requisitos Não Funcionais

| ID | Requisito | Prova |
|---|---|---|
| RNF-01 | Segurança da origem | recipe/source coerentes; proveniência não inventada |
| RNF-02 | Determinismo | mesmos parâmetros geram os mesmos IDs e signature (sem timestamp/PID) |
| RNF-03 | Retrocompatibilidade | a `cabinet_request.v1` existente não altera output/peças/assinatura |
| RNF-04 | Editabilidade | componentes reais e `make_unique` comprovado após reabertura |
| RNF-05 | Resiliência | falha deixa canônico intacto, PIDs próprios, sem `taskkill /IM` |
| RNF-06 | Observabilidade | log/trace `request_id,room,recipe,capability,version,signature,job_id,pid,gates,sha` |
| RNF-07 | Honestidade da evidência | `CI != L2 != L3`; `grain=NOT_SUPPORTED` se não há UV |
| RNF-08 | Sem regressão | baterias antigas completas e hash do baseline |
| RNF-09 | Sem dependência cruzada | shared não depende de kitchen/bedroom; AST ownership gate |
| RNF-10 | Testes negativos | geometria inválida, recipe divergente, assinatura adulterada, arquitetura, PID externo |

### 2.8 Estratégia de Testes

#### 2.8.1 Unitários obrigatórios

| Suíte | Cenários |
|---|---|
| **PROPOSTO** `tests/test_fp046_shaker_plan.py` | medidas e origem; contagem 1/2; dimensões impossíveis; peças/hierarquia; topologia; setbacks reais; assinatura; idempotência |
| **PROPOSTO** `tests/test_fp046_shaker_sketchup.py` | fake SU, call order, `require_valid`, saída proibida, job fail, identidade, tag/material/definição/make_unique |
| **PROPOSTO** `tests/test_fp046_kitchen_flow.py` | routing, binding, allowlist, quatro gates, source stale, bloqueio Shaker antes do builder, trace |
| `tests/test_cabinet_plan.py` | planos antigos retornam resultados idênticos, regras de frentes lisas |
| `tests/test_cabinet_sketchup_driver.py` | continua a recusar outro schema/capability, L2 só com prova |
| `tests/test_kitchen_cabinet_flow.py` | idempotência, PID, negativos de arquitetura e shaker ausente até promoção |
| `tests/test_fp045_knowledge_provenance.py` | estender para vínculo `binding→recipe→source` e caso divergente real |

#### 2.8.2 Integração/E2E

**L1:** fixtures sintéticas novas `fixtures/synthetic_cabinets/fp046_shaker_*.json` para painel largo/estreito inválido, uma/duas portas, rotação 0/90/30, materiais distintos, alteração localizada. Check `inventory_gate --strict` após registrar cada fixture e arquivo novo. Rodar testes da escala `planta74_scale` em processo separado.

**L2:** SketchUp Windows real, não fake; para cada cenário aprovado: criar uma cópia nova, executar job, inspecionar volume real e componentes, fazer mudança de material e teste `make_unique`, salvar, fechar próprio PID, reabrir e provar igualdade com plano. Hash da base SKP antes/depois deve ser idêntico. Registrar SHA, Git commit, versão do SU, PID, log, contato/colisão, verificação de material e output.

**L3:** comparação frontal/top/iso contra porta lisa e contra a geometria descrita; somente Felipe aprova a aparência. Capturas não significam sucesso estético.

**WireMock/Testcontainers:** `N/A`; ausência de HTTP/broker.

#### 2.8.3 TAAC — Given / When / Then

| CA | Given | When | Then |
|---|---|---|---|
| CA-01 | recipe Shaker e binding atuais divergentes | rodar gate de fontes | FAIL com IDs/URLs implicados; corrigir após verificar fonte |
| CA-02 | pedido Shaker sem implementação | planejar | `BLOCKED_CAPABILITY_MISSING`, 0 jobs |
| CA-03 | input completo e válido | planejar | plano tipado com montantes, travessas e painel |
| CA-04 | falta `origin` | planejar | REFUSED antes do job |
| CA-05 | largura insuficiente para 2 montantes | planejar | erro de vão inviável |
| CA-06 | recuo maior que espaço geométrico disponível | planejar | erro e nenhum SKP |
| CA-07 | 1 frente Shaker | comparar geometria | exatamente 5 peças de submontagem (2 montantes, 2 travessas, 1 painel) e nenhuma frente lisa sobreposta |
| CA-08 | 2 frentes | comparar identidade | 2 submontagens sem colisões nem IDs duplicados |
| CA-09 | painel com setback declarado | medir coordenadas | face visível realmente atrás da moldura conforme medida |
| CA-10 | geometria validada | calcular hash | assinatura estável; outro parâmetro muda assinatura |
| CA-11 | plano adulterado | chamar materializador | `PlanRefused` antes de abrir SU |
| CA-12 | 0°/90°/30° | executar L2 | vértices do modelo reaberto equivalentes ao plano no erro máximo definido no verificador |
| CA-13 | componentes equivalentes | gerar SKP | definição compartilhada só quando equivalentes |
| CA-14 | editar só uma instância | `make_unique` | outra instância não muda |
| CA-15 | mesmo request no mesmo modelo | executar de novo | 1 grupo `Cabinet_<request_id>`, sem duplicatas |
| CA-16 | falha do job | consultar saída | FAILED, sem sucesso fantasma/canônico alterado |
| CA-17 | arquitetura/âncora pia afetada | adapter cozinha | gate falha antes de executar |
| CA-18 | alteração de Shaker e render novo | concluir L2 | `PENDING_HUMAN`, sem aprovar visual automaticamente |
| **CA-19** | fases P0–P6 entregues | executar suíte E2E completa e prova Windows real | 4 jobs CI verdes, micro-fixtures L2 rastreadas, reabertura/editabilidade, hashes intactos, status real de L3, sem fail/skip como PASS |
| CA-20 | request legado de frente lisa | executar suite existente | mesmo plano, IDs, geometria e assinatura legados |
| CA-21 | pedido de ferragens/UV | planejar | `BLOCKED_CAPABILITY_MISSING`/`NOT_SUPPORTED` explícito |
| CA-22 | símbolo alterado após prova | verificar capability | `BLOCKED_EVIDENCE_STALE` até nova L2 |
| CA-23 | outro cômodo importa shared | rodar ownership | sem `CROSS_ROOM_DEPENDENCY` |
| CA-24 | imagens e prova visual ausentes | fechar relatório | status parcial, nunca COMPLETE |

**CA-19:** registrar matriz fixture→teste→commit→hash→L1/L2/L3; evidência “Windows real” não pode ser substituída pelo fake `tests/test_cabinet_sketchup_driver.py`.

### 2.9 Estratégia de Lançamento

Cada P0–P6 é PR pequeno para `develop`, 4 checks aplicáveis verdes. P0 (fonte) fica na FP-045/F4 e não altera materialização. P1–P2 = pure Python sem SKP. P3 = micro-fixtures L2 Windows. P4 = adapter opt-in Shaker, sem alterar padrão de frente lisa. P5 = gates regressivos. P6 = relatórios, catálogo e pacote visual. Merge da fase técnica não confere aprovação estética.

**Rollback:** `git revert` de cada fatia, restaurando dados do catálogo e schemas compatíveis; descartar `runs/` do experimento, conferir `fp044_baseline compare` e SHA-256 de fonte/fixture/canônicos. Não substituir qualquer `artifacts/planta_74/*.skp`. Em alterações estruturais, backup local + hash; cópia em Downloads no Windows somente após confirmar integridade e informar falha quando indisponível. Não converter fixture sintética em referência canônica sem revisão.

### 2.10 ADRs vinculados

- `docs/specs/FP-045_specialists_knowledge_and_room_modularization.md` — capacidade, proveniência e L1/L2/L3.
- `docs/specs/FP-041_video_knowledge_consultation.md` — recipe de gabinete é consultiva, não execução automática.
- `docs/specs/FP-043_repository_navigation_and_room_specialists.md` — especialista/kitchen P5–P7.
- `docs/reports/FP-043_final_validation.md` — piloto de gabinete real.
- `docs/specs/FP-043_open_decisions.md` — preservar D-007/D-011 e decisões humanas.
- **ADR-046-01 (PROPOSTA):** extensão tipada de `cabinet_assembly_plan` versus `shaker_door_plan.v1` sem quebra de v1.
- **ADR-046-02 (PROPOSTA):** definições de componentes, compartilhamento, `make_unique` e representação do recuo real.

## 🔄 BLOCO 3 — Governança

### 3.1 Dúvidas resolvidas / pendentes

| ID | Estado | Decisão |
|---|---|---|
| D46-01 | RESOLVIDA | titular técnico da geometria = shared cabinet; cozinha é adapter |
| D46-02 | RESOLVIDA | começar por moldura+painel rebaixado; sem gaveta, ferragem, UV ou fabricação |
| D46-03 | RESOLVIDA | `cabinet_request.v1` e frentes lisas mantêm contrato atual |
| D46-04 | RESOLVIDA | observação de recuo depende de vértices/peças no SketchUp, não render bonito |
| D46-05 | RESOLVIDA (#345) | origem da recipe Shaker verificada: binding agora cita só o que a recipe cita |
| D46-09 | PENDENTE TÉCNICA + FELIPE | fonte *inspecionada* para o binding Shaker (ver 2.1); bloqueia só o P4 |
| D46-06 | PENDENTE TÉCNICA | ADR do versionamento do plano e Ruby job |
| D46-07 | PENDENTE FELIPE | aparência final e aceitação das proporções (valores sintéticos ≠ padrão) |
| D46-08 | PENDENTE TÉCNICA | integrar Shaker como opção sem modificar `cabinet_flow` legacy; provar compatibilidade |

### 3.2 Histórico de Versões

| Versão | Data | Autor | Descrição |
|---|---|---|---|
| 1.0.0 | 2026-10-21 | GPT-6 | SPEC executável P0–P6, Shaker compartilhado, 24 regras, 24 critérios e CA-19 |
| 1.1.0 | 2026-10-21 | Claude (validação contra o código) | Conferido: `quantity`, `Params`, `build_parts` (`front`/`front_N`, quadro local), `definitions`, `plan_cabinet/require_valid`, `cabinet_build.rb` aceita só `shared.cabinet.parametric`. Correções: (1) P0 entregue em #345 — eram 4 bindings, não 3; (2) nova pendência D46-09: binding Shaker só cita fonte descritiva e não pode ganhar capability sem fonte inspecionada; (3) restrições de profundidade ausentes (`frame_thickness == panels.front`, `recess + panel ≤ frame`); (4) `parent_plan_signature`; (5) papéis `frame`/`panel` novos; (6) baseline `23939d9` |

### 3.3 Handoff de implementação

1. `git fetch origin`, confirmar `develop` atual; se divergir do baseline acima, reconciliar antes de escrever código.
2. Corrigir o gap de proveniência FP-045 com negativo que falha na `develop` antiga; não forçar fonte sem evidência.
3. Ler `tools/rooms/shared/cabinet/{model,assembly,plan,validation,sketchup}.py` e `ruby/cabinet_build.rb`, além dos três testes legados; mapear qual contrato será estendido.
4. Implementar P1 como módulo puro de planejar e validar, com testes negativos em primeiro lugar. Não abrir SketchUp antes do plano íntegro.
5. Criar job Ruby com proteção de base/cópia/PID e, em Windows, provar editar/reabrir; não alegar L2 sem a máquina real.
6. Conectar `bind.kitchen.shaker` só após símbolos, allowlist, source e evidências consistentes; antes disso continuar bloqueando.
7. Rodar os quatro jobs de CI, ambas escalas em processos separados, provas por cômodo da FP-047 quando disponíveis; abrir PR pequeno para `develop`.
8. Manter status `PENDING_HUMAN` até veredito estético por commit/hash. Não abrir mudança em `main`.

## ✅ Checklist de Completude

**SPEC definida:**
- [x] Metadata e fonte real
- [x] Dentro/fora do escopo
- [x] Fases P0–P6
- [x] Arquitetura, pipeline e 24 regras
- [x] Componentes/contratos reais vs novos explicitamente propostos
- [x] JSONs com unidades/origens plausíveis e sem hashes fabricados
- [x] N/A explícito para Kafka/SQS/ACK/HTTP
- [x] NFRs, testes unitários, L1/L2/L3, CA-19 e rollback
- [x] Governança/handoff
- [ ] ADR de versionamento do plano aprovada

**Implementação — tudo pendente:**
- [x] P0 fonte Shaker/binding verificados e teste vermelho→verde (#345)
- [ ] P1 Schema + inputs completos, negativos e plano assinado
- [ ] P2 5 peças por frente, recuo real, sem overlap positivo
- [ ] P3 job SketchUp real e reabertura/editabilidade comprovada
- [ ] P4 roteamento/allowlist/kitchen gates preservados
- [ ] P5 regressão legada e geometria do apartamento não alteradas
- [ ] P6 comparação visual e aprovação humana quando cabível
- [ ] CA-19 e matriz final com CI+L2 e hashes
- [ ] Só marcar COMPLETE após os gates e decisões bloqueantes

**Estado:** SPEC em RASCUNHO, sem implementação autorizada por mera criação do documento.
