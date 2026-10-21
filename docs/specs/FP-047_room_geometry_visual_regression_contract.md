# 📐 SPEC de Feature — FP-047: Contrato de Regressão Geométrica e Visual por Cômodo
> Fluxo de Desenvolvimento Agêntico (SDD) · sketchup-mcp · Python / SketchUp Windows / revisão humana

## 🏷️ BLOCO 1 — Metadata

```yaml
spec:
  feature: "FP-047 — Regressão geométrica e visual com isolamento de cômodos"
  escopo_versao: "Distinguir refatoração de alteração funcional autorizada e bloquear regressões arquitetônicas, geométricas e visuais fora do escopo de cada PR."
  versao: "1.0.0"
  status: "RASCUNHO"
  classificacao:
    contexto_delimitado: "Fidelidade e Validação de Modelagem"
    dominio: "SketchUp MCP / validação cross-room / evidências L1-L2-L3"
    funcionalidade: "baseline tipado, delta por cômodo, colisões, SKP real, revisão visual"
  autor: "GPT-6 (proposta SDD); aprovação estética e decisões de referência: Felipe"
  data_criacao: "2026-10-21"
  ultima_atualizacao: "2026-10-21"
  baseline_develop: "214d73e3c38c8bae9a3dc16f0fc579b64a017ac7"
  spec_mae: "docs/specs/FP-045_specialists_knowledge_and_room_modularization.md"
  spec_relacionada: "FP-046 — Porta Shaker Paramétrica"
  entrega_por: "PRs pequenos na develop"
```

**Nota de escopo:** esta SPEC não “corrige tudo” do apartamento. Cria um **contrato de regressão executável** para toda mudança de geometria, com comparação por cômodo, controle de alterações legítimas, proteção de referências e revisão visual humana. Qualquer defeito de geometria encontrado deve ser corrigido no módulo dono por PR separado (ou em fatia delimitada), preservando o baseline factual.

**Dentro:** classificar PR, capturar baseline, diferenciar mudança proibida de mudança autorizada, comparar caixas por cômodo e metadados, revalidar arquitetura/parede/giro/circulação, inspecionar SketchUp real, organizar pacote visual e decisões humanas, provas por commit/hashes, sabotagens, regressões de técnicas novas FP-046.

**Fora:** alterar automaticamente PDF, consensus, fixtures e canônicos; fabricar avaliação estética; redesenhar SUITE 02, cozinha ou apartamento; refazer `tools.validation.room_collisions.audit` do zero; substituir o inspector SketchUp atual; criar algoritmo novo de layout fora do owner; corrigir o D-001 (quadrado) sem decisão; integrar ferramentas externas de imagem ou filas. Não usar tolerância “relaxada” para mascarar um achado.

## 📐 BLOCO 2 — Especificação Técnica

### 2.1 Resumo da Feature

**Objetivo único:** provar, de forma reproduzível, que uma mudança altera **somente os elementos autorizados** e não viola arquitetura/parede/porta/circulação, mantendo separados L1 (planejamento), L2 (arquivo SketchUp salvo e reaberto) e L3 (revisão estética humana).

**O que já existe (não reimplementar):**

| Elemento | Fonte real / prova | Limite |
|---|---|---|
| Hash por cômodo + SHA dos canônicos | `tools.validation.fp044_baseline.capture/compare` | compara **saída idêntica**: útil para refatoração, não aceita mudança funcional intencional |
| Colisões de planejador | `tools.validation.room_collisions.audit/findings` | `FURNITURE/FIXTURE` x paredes, `DECORATIVE` no giro; categorias específicas |
| Footprint e portas | `tools.rooms.shared.clearance.{box_footprint_pt,wall_mass_pt,door_swings_pt}` | geometria/conversões já utilizadas no L1 |
| Circulação | `tools.validation.circulation_gate.gate` | check por room ID com entradas do consensus |
| Gate de fidelidade geral | `tools.validation.run_deterministic_gates` / CLI `tools.run_deterministic_gates` | contrato vigente para planta_74/quadrado |
| Executor e inspeção reais | `tools.sketchup.jobs`, `tools.mcp_server.server`: `su_build_shell/su_furnish/su_inspect` | CI Linux não abre SketchUp; L2 Windows é outra prova |
| Montagens visuais | `tools.validation.visual_regression_gate.build_montage` | produz imagem de comparação, não veredito humano |
| Oracle/visão | `tools.oracle.run_skp_visual_review` | consultivo; IA não aprova estética do Felipe |
| Prova FP-043 P8 / FP-044 F7 | `docs/reports/FP-043_final_validation.md` / `FP-044_final_validation.md` | SketchUp 26.0.429; 402/402 peças, erro máx. 0,05 mm naquele build, 0 mobília/fixture/decor em parede/giro (segundo relatório) |
| D-007 | `docs/specs/FP-043_open_decisions.md` e PR #338 | guarda-roupa sintético invade parede ~4,5 cm; solução tentada modifica SUITE 02 |
| CI vigente | head `214d73e` — `ci` concluído `success` | quatro checks; não é L2 nem L3 |

**Regra central:** `strict_identity` para refatoração/movimento de arquivos; `scoped_change` para evolução funcional. Em `scoped_change`, apenas as peças autorizadas mudam e **todos** os invariantes globais e de cômodos-controle continuam válidos. Não converter um hash diferente em “PASS porque alterou apenas a suíte”: verificar o delta semântico, o gate real e o visual.

**Fases:**

| Fase | Entrega | Critério de saída |
|---|---|---|
| F0 | Snapshot reprodutível e taxonomia de mudanças | hashes, fontes e ownership atuais |
| F1 | Contrato `room_regression_request.v1` e relatório `.v1` | schema de dois modos, teste de schema e negativos |
| F2 | Motor L1 de diff semântico por room e layer | prova de positivos/negativos, tolerâncias explícitas, `xfail` honestos |
| F3 | Integração com gates de parede/giro/circulação/arquitetura | controles cruzados e fail-closed |
| F4 | Piloto D-007 (diagnóstico e simulação), sem alterar canônicos | antes/depois SUITE 02 + sintéticas, package para Felipe |
| F5 | Inspeção L2 no SketchUp Windows | reabrir saída, comparar geometria, tags, objetos e hash base |
| F6 | Pacote L3 e veredito humano versionado | antes/depois render, hash, estado `PENDING_HUMAN` ou decisão válida |
| F7 | Integração como gate condicional da FP-046 e próximos PRs | política de modo/escopo comprovada no CI, não autoaprovar |
| F8 | Relatório, dashboards simples e fechamento | CA-19 completo e lacunas separadas |

### 2.2 Arquitetura de Solução

```text
origin/develop / candidate commit + PDF/consensus/fixtures
  -> tools.validation.fp044_baseline (hash de boxes e canônicos)
  -> PROPOSTO: tools.validation.room_regression.capture + compare
      -> diff estruturado de boxes por room / layers / intent
      -> tools.validation.room_collisions.audit (parede + arco)
      -> tools.validation.circulation_gate.gate (por room)
      -> tools.validation.*_gate existentes para shell/fidelidade
      -> report L1: PASS / FAIL / BLOCKED / PENDING_L2
  -> job SketchUp seguro (PID próprio, SKP novo, não canônico)
      -> su_inspect + medidas SKP realmente reaberto
      -> report L2 por cômodo (pass/fail/skip explícito)
  -> visual_regression_gate.build_montage + vistas
      -> VISUAL_REVIEW de Felipe (humano, por hash)
      -> report L3: APPROVED / REJECTED / PENDING_HUMAN
  -> entrega do PR (CA-19 + links + rollback)
```

**Arquitetura de ownership:** módulo novo em `tools/validation/room_regression.py` (PROPOSTO), consumidores em `tools/orchestration/` se necessário. Não criar lógica de validação na cozinha ou nos quartos; manter `tools/rooms/shared/clearance.py` como primitiva comum. FP-047 valida os builders de sala/bedroom/kitchen/bathroom/service sem dependência inversa dos cômodos para o novo gate.

#### 2.2.1 Pipeline obrigatório

1. Ler commit-base e commit-candidato; revalidar `origin/develop`, SHA dos canônicos e caminho do consenso protegido.
2. Escolher `change_mode` pelo contrato do PR: `strict_identity` ou `scoped_change`. Modo omitido/invalidado: `BLOCKED_CHANGE_MODE` (PROPOSTO), nunca inferir `scoped_change` a partir do diff.
3. Em `scoped_change` exigir lista `allowed_changes[]` por room e, quando possível, módulos/peças/campos; justificativa, especificação, R/CA e responsável por visual se aplicável.
4. Capturar baseline por commit e escala isolada: boxes (room, module, label/kind, intent, placement, bounds, host, policy, materials) + hash canônico + snapshot de consensus e fixtures.
5. Normalizar JSON, unidades e floats com contrato explícito, preservando diferenças geométricas acima da tolerância aprovada; nunca arredondar até “sumir” invasão de centímetros.
6. Recomputar planejamentos no commit candidato usando **o mesmo** PDF/consensus e parâmetros de entrada; obter delta estruturado por room e por peça, não apenas `sha256`.
7. Comparar `strict_identity`: qualquer diferença semântica/geométrica em boxes, canônicos ou input protegido = FAIL.
8. Comparar `scoped_change`: toda diferença deve casar com `allowed_changes` e **nenhuma** mudança fora da allowlist pode passar, mesmo se o hash de room autorizado mudou de forma esperada.
9. Rodar `room_collisions.audit` e gates de circulação por room; respeitar distinção intencional entre mobília, decoração, estrutural, hosted e walkable.
10. Revalidar arquitetura (parede, aberturas, anchors de hidráulica e contrato semântico) com gates existentes; inputs protegidos jamais podem ser mutados silenciosamente.
11. Executar sabotagens/fixtures negativas que comprovem que o gate encontra colisão lateral, área sobreposta, porta, mudança em outro cômodo e falso visual aprovado.
12. Se modo/escopo/provas não bastarem, registrar `BLOCKED/FAIL/PENDING` com motivo e próximos testes, sem editar canônico.
13. Para alteração geométrica autorizada, criar uma cópia de trabalho e executar job SketchUp em Windows real, com PID próprio e versão; salvar e reabrir.
14. Inspecionar caixas/elementos reais após reabertura; cruzar `room_id` e `persistent_id`/tags/atributos quando disponíveis; o comparador L2 não pode confundir box planejado com componente materializado.
15. Capturar renderizações top/iso e ângulos relevantes, dimensionadas para comparação com baseline; chamar `visual_regression_gate.build_montage` ou equivalente.
16. Se aparência mudou, exigir registro de `VISUAL_REVIEW` humano por Felipe vinculado à combinação `commit + before/after sha`. Sem registro: `PENDING_HUMAN`.
17. Gravar manifesto, hashes, decisões, provas executadas, skips e estado `PASS/PARTIAL/BLOCKED/FAILED`; atualizar docs/CI/PR sem inventar aprovação.
18. Somente após CA-19 concluir, fechar a fatia; abrir PR de correção do dono para cada achado real não coberto.

#### 2.2.2 Regras numeradas

| Regra | Condição | Efeito |
|---|---|---|
| R-01 | change_mode ausente/inesperado | `BLOCKED_CHANGE_MODE`, sem inferência |
| R-02 | `strict_identity` e qualquer box alterado | FAIL com before/after por room/peça |
| R-03 | `strict_identity` e canônico alterado | FAIL, sem re-baselinar automaticamente |
| R-04 | `scoped_change` sem allowed_changes ou justificativa | BLOCKED |
| R-05 | mudança em room não listado | `UNAUTHORIZED_ROOM_DELTA` (PROPOSTO) |
| R-06 | room autorizado muda outra peça não permitida | `UNAUTHORIZED_PART_DELTA` (PROPOSTO) |
| R-07 | `FURNITURE/FIXTURE` não hospedado invade parede além do epsilon do gate atual | FAIL, report área e profundidade |
| R-08 | `FURNITURE/FIXTURE/DECORATIVE` atrapalha arco de porta conforme limite/Z do gate atual | FAIL com door_id e área |
| R-09 | `STRUCTURAL` entra sob parede como junta intencional | não tratar como falha de mobília, mas continuar gates arquitetônicos |
| R-10 | `host.relationship != NONE` ou `interaction_policy.furniture_overlap != EXCLUSIVE` | aplicar exceção existente e documentar porque, não ignorar toda colisão |
| R-11 | material walkable (topo ≤ 2 cm) | não bloquear giro onde `room_collisions` já exclui |
| R-12 | porta até altura definida no gate atual (2,10 m) | comparar interseção vertical; não reportar colisão por footprint sem Z |
| R-13 | tolerâncias `EPS_AREA_PT2` e área de arco atual | reutilizar thresholds existentes, não reduzir/aumentar sem ADR |
| R-14 | diferença de float/unidade/ordem de JSON | normalizar sem esconder mudança real de coordenadas |
| R-15 | material/role/tag alterados, bbox idêntica | reportar delta semântico, não declarar “idêntico” por bbox |
| R-16 | fonte PDF/consensus/fixture alterada sem aprovação | FAIL protegido independentemente do modo |
| R-17 | D-007 corrigido em sintética mas muda SUITE 02 | comparação de controle + `PENDING_HUMAN`, nunca auto-merge de mudança visual |
| R-18 | mudança em cômodo open-plan sem célula física independente | usar room semântico/ID consistente; não criar parede artificial |
| R-19 | nova capability Shaker FP-046 | mudança permitida só na peça alvo; todo o resto do gabinete e cômodos-controle intactos |
| R-20 | L1 PASS sem SketchUp Windows | estado `PENDING_SKETCHUP` para L2, não `L2_PASS` |
| R-21 | job SKP falha/timeout | manifesto FAILED, canônico/base igual, sem sucesso aparente |
| R-22 | model inspect reaberto difere do plano | `FAILED_L2` com peça e dimensão |
| R-23 | saída salva tem componentes não editáveis ou objetos duplicados | `FAILED_L2` |
| R-24 | mudança estética sem registro humano | `PENDING_HUMAN`, jamais `APPROVED` |
| R-25 | render da versão A reutilizado para commit B | `BLOCKED_STALE_VISUAL_EVIDENCE` |
| R-26 | falha anterior/`xfail(strict)` conhecida | preservar estado e relatório; não transformar em PASS por ajuste de esperado |
| R-27 | diff diferente após reexecução igual | falha de determinismo com hash/entradas, não sobrescrever baseline |
| R-28 | código de room depende de outro room em novo PR | `ownership_audit` reprovando, corrigir owner/shared |
| R-29 | comparar fixtures real e sintética | processos separados por `PT_TO_M` |
| R-30 | relatório tem skipped/ambíguo/sem PID/version | não declarar `COMPLETE` de L2 |
| R-31 | grade de controle passa mas canônicos mudam | FAIL absoluto, sem exceção por allowed_changes |
| R-32 | revisão humana rejeita visual | estado `REJECTED`, voltar para nova variante sem “consertar” a referência aprovada |

**Tabela de decisão — tipo de mudança:**

| Tipo de PR | Modo exigido | Rooms que podem mudar | Prova |
|---|---|---|---|
| Refatoração de imports/fachadas (FP-044) | `strict_identity` | nenhum | `fp044_baseline compare IDENTICO` + gates |
| Alteração apenas de tests/docs sem mudar runtime | `strict_identity` / `no_runtime_change` como subclasse explicitamente aprovada | nenhum | baseline e invariantes de referências |
| Feature no gabinete sintético sem tocar planta | `scoped_change` | identificador de fixture/objeto novo; planta real: nenhum | plano+micro-fixture, hashes canônicos iguais |
| Fix D-007 sintética | `scoped_change` | `bedroom_medium_14m2_inner_face` declarada; SUITE 02 inicialmente controle | execução negativa, comparar SUITE 02; visual se muda |
| Fix sala (painel/mesa) com aparência | `scoped_change` | peças declaradas em sala | regressão geométrica e `VISUAL_REVIEW` |
| Correção estrutural de PDF/consensus | fora do escopo FP-047 | nenhum sem autorização e SPEC própria | bloquear por fonte protegida |

**Tabela de decisão — achado geométrico:**

| Tipo | Parede | Giro de porta | Resultado |
|---|---|---|---|
| `FURNITURE` normal/exclusiva | auditar | auditar respeitando Z | penetrou → FAIL |
| `FIXTURE` normal/exclusiva | auditar | auditar respeitando Z | penetrou → FAIL |
| `DECORATIVE` rente ao piso não walkable | seguir `audit` existente (não parede no contrato atual) | auditar giro se z relevante | porta invadida → FAIL |
| `STRUCTURAL` | não auditar como mobília | contrato arquitetônico separado | não mascarar como “móvel” |
| Hosted/`furniture_overlap != EXCLUSIVE` | regra especial real do gate | verificar circulação/Z normalmente | resultado/justificativa auditável |
| `WALKABLE` e baixa altura | contrato walkable | isenção do giro conforme gate | manter regras existentes |

**Matriz de responsabilidade — baseline versus delta:**

| Campo | Fonte de verdade | Pode variar? |
|---|---|---|
| Geometria arquitetônica | PDF + consensus protegido | NÃO nesta SPEC |
| `room_id` e room semântico | consensus + room registry | NÃO mudar para justificar delta |
| Box planejado | brain de cada owner + inputs | só se autorizado explicitamente no `allowed_changes` |
| Objeto real do SKP | reabertura + `su_inspect` / inspector próprio | deve refletir o plano aprovado |
| Hash do canônico | bytes canônicos (JSON com newline normalizado) | NÃO |
| Render/composição | câmera/view + SKP exato | pode mudar para evidência, nunca como prova geométrica isolada |
| Resultado estético | Felipe | só com veredito por commit+hash |
| Resultado de gates | runner/CI e L2 Windows | produzido em cada execução; nunca copiado de outra versão |

### 2.3 Componentes Impactados

| Caminho existente | Impacto | Detalhe |
|---|---|---|
| `tools/validation/fp044_baseline.py` | REUTILIZAR, não relaxar | `capture`/`compare` como base de modo estrito |
| `tools/validation/room_collisions.py` | REUTILIZAR | `audit`/`findings`, sem mudar semântica para encaixar esperado |
| `tools/rooms/shared/clearance.py` | REUTILIZAR | footprint, massa de parede, arcos e thresholds |
| `tools/validation/circulation_gate.py` | CHAMAR | regras existentes por cômodo |
| `tools/validation/run_deterministic_gates.py` | CHAMAR | fidelidade do shell |
| `tools/validation/scene_spatial_gate.py` | CONSULTAR/COMPOR | organização espacial quando apropriada |
| `tools/validation/visual_regression_gate.py` | REUTILIZAR | montagem, não aprovação |
| `tools/oracle/run_skp_visual_review.py` | NÃO DAR AUTORIDADE ESTÉTICA | consultivo somente |
| `tools/sketchup/jobs.py`, `tools/sketchup/process.py` | PRESERVAR | jobs seguros com PID próprio |
| `tools/mcp_server/server.py` | PRESERVAR | `su_furnish`, `su_build_shell` e `su_inspect` |
| `tools/orchestration/furnish_apartment.py` | FONTE DE BOXES | `collect_boxes(consensus)` |
| `tools/rooms/bedroom/designer.py` | OWNER DE D-007 | mudança apenas em PR específico, jamais por gate |
| `tests/test_fp043_room_collisions.py` | REGRESSÕES ANTIGAS | 0 parede/0 giro planta_74 |
| `tests/test_synthetic_polygon_convention.py` | NEGATIVO CONHECIDO | `xfail(strict)` preservado até correção e visual |
| `tests/test_kitchen_cabinet_adapter.py` e `test_kitchen_cabinet_flow.py` | REGRESSÃO FP-046 | quatro gates, idempotência, sem alteração no apartamento |
| `docs/specs/FP-043_open_decisions.md` | REGISTRAR ESTADO | D-007/D-001/visuais bloqueados |
| `docs/reports/FP-043_final_validation.md`, `FP-044_final_validation.md` | REFERENCIAR | histórico não é reescrito |
| **PROPOSTO** `tools/validation/room_regression.py` | CRIAR | `capture`, `compare`, classificações e relatório |
| **PROPOSTO** `core/schemas/room_regression_request.v1.schema.json` | CRIAR | allowlist, modos e owner |
| **PROPOSTO** `core/schemas/room_regression_report.v1.schema.json` | CRIAR | deltas, gates, evidências |
| **PROPOSTO** `tests/test_fp047_room_regression.py` | CRIAR | deltas, classificação, sabotagens |
| **PROPOSTO** `tests/test_fp047_sketchup_validation.py` | CRIAR | fake + bateria L2 Windows separada |
| **PROPOSTO** `tests/test_fp047_visual_verdict.py` | CRIAR | decisão humana vinculada ao hash, sem autopromoção |
| `docs/specs/fp042_inventory.v1.json` e `tools/rooms/ownership_audit.py` | REGISTRAR/VALIDAR | não criar arquivos órfãos |

### 2.4 Contratos de API

**API nova proposta é Python/CLI local, NÃO HTTP:**

```python
# PROPOSTO — não existe em develop@214d73e
from tools.validation.room_regression import capture, compare
before = capture(commit="BASE_SHA", fixture="planta_74", pt_to_m=0.0259)
after = capture(commit="CANDIDATE_SHA", fixture="planta_74", pt_to_m=0.0259)
report = compare(before, after, change_contract=contract)
# exit 0 apenas para PASS; 1 FAIL; 3 INCOMPLETE/BLOCKED (padrão proposto).
```

Não prometer `commit` remoto executável diretamente sem checkout isolado: `capture(commit=...)` requer worktree limpo para cada ref OU snapshots atestados; a API final deve receber paths de snapshots e rejeitar comparação sem base verificável. Definir o modo de comando explicitamente, por exemplo `python -m tools.validation.room_regression capture --out ...` e `compare --contract ... --before ... --after ...`, apenas após schema e testes.

**Integrações existentes:** `room_collisions.audit(consensus,boxes)` → `{room: {wall_penetration, door_swing_hits}}`; `fp044_baseline.capture()`/`compare(baseline)` → hash/deltas de identidade; `circulation_gate.gate(con,boxes,room_id)`; MCP stdio `su_build_shell`, `su_furnish`, `su_inspect` (parâmetros e erros conforme servidor existente).

**Exemplo de `room_regression_request.v1` (PROPOSTO):**

```json
{
  "schema_version": "room_regression_request.v1",
  "change_id": "fp047-d007-repro-001",
  "base_commit": "214d73e3c38c8bae9a3dc16f0fc579b64a017ac7",
  "candidate_commit": "SHA_DO_COMMIT_A_SER_TESTADO",
  "fixture": "planta_74",
  "consensus_path": "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json",
  "pt_to_m": 0.0259,
  "change_mode": "scoped_change",
  "allowed_changes": [
    {
      "room_key": "SUITE 02",
      "part_keys": ["wardrobe"],
      "allowed_effects": ["position"],
      "reason": "EXEMPLO de alteração sujeita a revisão visual",
      "spec_rule": "FP-047/R-17",
      "visual_review_required": true
    }
  ],
  "control_rooms": ["kitchen", "service"],
  "protect_canonicals": true,
  "require_l2": true,
  "require_l3_if_visual_changed": true
}
```

**Cuidado:** `room_key`, `part_keys` e `control_rooms` do exemplo são rótulos ilustrativos, não IDs canônicos resolvidos. Na implementação o comparador deve resolver contra o registry/consensus e rejeitar alias ambíguo ou inexistente; nunca permitir que um alias desconhecido faça o check pular um cômodo. Para D-007 o contrato de teste real precisa cobrir também a fixture sintética em **processo de outra escala**, não usar exemplo `pt_to_m=0.0259` para ela.

#### 2.4.1 Pré-requisitos de infra

Python 3.11/3.12 CI; `PT_TO_M=0.0259` apenas processo da planta_74, sintéticos com escala declarada da fixture; Git clean checkout/worktrees para comparações cross-commit; duas árvores rastreadas; SketchUp Windows (L2, versão registrada), acesso às cópias de SKP; jobs PID isolados; fonte PDF/consensus canônicos; sem usar `headless` no dev local; 4 checks CI (2 pytest, fidelity e MCP). Não precisa banco, filas, REST, Kafka ou login externo. V-Ray opcional para comparações que dependam do renderer.

### 2.5 Eventos e Mensageria

**Kafka/Avro/SQS/ACK manual: N/A.** Esta feature usa snapshots/manifestos locais com hash e pode registrar eventos JSONL do `core.observability` existente, opcional. Não introduzir tópico fictício.

#### 2.5.1 Entrada
`room_regression_request.v1` acima, chamado por script/PR/runner CI, não evento de tópico.

#### 2.5.2 Saída
**Exemplo de relatório PROPOSTO (`room_regression_report.v1`), sem fingir que houve execução:**

```json
{
  "schema_version": "room_regression_report.v1",
  "change_id": "fp047-d007-repro-001",
  "mode": "scoped_change",
  "state": "PENDING_L2",
  "base_commit": "214d73e3c38c8bae9a3dc16f0fc579b64a017ac7",
  "candidate_commit": "SHA_DO_COMMIT_A_SER_TESTADO",
  "input_sha256": null,
  "canonical_hashes_unchanged": null,
  "room_results": [
    {
      "room_key": "SUITE 02",
      "state": "NOT_RUN",
      "allowed_delta_count": 0,
      "unexpected_delta_count": 0,
      "wall_penetrations": [],
      "door_swing_hits": []
    }
  ],
  "tests": {"l1": "NOT_RUN", "l2": "PENDING_SKETCHUP", "l3": "PENDING_HUMAN"},
  "evidence": {
    "out_skp": null,
    "output_sha256": null,
    "sketchup_version": null,
    "before_after_contact_sheet": null,
    "visual_verdict_ref": null
  }
}
```

Campos `null`/`NOT_RUN` são intencionais e não podem virar PASS por default. `room_key` e `allowed_delta_count` só viram fatos após execução.

#### 2.5.3 Retry
Hash e combinação base/candidato iguais, compare puro pode reexecutar deterministicamente; job Windows falhou → registrar falha e nova tentativa explícita em cópia. Não reusar SKP/render de outro commit; nunca duplicar grupo.

#### 2.5.4 SQS/DLQ
`N/A`; erros são relatório tipado e evidência de execução.

#### 2.5.5 ACK manual
`N/A`; sucesso local só após arquivo report válido e evidências, sem afirmar durabilidade de broker.

### 2.6 Modelo de Dados

**DTOs propostos:**

| DTO | Campos | Invariante |
|---|---|---|
| `ChangeContractV1` | mode, base/candidate refs, allowed_changes, controls, reason, spec rule | mudança autorizada NÃO autoriza mutar PDF/consensus |
| `RoomSnapshotV1` | room_key+canonical room ID, box list, semantic hash, gate output, scale, source digests | guarda identidade por peça e unidades |
| `RoomDeltaV1` | before/after per part, fields_changed, area/coordinate delta, authorization, severity | permitir mudança apenas por allowed part/field |
| `GeometryFindingV1` | room, module, label, geometry_intent, wall/door ID, overlap_area_cm2, depth_cm, source | reports determinísticos, não adjetivos |
| `SketchUpEvidenceV1` | own_pid, SketchUp version, SKP input/output SHA, inspection checks, artefact path | L2 só com arquivo reaberto |
| `VisualReviewV1` | base/candidate hashes, view paths+hashes, reviewer, decision, timestamp | decisão humana, hash exato |
| `RoomRegressionReportV1` | contract, snapshots, deltas, gates, L1/L2/L3, status, reasons | nunca PASS com prova incompleta |

**Estados (propostos, mapeados explicitamente antes da implementação):** `PASS`, `FAIL`, `BLOCKED`, `PENDING_SKETCHUP`, `PENDING_HUMAN`, `REJECTED`, `NOT_APPLICABLE`. Usar `PENDING_HUMAN` conforme FP-045 v1.1.0, **não** inventar `PENDING_VISION` no código atual. Taxonomia de erro por tipo `INVALID_CONTRACT`, `BASELINE_MISMATCH`, `UNAUTHORIZED_ROOM_DELTA`, `UNAUTHORIZED_PART_DELTA`, `WALL_PENETRATION`, `DOOR_SWING_COLLISION`, `STALE_L2`, `STALE_VISUAL` (todos PROPOSTOS até schema implementado).

**Normalização:** JSON serializado ordenadamente com coordenadas no sistema documentado, valores e tipos preservados; tolerâncias geométricas **baseadas nos gates existentes**, não em threshold novo escolhido para passar D-007. SHA256 dos arquivos binários bruto; para JSON histórico normalizar LF/CRLF como `fp044_baseline._sha`. Datas, PIDs e caminho absoluto fora do fingerprint lógico (podem ir ao trace).

### 2.7 Requisitos Não Funcionais

| ID | Requisito | Prova |
|---|---|---|
| RNF-01 | Determinismo | mesma base+candidato+contrato gera deltas idênticos |
| RNF-02 | Integridade | SHA256 de canônicos e fixtures invariantes, antes/depois |
| RNF-03 | Fail-closed | modo/room/part incerto gera BLOCKED e exit não-zero |
| RNF-04 | Segurança de SketchUp | jobs em cópia, PID próprio; nunca `taskkill /IM` |
| RNF-05 | Independência do visual | IA não marca estética positiva sem humano |
| RNF-06 | Proveniência de prova | logs `change_id,commits,scale,room,part,gate,state,hash,sketchup_version` |
| RNF-07 | CI Linux | L1/contratos; skips L2 explícitos, nunca PASS |
| RNF-08 | Performance | usar hash como filtro rápido e delta detalhado só quando divergente; medir baseline antes de fixar tempo máximo |
| RNF-09 | Granularidade | relatório por room, objeto, campo e propriedade; não só “imagens diferentes” |
| RNF-10 | Compatibilidade | `fp044_baseline.compare` permanece estrito e disponível |
| RNF-11 | Source ownership | gate fica em validation e não importa implementações internas de um único cômodo |
| RNF-12 | Retenção | manifests append-only por commit; histórico de decisões versionado |

**Métricas propostas, se houver sink compatível:** `room_regression_total{mode,result}`, `room_delta_total{room,kind,authorized}`, `skp_inspection_total{status}`, `visual_review_pending_total{room}`. Não inserir biblioteca de métricas nova por padrão.

### 2.8 Estratégia de Testes

#### 2.8.1 Unitários obrigatórios

| Teste / arquivo | Cenários |
|---|---|
| **PROPOSTO** `tests/test_fp047_room_regression.py` | baseline idêntico, modificação permitida, room extra não permitido, mudança de tag sem bbox, reorder inofensivo, mudança >epsilon, alias inválido |
| **PROPOSTO** `tests/test_fp047_negative_fixtures.py` | guarda-roupa em parede, cadeira no arco, objeto hospedado, elemento estrutural, item piso walkable, alteração cross-room |
| **PROPOSTO** `tests/test_fp047_visual_verdict.py` | falta revisão, hash mismatch, reviewer não humano, rejeição, render stale, L3 approved só hash correto |
| **PROPOSTO** `tests/test_fp047_sketchup_validation.py` | FakeSystem prova fiação; bateria Windows separada L2 real |
| `tests/test_fp043_room_collisions.py` | contrato atual de mobília/fixture e giro, zero findings na planta real |
| `tests/test_synthetic_polygon_convention.py` | `xfail(strict)` D-007 documentado; não marcar PASS até correção verdadeira |
| `tests/test_kitchen_cabinet_adapter.py` / `test_kitchen_cabinet_flow.py` | âncora/circulação/escala/gabinete não invadir objetos |
| `tests/test_fp044_baseline.py` | comparação estrita permanece sensível a qualquer mudança de box/canônico |
| `tests/test_fp042_ownership_audit.py` | novo validation não cria dependência entre cômodos |
| `tests/test_fp045_knowledge_provenance.py` | FP-046 não promove fonte incorreta para mudar geometria |

**Negativos específicos, obrigatórios:** mover um móvel 4,5 cm para dentro de parede lateral; mover uma cadeira para arco de porta; mudar a caixa da SUITE 02 enquanto só sintética estava autorizada; renomear `room` para escapar comparação; preservar bbox mas trocar `geometry_intent` para `STRUCTURAL` e tentar esconder finding; alterar fixture protegida; desligar L2; reutilizar visual de SHA anterior.

#### 2.8.2 Integração / E2E

**L1 (Linux e Windows):** duas escalas em invocações separadas; registrar baseline real e synthetic isoladamente. Comandos existentes a executar:

```bash
python -m tools.rooms.inventory_gate --strict
python -m tools.rooms.ownership_audit
python -m tools.rooms.capability_catalog
python -m tools.navigation.p0_map --check
python -m tools.navigation.docs_check
python -m tools.rooms.asset_provenance
python -m tools.rooms.reference_provenance
python -m tools.run_deterministic_gates --fixture quadrado
python -m tools.run_deterministic_gates --fixture planta_74
python -m tools.mcp_server.smoke
python -m tools.mcp_server.stdio_check
python -m pytest tests/ -q -m "not planta74_scale"
PT_TO_M=0.0259 python -m pytest tests/ -q -m planta74_scale
```

**L2 (Windows real):** workflow real `su_build_shell → su_furnish → su_inspect` sob PID próprio; output apenas em `runs/`. Reabrir `.skp`, validar posições/quantidades/tags/materiais/arquitetura/gates; prova das versões e dos SHAs. Para alterações de mobiliário, comparar ante/depois especificamente nas peças e cômodos permitidos, inclusive em controles. Não usar o L2 do FP-043/044 como prova de uma implementação futura.

**L3:** pacote antes/depois com mesma câmera/iluminação/escala por visão, apontando a peça modificada; julgamento humano de Felipe com `APPROVED/REJECTED` ou `PENDING_HUMAN` e hash da versão. Diferenças de render podem ser aviso/insumo, não prova estética.

**Testcontainers/WireMock:** `N/A` sem backend/mensageria obrigatório.

#### 2.8.3 Critérios de Aceite (TAAC)

| CA | Given | When | Then |
|---|---|---|---|
| CA-01 | contrato sem modo | validar | BLOCKED, sem escolher `scoped_change` automaticamente |
| CA-02 | refatoração sem alterar output | `strict_identity` | hashes e boxes iguais, PASS L1 |
| CA-03 | refatoração altera box sala | `strict_identity` | FAIL com room e peça |
| CA-04 | canônico mudou (qualquer modo) | compare | FAIL não substituído por visual |
| CA-05 | mudança autorizada sem objeto específico | `scoped_change` | BLOCKED até delimitar |
| CA-06 | só o gabinete sintético pode mudar | alterar SUITE 02 | `UNAUTHORIZED_ROOM_DELTA` |
| CA-07 | quarto autorizado, mas peça diferente da allowlist | compare | `UNAUTHORIZED_PART_DELTA` |
| CA-08 | mesma bbox, material/tag/intent diferentes | compare | delta semântico visível |
| CA-09 | `FURNITURE` invade parede | audit | FAIL com profundidade/área |
| CA-10 | fixture ocupa arco de porta com Z relevante | audit | FAIL com `door_id` |
| CA-11 | só `STRUCTURAL` tem junta sob parede | audit | não fabricar finding de mobília; gate arquitetônico continua |
| CA-12 | hosted/walkable legítimos | audit | aplica isenção específica, sem desligar validação global |
| CA-13 | 0,0259 e sintética distintas | rodar suíte | processos isolados e resultados reprodutíveis |
| CA-14 | D-007 presente na sintética | rodar negativos | `xfail(strict)` continua visível, não suprimido |
| CA-15 | fix D-007 muda SUITE 02 | comparar | requires visual + explicitar delta; sem auto-merge |
| CA-16 | mudanças dentro do escopo | executar L1 | todos os gates determinísticos passam; canônicos idênticos |
| CA-17 | L1 PASS sem Windows | encerrar L1 | `PENDING_SKETCHUP` em L2 |
| CA-18 | SketchUp reaberto não confere com plano | validar L2 | `FAILED_L2` e evidência |
| **CA-19** | contrato, L1 e L2 aplicáveis completos | executar E2E/CI | quatro checks verdes, comparação base→candidato, SKP real reaberto, hashes intactos, controles sem mudanças e L3 humano se visual; caso contrário PARTIAL/BLOCKED |
| CA-20 | PID humano não salvo aberto | rodar L2 | sessão humana continua viva/não salva, jobs só fecham PIDs próprios |
| CA-21 | render antigo para novo commit | validar visual | `STALE_VISUAL` e `PENDING_HUMAN` |
| CA-22 | Felipe rejeitou resultado | promover | não promove; exige novo candidato |
| CA-23 | FP-046 gera porta Shaker na fixture | compare | apenas objetos autorizados mudam, nenhum componente duplicado |
| CA-24 | `room_id` sem correspondência | compare | FAIL/BLOCKED, não ignora room |
| CA-25 | código entra em owner errado | ownership | FAIL e rota de extração correta |
| CA-26 | testes locais skipped | relatório final | skip explicitado e nível de prova reduzido |
| CA-27 | documento histórico FP-043/044 | publicar novo resultado | novo relatório com commit, sem reescrever prova histórica |
| CA-28 | diff não reproduzível com mesmos inputs | reexecutar | falha de determinismo e hashes para diagnóstico |

**CA-19 é gate final obrigatório:** referência à execução do CI, lista de fixtures realmente executadas, evidências L2 Windows se requerido, aprovação humana vinculada a versão quando requerida, e hash SHA256 dos artefatos; execução parcial nunca rotulada como completa.

### 2.9 Estratégia de Lançamento

**R0:** adicionar schema/snapshot/fatos F0/F1, nenhum builder tocado. **R1:** L1 puro e sabotagens F2/F3 no CI. **R2:** piloto D-007 em modo análise, sem aplicar mudança de aparência/geometry na `develop` até pacote antes/depois e decisão de Felipe. **R3:** L2 Windows real em cópia F5. **R4:** pacote humano F6 e contrato de uso em PRs FP-046/F7. **R5:** consolidar relatório F8 com pendências honestas.

**Regras de PR:** pequenos, branch `develop`, cada mudança ligada a R/CA, quatro checks verdes; `main` só recebe release controlado. Gate modo `strict_identity` para refactors e `scoped_change` explícito para features/fixes. Novo motor **não substitui** `fp044_baseline compare`, que continua obrigatório para movimentos puros.

**Rollback:** `git revert` da fatia; cópias experimentais em `runs/` descartadas; referência/fixture/canônico nunca editados. Se a mudança funcional afetou geometria permitida, restaurar commit anterior e reexecutar L1; no Windows reabrir arquivo restaurado e validar. Antes de mudança estrutural, backup/hash; sincronizar cópia de prova em Downloads quando ambiente permitir, com verificação SHA e falha registrada se não permitir. `VISUAL_REVIEW` de uma versão não é portátil para outra.

### 2.10 ADRs vinculados

- `docs/specs/FP-045_specialists_knowledge_and_room_modularization.md` — L1/L2/L3, CA-19, governança por PR.
- `docs/specs/FP-043_open_decisions.md` — D-001/D-007/visuais.
- `docs/specs/FP-042_final_validation.md`, `docs/reports/FP-043_final_validation.md` e `docs/reports/FP-044_final_validation.md` — baselines e limites históricos.
- `docs/specs/FP-044_root_and_tools_consolidation.md` — `strict_identity` e integridade.
- `docs/specs/FP-046_shaker_parametric_cabinet_specialist.md` — consumidor do contrato para modelagem de marcenaria.
- **ADR-047-01 PROPOSTA:** esquema de `allowed_changes` e identidade de peças/cômodo em geometria com semantic zones.
- **ADR-047-02 PROPOSTA:** regras versionadas de equivalência de snapshots e tolerâncias que não escondam regressões.
- **ADR-047-03 PROPOSTA:** registro L3 de decisão humana ligado a hash/commit/câmera.

## 🔄 BLOCO 3 — Governança

### 3.1 Dúvidas resolvidas / pendentes

| ID | Estado | Decisão |
|---|---|---|
| D47-01 | RESOLVIDA | duas classes: `strict_identity` (refactor) e `scoped_change` (mudança autorizada) |
| D47-02 | RESOLVIDA | seguir a semântica existente `room_collisions.audit` em vez de novo detector incompatível |
| D47-03 | RESOLVIDA | aceitar alteração de caixa somente com diff semântico e allowlist, além de hash |
| D47-04 | RESOLVIDA | relatório histórico não é baseline reescrito; L2 novo precisa de execução nova |
| D47-05 | RESOLVIDA | `PENDING_HUMAN`, e não aprovação por oráculo, para aparência |
| D47-06 | PENDENTE TÉCNICA | identidade estável por peça/instância (module+label/id quando disponíveis); collisions de IDs |
| D47-07 | PENDENTE TÉCNICA | política de equivalência de floats e transforms; ADR 047-02 |
| D47-08 | PENDENTE FELIPE | aprovar qualquer aparência afetada pela correção D-007/SUITE 02 |
| D47-09 | PENDENTE FELIPE | D-001/quadrado é contrato separado, nunca baseline trocado para passar |
| D47-10 | PENDENTE TÉCNICA | conectar gate em CI e jobs Windows sem inferir L2 pelo Linux |
| D47-11 | PENDENTE TÉCNICA | ancorar revisão visual com hash, evitando falso `APPROVED` herdado |

### 3.2 Histórico de Versões

| Versão | Data | Autor | Descrição |
|---|---|---|---|
| 1.0.0 | 2026-10-21 | GPT-6 | SDD F0–F8, 32 regras, 28 critérios, modo dual, D-007 e integração FP-046 |

### 3.3 Handoff para agente implementador

1. Confirme `origin/develop`/CI/PRs atualizados; anote SHA real se evoluiu além de `214d73e`.
2. Leia `tools/validation/{fp044_baseline,room_collisions,circulation_gate}.py` e `tools/rooms/shared/clearance.py`; não invente thresholds.
3. Crie as fixtures negativas primeiro: SUITE 02 muda sem permissão, parede/arco/semantic tag e mudança em canônico.
4. Implemente F1/F2 puro e mantenha API `fp044_baseline`; regist­re novos arquivos em `fp042_inventory.v1.json` na mesma PR.
5. Rode 13 comandos L1 (seção 2.8.2), escalas separadas. Compare base vs candidato com input/hash igual e registre diferenças permitidas.
6. Faça F3 com o gate existente e F4 apenas diagnóstico D-007, sem conserto silencioso de SUITE 02.
7. Só após L1 bem definido executar L2 Windows real em `runs/`; registrar PIDs, versão, commit e reabertura.
8. Empacote L3 para Felipe nas alterações estéticas; mantenha `PENDING_HUMAN` até veredito real.
9. Exponha o gate na FP-046/F7 sem permitir `scoped_change` default.
10. PRs pequenos na `develop`, cada um com regras/CAs, rollback, quatro checks verdes e relatório de status.

## ✅ Checklist de Completude

**SPEC:**
- [x] Metadata, escopo/fim
- [x] Diagnóstico real (gates, D-007, L2/CI)
- [x] Pipeline e arquitetura com dois modos de mudança
- [x] 32 regras testáveis, tabelas de decisão, matriz de responsabilidades
- [x] Componentes reais e novos identificados como PROPOSTOS
- [x] Contratos JSON com exemplos que NÃO afirmam execução
- [x] Infra e mensageria N/A
- [x] Modelo, NFRs e métricas
- [x] Testes L1/L2/L3, sabotagens, 28 CAs e CA-19
- [x] Rollout, rollback, ADRs e governança
- [ ] ADR-047-01/02 (identity/tolerâncias) aprovada

**Implementação — tudo pendente:**
- [ ] F0 baseline por hash e mapa de controles verificado
- [ ] F1 schemas de request/report e negativos
- [ ] F2 comparador semântico e allowlist funcionando
- [ ] F3 gates de parede/giro/circulação com regras reais
- [ ] F4 D-007 analisado comparativamente, SUITE 02 com pacote humano (sem editar canônico)
- [ ] F5 L2 real no Windows e prova de reabertura
- [ ] F6 evidência visual e veredito humano por SHA
- [ ] F7 compatível com FP-046 e CI, sem regressão em `strict_identity`
- [ ] F8 relatório final e CA-19 com todas as evidências
- [ ] Nenhum `xfail/skip/PENDING` contado como PASS

**Estado:** RASCUNHO; não há alteração de geometria nem autorização automática para promover SKP ou baseline.
