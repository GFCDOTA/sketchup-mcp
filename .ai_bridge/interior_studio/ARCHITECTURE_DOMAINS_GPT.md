# Arquitetura — Domínios ricos por ambiente + Locais autônomos · Claude × GPT (ponte) · 2026-06-22

> Felipe: (1) a app não SABE qual ambiente estamos tratando; quer domínio por ambiente + múltiplos fluxos
> vivos; (2) os LLMs locais ficam parados, quer eles autônomos. **GPT concordou com as 2 posições do Claude**,
> com refinamentos. Consenso abaixo.

## VEREDITO GPT: "concordo com as duas posições" — com 1 trava
**Domínios ricos EM CÓDIGO, contratos claros, mas dentro de um MONÓLITO MODULAR/local — não vira
microserviço cedo demais. O produto precisa ficar mais INTELIGENTE, não mais distribuído.**

## 1) Domínio por ambiente (CONCORDO 95%)
A app é centrada em ciclo ativo, mas o Felipe pensa por **ambiente real** ("estou na cozinha", "esse sofá é da sala",
"essa pedra é da cozinha", "esse render é da sala, não do projeto inteiro"). Precisa de **domínio rico por ambiente**.

**Estrutura (raiz):** `Project → EnvironmentDomain[]` (LivingRoom · Kitchen · Bedroom · Bathroom · Laundry · …).

**Cada `EnvironmentDomain`** (rico, mas COMPOSTO de peças pequenas — NÃO God object `KitchenDomainGodObject`):
- `EnvironmentState` — guarda o estado.
- `EnvironmentPolicy` — sabe quais etapas fazem sentido NAQUELE ambiente.
- `AssetRegistry` — sabe quais assets pertencem ao ambiente.
- `PipelineResolver` — calcula fase/status.
- `NextActionResolver` — calcula o próximo botão.
- `EvidenceIndex` — aponta artefatos, renders, perguntas, patches, commits.
Campos: identity(project/env/name/source_room_id) · geometry_state(extracted/validated/frozen/issues) ·
design_intent(style/material/constraints/anti_patterns) · assets[] · pipeline(current_phase/next_action/blockers/evidence) ·
learning(approved_patches/rejected_patches/frozen_rules).

**Pipeline é POLÍTICA do domínio, não enum global burra** — cada ambiente tem o seu:
- Sala/móvel: Referências → Curadoria → Build Spec → Construção → Golden Render → Learning Patch → Frozen.
- Cozinha: Geometria → ... → Golden Render → Learning Patch → Frozen.
- Banheiro: Geometria → Louças/metais → Bancada/cuba → Revestimento → Iluminação/espelho → Render → Learning Patch → Frozen.

**Múltiplos focos vivos** (resolve "tenho 2-3 sessões abertas"): `active_focuses[]` derivado do estado:
```json
{"active_focuses":[
  {"environment":"sala","asset":"sofa","phase":"vray_ready","reason":"MT-SOFA-004 aprovado no contexto"},
  {"environment":"cozinha","asset":"backsplash","phase":"curation_needed","reason":"refs removidas, pack insuficiente"}]}
```
No dash: "Focos ativos: 1. Sala/Sofá — pronto p/ V-Ray · 2. Cozinha/Pedra — reabastecer refs · 3. Cozinha/Iluminação — aguardando spec".
Felipe não escolhe manual sempre — o sistema mostra os fluxos VIVOS.

## 2) Locais autônomos (CONCORDO 90%)
LLMs locais parados = subutilizados → viram **workers offline de bastidor**. **MAS sem autonomia de mexer no
estado canônico** (eles PROPÕEM, Felipe aprova — mesmo gate do Learning Patch).
**Worker loop offline (`offline_jobs`):** reference_analysis · spec_draft · consistency_check · gap_detection ·
anti_pattern_scan · next_task_proposal · learning_patch_draft.
Cada resultado vira um `proposal` {proposal_id, source_worker, environment, asset, confidence, summary, evidence,
suggested_action, **requires_approval: true**}. **Nada entra direto.**

## Scout/Claude reabastece referências (CONCORDO 100%)
"Remover ref ruim e o pack ficar vazio = o fluxo morre. Isso é erro de produto." Precisa de `ReferencePackHealth`
{enough_refs, missing_categories, rejected_refs, reason, **next_action: scout_fetch_more**}. Pack esvaziou → auto-flag → Scout reabastece.

## Plano (consenso Claude+GPT) — monólito modular, rico, sem God-object
1. **EnvironmentDomain** (composto: State/Policy/AssetRegistry/PipelineResolver/NextActionResolver/EvidenceIndex) — evoluir o `project_state.py` atual.
2. **active_focuses** no dash (substitui o "foco = ciclo ativo" por N fluxos vivos).
3. **Pipeline por política de domínio** (móvel ≠ cozinha ≠ banheiro).
4. **Offline worker loop** dos locais → proposals (requires_approval) — dar trampo pros caras.
5. **ReferencePackHealth** + Scout auto-refill (mata o beco sem saída).

⚠️ Bridge gotcha confirmado: setas `→`/acentos corrompem msg longa pelo digitador do Chrome — mandar com "->".
