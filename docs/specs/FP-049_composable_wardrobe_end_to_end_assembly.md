# 📐 FP-049 — Guarda-Roupa Componível com Capabilities Compartilhadas
> SPEC SDD · sketchup-mcp · Python / Ruby / SketchUp Windows · Produto final a partir de habilidades validadas

## 🏷️ BLOCO 1 — Metadata

```yaml
spec:
  feature: "FP-049 — Guarda-roupa componível do pedido ao SKP editável"
  escopo_versao: "Compor caixaria, portas, prateleira, puxadores e elementos internos de guarda-roupa por capabilities compartilhadas, validando um móvel completo sem duplicar técnicas de outros cômodos."
  versao: "1.0.0"
  status: RASCUNHO
  classificacao:
    contexto_delimitado: "Composição de móveis paramétricos"
    dominio: "SketchUp MCP / Quarto / Closet"
    funcionalidade: "Assembly declarativa, dependency graph, execução L2, regressão FP-047"
  data_criacao: "2026-10-21"
  baseline_develop: "09bd668210e4f5c66c7a3400640b9df0f3005639"
  spec_pai: "FP-045"
  dependencias: ["FP-046 Shaker", "FP-047 regressão", "FP-048 shared geometry"]
  area_inicial: "bedroom; closet somente reuse/advisory até validação"
  destino: develop
```

### Motivação e diagnóstico real

A FP-046 comprova uma habilidade pequena (porta Shaker). A FP-048 separa operações e adapta os frames entre cômodos. **Esta feature prova composição**, sem virar um projeto que só cria peças isoladas.

O repositório já possui `tools/rooms/shared/wardrobe.py` com `build_wardrobe(WardrobeSpec)`, que retorna rodapé, corpo, N portas e puxadores em caixas, e `tools/rooms/shared/anatomy.py` com `WardrobeSpec`. `tools/rooms/bedroom/designer.py` escolhe e posiciona mobília no quarto; `tools/rooms/bedroom/validation/wardrobe_gate.py` valida o armário; o especialista bedroom possui capability `bedroom.wardrobe.build`; o closet é `role=reuse` do quarto com allowlist vazia. Esses providers **não demonstram por si só** um móvel complexo composto de componentes independentes, plenamente editáveis e reabertos em um SketchUp real.

Há dois frames distintos: `wardrobe.py` usa frente **−Y** e `cabinet/assembly.py` usa frente **+Y**. A composição não deve inverter portas/puxadores. O problema D-007 da fixture sintética de guarda-roupa penetrando a parede em ~4,5 cm continua bloqueante para aplicar correção global de posicionamento sem a FP-047 e revisão da SUITE 02.

O modelo inicial da FP-049 deve ter uma estrutura externa e módulos internos úteis e editáveis, não uma caixa única pintada para parecer armário. **Não presumir** que gavetas, trilhos, portas de correr, ferragens reais ou UV existem só porque o catálogo possui recipes.

## 📐 BLOCO 2 — Especificação Técnica

### 2.1 Objetivo, não objetivos e fases

**Objetivo único:** gerar um guarda-roupa de abrir, parametrizado, editável, rastreado da request ao arquivo SketchUp reaberto, composto exclusivamente de capacidades comprovadas; nenhuma camada nova reimplementa porta Shaker ou peças já disponíveis em shared.

**MVP positivo:** corpo com laterais/tampo/base/fundo, plinto/rodapé recuado, divisórias internas quando requisitadas, ao menos uma prateleira, 2 frentes de abrir com folgas, puxadores e materiais por papel; *opcional* Shaker somente depois da FP-046 comprovada e adaptada ao frame -Y. Porta plana legada deve continuar possível sem mudança no contrato antigo. Abertura dinâmica em arco não é prova de dobradiça/ferragem funcional; gate de giro usa envelope matemático conservador, sem prometer mecanismo físico implementado.

**Fora:** correr/rails, gavetas de caixa/corrediças, dobradiças detalhadas/física dinâmica, iluminação elétrica, fábrica/CNC/BOM industrial, mudança no consensus/PDF/SUITE 02, produção automática em SKP canônico, multi-ambiente final antes do piloto.

| Fase | Escopo | Evidência |
|---|---|---|
| F0 | Atualizar develop e pré-requisitos, mapear existing wardrobe vs cabinet | lista de abilities implementadas, ausentes, testes, frames |
| F1 | `furniture_assembly_request.v1` e `assembly_plan.v1` | schema/negativos/sem defaults/integridade |
| F2 | Resolver DAG de capabilities e dependencies | seleção fail-closed e binding de cada peça |
| F3 | Gerar estrutura e interior com primitives shared | partes semânticas, colisões, espaçamentos e editabilidade |
| F4 | Reutilizar frente plana e Shaker se provada | um único produtor por tipo, adapter frame, não duplicação |
| F5 | Integrar bedroom e closet advisory | gates de quarto + colocação, sem declarar closet executor |
| F6 | Executar fluxo Windows SketchUp real | .skp novo, save/reopen, edits, prova de componentes |
| F7 | FP-047, controle D-007, visual e relatório CA-19 | sem delta não autorizado; L3 humano se aparência mudar |

**Precondições:** FP-048 F2 (frames) antes de importar Shaker na montagem; FP-047 F2/F3 antes de alterar posição real de móvel; FP-046 L2 atual para declarar Shaker pronta. Se não cumpridas, implementar plano consultivo L1 e bloquear etapas dependentes com `BLOCKED_DEPENDENCY`, sem criar substituição escondida.

### 2.2 Arquitetura

```text
Pedido: "guarda-roupa 2 portas, uma prateleira, acabamento definido"
 -> registry + bedroom specialist advisory
 -> recipe/binding/source -> capability catalog [prova]
 -> PROPOSTO: furniture.assembly dependency resolver (DAG puro)
      -> shared wardrobe anatomy / existing wardrobe spec
      -> shared cabinet carcass/panels where compatible
      -> FP-046 Shaker [optional; blocked until proven]
      -> shared transforms FP-048 (+Y/-Y)
      -> shared material/instance semantics
 -> PROPOSTO: furniture assembly validator
 -> bedroom gates: clearance, janela, porta, arquitetura, circulação
 -> SketchUp tool allowlist / copy save -> inspect -> versioned manifest
 -> FP-047 regression -> visual human if changed
```

**Owner:** montagem genérica em `tools/rooms/shared/assembly/` (PROPOSTO). Bedroom adapter em `tools/rooms/bedroom/capabilities/` (PROPOSTO). Closet reuse mantém consultivo; quando uma futura spec tiver executor independente, deve comprovar perfil, allowlist, recipe/capability e gates próprios. Nenhum import de bedroom dentro de shared.

#### 2.2.1 Pipeline obrigatório

1. Resolver projeto/ambiente por `tools.rooms.registry` e `core.domain.room_registry`, sem mudar arquitetura.
2. Ler constraints de origem PDF/consensus; pedido de medidas com `value/unit/origin`, incluindo altura/largura/profundidade, painéis, folga de frentes, recuo, prateleiras.
3. Carregar receita e capabilities **disponíveis**; construir DAG de peças/capabilities versionadas; relatório mostra implementadas vs bloqueadas, sem autorizar execução por catálogo.
4. Se Shaker solicitada, exigir a mesma capability FP-046 com prova e digest válido. Não substituir automaticamente por porta lisa, nem criar um segundo Shaker em bedroom.
5. Se gavetas/trilhos/portas de correr solicitados e sem builder/prova, devolver gaps específicos; opcionalmente planejar parte suportada apenas com consentimento explícito de escopo reduzido.
6. Converter frames de qualquer componente usando FP-048; validar face externa, posição de puxador, dobradiça conceitual e distâncias, sem espelho acidental.
7. Criar hierarquia de componentes: `Wardrobe_<request_id>` raiz, `carcass`, `interior`, `fronts`, `hardware_placeholder` (o último é visual/proporção, não ferragem funcional).
8. Montar peças reais editáveis com IDs semânticos e envelopes. Corpo não pode ser caixa sólida única ocupando todo interior útil.
9. Validar topologia do móvel: paredes de painel, vão real, folgas, profundidade, portas sem se atravessar e prateleira dentro do volume útil.
10. Validar acesso e interferência por portas de abrir com envelope de giro calculado (sem alegar animação/hinge real); aplicar o `wardrobe_gate`/circulação/parede/janela do bedroom sem tolerância nova para D-007.
11. Gerar `assembly_plan.v1` com signature SHA e `require_valid` equivalente, sem I/O ou SketchUp.
12. Registrar idempotência por request/base/consensus/capabilities/versões, sem timestamps no hash lógico.
13. Materializar apenas em cópia nova por ferramenta allowlisted; rejeitar path em fixtures/artifacts protegidos ou arquivo existente.
14. Salvar, fechar PID próprio, reabrir e medir componentes reais/instâncias/materiais/bounds; comparar cada part ID ao plano.
15. Editar uma porta em separado via `make_unique`, comprovar que outra não muda e save/reopen; registrar material e estado de UV honestamente.
16. Rodar FP-047 `scoped_change` e controlar SUITE 02, cozinha e demais rooms conforme política; se D-007 bloquear posicionamento real, permanecer na micro-fixture.
17. Empacotar vistas frontal/top/iso e comparativo com baseline; `PENDING_HUMAN` para alterações estéticas da planta real.
18. Registrar trace `request -> recipe -> capabilities -> parts -> gates -> job -> inspect -> regression -> visual` e matrix CA-19.

#### 2.2.2 Regras numeradas

| Regra | Condição | Resultado |
|---|---|---|
| R-01 | capability requerida ainda PLANNED | `BLOCKED_CAPABILITY_MISSING` |
| R-02 | dependência FP-046/048 incompleta | `BLOCKED_DEPENDENCY`, sem fallback |
| R-03 | pedir guarda-roupa “Shaker” | importar UMA capability shared FP-046, não reimplementar |
| R-04 | frente lisa explicitamente requisitada | fluxo antigo continua suportado |
| R-05 | dimensão sem value/unit/origin | recusar antes de job |
| R-06 | altura/profundidade incompatíveis com painéis | plano recusado |
| R-07 | parte interna não possui volume útil | FAIL geometria |
| R-08 | caixaria emitida como único cubo sólido | FAIL composição semântica |
| R-09 | prateleira extravasa os painéis ou corta porta | FAIL |
| R-10 | puxador na face de trás por frame invertido | FAIL |
| R-11 | mistura +Y/-Y sem transformada provada | bloquear |
| R-12 | duas portas se sobrepõem em posição fechada | FAIL |
| R-13 | giro/interferência com outros objetos | bloquear com envelope e motivo |
| R-14 | wardrobe entra em parede/janela/portal | FAIL gates existentes |
| R-15 | fixture D-007 de ~4,5 cm | manter teste negativo e estado visível |
| R-16 | mexer SUITE 02 por correção sintética | exigir FP-047 e review de Felipe |
| R-17 | material/grain declarado | aplicar o suportado, registrar NOT_SUPPORTED para UV não comprovado |
| R-18 | duas portas equivalentes | definitions iguais somente sob fingerprint idêntico |
| R-19 | modificar porta A | `make_unique`; B permanece |
| R-20 | mesma request | idempotência, grupo raiz único |
| R-21 | alterações fora do wardrobe autorizado | regressão FP-047 FAIL |
| R-22 | base .skp/consensus/PDF mudou | FAIL sem baseline automático |
| R-23 | job Windows não rodou | L2 `PENDING_SKETCHUP` |
| R-24 | estética sem decisão humana | `PENDING_HUMAN` |
| R-25 | closet sem allowlist executora | advisory e bloqueio real |
| R-26 | tentar drawer/sliding sem capability | não gerar falsa funcionalidade |
| R-27 | componente não editável/duplicado após reabertura | FAILED_L2 |
| R-28 | símbolo ou source mudou depois da prova | EVIDENCE_STALE, reexecutar |

### 2.3 Componentes Impactados

| Path | Responsabilidade |
|---|---|
| `tools/rooms/shared/wardrobe.py` | `build_wardrobe` legado, preservar outputs; extrair apenas com testes |
| `tools/rooms/shared/anatomy.py` | `WardrobeSpec` atual, sem alterar defaults históricos |
| `tools/rooms/shared/cabinet/{assembly,model,plan,validation,sketchup}.py` | fornecedor da caixaria e da prova de SKP, schema v1 preservado |
| `tools/rooms/shared/geometry.py` e FP-048 | transform, frame, part, positioning sem duplicação |
| `tools/rooms/shared/materials.py` | acabamento por papéis, sem afirmar UV ausente |
| `tools/rooms/bedroom/designer.py` | layout quarto; não alterar footprint real até gates |
| `tools/rooms/bedroom/validation/wardrobe_gate.py` | validar interferências e constraints |
| `tools/rooms/bedroom/specialist.v1.json` | perfil/allowlist somente com símbolos/provas |
| `tools/rooms/closet/specialist.v1.json` | permanece reuse/advisory no MVP |
| `tools/rooms/capability_catalog.v1.json` e `capability_catalog.py` | DAG de capacidade/prova/digests/estado |
| `tools/rooms/specialists.py` | roteamento advisory, sem execução implícita |
| `tools/validation/room_collisions.py` e FP-047 | regresso cross-room |
| **PROPOSTO** `tools/rooms/shared/assembly/{model,planner,validator}.py` | composição pura, DAG e assinatura |
| **PROPOSTO** `tools/rooms/shared/assembly/sketchup.py` | adapter seguro de job/inspector |
| **PROPOSTO** `core/schemas/furniture_assembly_request.v1.schema.json` | input tipada e origem |
| **PROPOSTO** `core/schemas/furniture_assembly_plan.v1.schema.json` | output e dependency graph |
| **PROPOSTO** `tests/test_fp049_assembly_plan.py` | fixtures + negativos de DAG/geometria |
| **PROPOSTO** `tests/test_fp049_sketchup.py` | driver fake e, separadamente, Windows L2 |
| **PROPOSTO** `tests/test_fp049_room_integration.py` | bedroom/closet, FP-047 e controle |
| `docs/specs/fp042_inventory.v1.json` | inventariar novos arquivos |

### 2.4 Contratos de API

**API PROPOSTA, não existe na develop:**

```json
{
  "schema_version": "furniture_assembly_request.v1",
  "request_id": "wardrobe-synthetic-001",
  "project_id": "synthetic_rooms",
  "room": "bedroom",
  "type": "hinged_wardrobe",
  "dimensions": {
    "width": {"value": 1800, "unit": "mm", "origin": "user_request"},
    "depth": {"value": 600, "unit": "mm", "origin": "user_request"},
    "height": {"value": 2400, "unit": "mm", "origin": "user_request"}
  },
  "panels": {
    "thickness": {"value": 18, "unit": "mm", "origin": "user_request"},
    "back_thickness": {"value": 6, "unit": "mm", "origin": "user_request"}
  },
  "plinth": {
    "height": {"value": 80, "unit": "mm", "origin": "user_request"},
    "recess": {"value": 35, "unit": "mm", "origin": "user_request"}
  },
  "fronts": {
    "type": "plain",
    "count": 2,
    "gap": {"value": 3, "unit": "mm", "origin": "user_request"}
  },
  "interior": {"shelf_count": 1, "hanging_rail": false, "drawers": 0},
  "materials": {"carcass": "mdf_sintetico", "back": "hdf_sintetico", "front": "mdf_sintetico", "hardware_placeholder": "metal_sintetico"},
  "pose": {"x": {"value": 1, "unit": "m", "origin": "user_request"},
           "y": {"value": 1, "unit": "m", "origin": "user_request"},
           "z": {"value": 0, "unit": "m", "origin": "user_request"},
           "rotation_deg": {"value": 0, "unit": "deg", "origin": "user_request"}},
  "execution_authorized": false
}
```

**Os valores são apenas fixture sintética, nunca tamanhos padrão inferidos para o apartamento.** Corrediças/rails não estão solicitados no MVP. Um pedido `fronts.type=shaker` exige contrato da FP-046 e parâmetros próprios, sem converter automaticamente valores para proporções Shaker. Hanging rod é opcional e **false** até capability/prova separada; se true sem capacidade, BLOCKED.

`furniture_assembly_plan.v1` proposto inclui `status`, `findings[]`, `assembly_id`, `parts[]` com ID/role/parent/bounds/material/grain/frame, `capabilities[]` com id/version/state/digest/source/recipe e dependency DAG ordenado, `gates[]`, `signature`, `execution_authorized=false`, `visual=NOT_REVIEWED`. Uma etapa separada autoriza job somente após o plano validado e allowlist.

**Erros novos PROPOSTOS:** `MISSING_CAPABILITY`, `BLOCKED_DEPENDENCY`, `FRAME_MISMATCH`, `NON_POSITIVE_INNER_VOLUME`, `PART_OUTSIDE_ASSEMBLY`, `UNSUPPORTED_FRONT_TYPE`, `WARDROBE_SWING_COLLISION`, `ASSEMBLY_SIGNATURE_MISMATCH`, `EDIT_ISOLATION_FAILED`.

**Não confundir:** `WardrobeSpec` legado não recebe este JSON diretamente; construir adapter/versionamento sem alterar o contrato anterior. O materializador `cabinet_build.rb` aceita somente capability legada de cabinet; não lhe passar `furniture_assembly_plan.v1` sem materializador validado.

### 2.5 Eventos, Mensageria e Idempotência

Sem Kafka/SQS/HTTP/Avro/ACK/DLQ nesta SPEC. Pipeline local em Python/Ruby + manifesto JSON. Chave de idempotência composta de request canônica, source/recipe/capability digests, base SKP/consensus e assinatura do plano. PID e timestamp não entram no hash lógico. Interrupção de job → FAILED, não declarar DONE_L2_VERIFIED ou deixar cópia não editada parecendo final.

### 2.6 Modelo e Invariantes

- `Assembly` tem raiz única, subgrupos (carcass/interior/fronts/hardware_visual), hierarquia de IDs e peça semanticamente nomeada.
- Cada componente tem volume/bounds/material/role e fonte. Nenhuma peça pode simplesmente copiar toda a caixa externa para “simular” o móvel.
- Travessas, laterais, fundo, prateleira e portas têm contato de face permitido, nunca intersecção volumétrica positiva não prevista.
- Frente de abrir deve ter eixo/normal corretos, abertura geométrica livre e gap parametrizado; “dobradiça dinâmica funciona” NÃO é alegação desta entrega.
- Compartilhar definição exige igualdade de geometria/material/role; `make_unique` isola edição.
- Portas, gavetas e recortes não implementados não viram pass por maquiagem visual.
- A geometria resultante e o papel do objeto têm verificação L1, inspeção L2 do SKP reaberto e revisão L3 separada.

### 2.7 RNFs

| ID | Exigência | Evidência |
|---|---|---|
| RNF-01 | peça realmente editável | instância/definition após reopen |
| RNF-02 | no duplicate implementation | import das capabilities shared |
| RNF-03 | determinação/identidade | part IDs e sha estáveis |
| RNF-04 | compatibilidade | testes de WardrobeSpec e gabinete legados |
| RNF-05 | segurança arquitetônica | gates bedroom e FP-047 |
| RNF-06 | proveniência | recipes, symbols, fixture e commits |
| RNF-07 | tolerância honesta | valores do validator atual; D-007 visível |
| RNF-08 | segurança local | work copy, PID próprio, no overwrite |
| RNF-09 | visibilidade de limitações | sliding/drawer/UV/hardware sem alegação falsa |
| RNF-10 | estética humana | revisão por Felipe e hashes por variante |

### 2.8 Plano de testes e TAAC

**L1:** fixture pequena de closet/bedroom sintética com 2 portas plain e uma prateleira, casos negativos de altura baixa, fundo para fora, folga negativa, um segundo interior inválido, frame espelhado, peça duplicada, origem ausente, DAG circular, Shaker PLANNED, sliding/rails solicitados, porta abrindo contra parede. Sem mutar modelo.

**L2 Windows real:** construir SKP novo, reabrir, inspecionar parte por parte e executar alteração localizada numa porta. Confirmar painel/paredes, recuos, componentes e nenhuma mudança na outra porta. Capturar SHAs, versão SU, PID, logs, raiz única e diferenças plano×inspeção. Ao montar em planta real, FP-047 e D-007 exigem controle da SUITE 02; sem isso, ficar só na fixture.

**L3:** pacote frontal/top/iso com câmera igual, aprovação de Felipe apenas nas mudanças de aparência do apartamento, registro versionado/hash. Não contar render automático como aprovação.

| CA | Given | When | Then |
|---|---|---|---|
| CA-01 | WardrobeSpec legado | executar regressão | outputs anteriores iguais |
| CA-02 | source/capability ausente | montar DAG | bloqueio tipado |
| CA-03 | Shaker não comprovada | solicitar frente Shaker | bloquear, sem plano falso de front lisa |
| CA-04 | 2 portas planas | planejar | duas partes de frente sem overlap |
| CA-05 | uma prateleira | planejar | peça separada no interior útil |
| CA-06 | altura/espessura impossível | validar | REFUSED |
| CA-07 | unit/origin ausentes | validar | REFUSED antes de SketchUp |
| CA-08 | modelo virou cubo único | validar semântica | FAIL |
| CA-09 | frame de frente espelhado | comparar | FAIL |
| CA-10 | puxador na face errada | comparar | FAIL |
| CA-11 | roda com posição em parede | gates quarto | FAIL |
| CA-12 | colide com giro de porta do quarto | gates | FAIL |
| CA-13 | duas portas iguais | materializar | definitions compartilhadas quando equivalentes |
| CA-14 | editar porta A | make_unique, save/reopen | porta B não muda |
| CA-15 | mesma request | reexecutar | 1 raiz, sem peças duplicadas |
| CA-16 | código/symbol mudou pós-prova | catalog verify | evidence stale |
| CA-17 | closet sem allowlist | solicitar SKP | advisory e BLOCKED |
| CA-18 | D-007 ainda falhando na sintética | regressão | xfail(strict)/falha visível, não “resolvido” |
| **CA-19** | fases F0–F7 concluídas | rodar suite CI+Windows e FP-047 | 4 checks verdes, geometria por peça L2, SKP reaberto/editável, hashes canônicos intactos, regressões cross-room e L3 humano se requerido; sem isso PARTIAL |
| CA-20 | SU job morre | consultar output | FAILED, original intocado |
| CA-21 | receita de drawer sem capability | request inclui drawer | bloquear (não gaveta pintada) |
| CA-22 | pedido sliding closet | route | bloqueio, não fingir mecanismo |
| CA-23 | UV grain não implementado | reportar | NOT_SUPPORTED explícito |
| CA-24 | Shaker FP-046 válida após merge | adapter para wardrobe | reutilizar o MESMO builder e verificar frame/normal |
| CA-25 | FP-047 flag unauthorized delta | tentar promover | FAIL e rollback |
| CA-26 | imagem nova, sem Felipe | marcar L3 | PENDING_HUMAN |
| CA-27 | mesma fixture input | gerar plano duas vezes | partes, assinatura e DAG determinísticos |
| CA-28 | pedido sem room legítimo | planejar | bloquear, não aplicar suíte padrão |

**Suite operacional:** inventário `python -m tools.rooms.inventory_gate --strict`; ownership `python -m tools.rooms.ownership_audit`; catalog `python -m tools.rooms.capability_catalog`; smoke/stdio MCP; `pytest -m "not planta74_scale"` e `PT_TO_M=0.0259 pytest -m planta74_scale` em processos separados; gates quadrado/planta_74 no caminho real do `ci.yml` após #343. Verificar 4 checks completos e reportar quaisquer skips, xfails e L2 pendentes.

### 2.9 Lançamento e Rollback

F0/F1 primeiro sem SketchUp e sem mexer em builders existentes. F2/F3 planos puros, testes vermelhos→verdes. F4 shared Shaker somente quando FP-046 com L2. F5 adapter bedroom e testes. F6 Windows SKP novo. F7 regressões FP-047, D-007 e pacote visual. Um PR pequeno por fase para develop; atualizar `fp042_inventory.v1.json` por arquivo. Evitar competir com branches FP-046/047/048 em desenvolvimento.

Rollback por `git revert` de cada fase; manter `WardrobeSpec`/cabinet legados compatíveis, invalidar provas stale, nunca editar `artifacts/planta_74/*.skp` nem `fixtures`/PDF protegidos. Saídas experimentais em `runs/`, com manifestos.

**ADRs propostas:**
- ADR-049-01: DAG de capabilities e bloqueio de dependências incompletas.
- ADR-049-02: raiz do wardrobe editável, política de definitions e submontagens.
- ADR-049-03: interpretação de porta de abrir e envelope de giro sem alegar ferragem funcional.
- ADR-049-04: adaptação para closet reuse sem executor independente.

## 🔄 BLOCO 3 — Governança

| Decisão | Estado |
|---|---|
| D49-01 reutilizar builder Shaker existente, não implementar outro | RESOLVIDA |
| D49-02 portas de abrir como MVP, não sliding/drawers | RESOLVIDA |
| D49-03 separar “móvel completo” de uma caixa sólida | RESOLVIDA |
| D49-04 integrar Shaker só depois da FP-046/048 | PENDENTE DEPENDÊNCIA |
| D49-05 FP-047 e D-007 antes de alterar SUITE 02 | PENDENTE DEPENDÊNCIA |
| D49-06 envelope de giro e modelagem de puxadores | PENDENTE TÉCNICA |
| D49-07 aparência final do guarda-roupa na planta | PENDENTE FELIPE |

**Handoff para Claude:** confirmar HEAD/progresso das FP-045 a FP-048; iniciar F0 com inventário de capacidades e lacunas; implementar planos/negativos primeiro; nunca copiar Shaker/drawer; usar micro-fixture editável em SketchUp Windows com reabertura; deixar integração na SUITE 02 bloqueada sem FP-047 e julgamento humano; abrir PR pequeno por fase, CI e hashes, registrar CA-19 final.

**Checklist:** [x] metadata; [x] escopo e fases F0–F7; [x] arquitetura/DAG; [x] 28 regras; [x] componentes/contratos propostos; [x] modelo/NFRs; [x] 28 CAs incluindo CA-19; [x] L1/L2/L3, negativos, rollout/rollback, ADRs e handoff. [ ] Implementação: pendente. **A SPEC não é prova nem aprovação estética do móvel.**
