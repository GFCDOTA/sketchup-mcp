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

---

## VEREDITO BRUTAL do GPT sobre o CORE construído (2026-06-22, GPT LEU o project_state.py raw)
**"isso AJUDA, não é firula. O domínio novo é bom. O risco agora é estragarem ele colocando IA opinativa e UI
bonitinha demais em cima ANTES de transformar o estado em dado confiável."**

**4 cortes/ajustes GRADUAIS (não agora — primeiro faz o dash usar bem o domínio):**
1. **UI dentro do domínio** (STATE_LABEL/ASSET_META/emoji/label/texto-de-botão no core) = acoplamento. Depois:
   criar `project_state_view.py`/`dashboard_presenter.py`; domínio fala `state="vray_ready"`, a UI traduz.
2. **Estado por substring de markdown é frágil "pra caralho"** (form_pass/ctx_pass procuram frase no .md) =
   **MAIOR RISCO REAL do core.** Fix: no próximo GPT gate salvar `gpt_verdict.json` sidecar {gate,verdict,asset,env};
   a state machine lê JSON, não frase. (mitigado parcial: já fiz case-insensitive, mas o certo é o sidecar JSON.)
3. **`asset_state()` recalcula 2-3×/render** (active_focuses chama asset_state; pipeline_for chama de novo; +carrega
   pack/cycles/glob). "Ok com 5 assets, molenga com 80." Fix: snapshot único — `state=project_state();
   active_focuses(state); pipeline_for(asset, asset_state)`. Sem banco, só não recalcula em cascata.
4. **`FIXED_STATE={"kitchen":"frozen"}` é gambiarra perigosa** — só a GEOMETRIA tá frozen; pele/pedra/eletros
   ainda vivos. Se o dash diz "cozinha congelada" Felipe perde confiança. Fix: kitchen_geometry=frozen,
   kitchen_skin=in_progress, kitchen_appliances=pending (sub-assets da cozinha).

**Locais (CONFIRMA minha posição):** "têm função decente, mas UMA só por enquanto: **Consistency/Gap Auditor**.
O resto é firula até o core estar sólido." Lê project_state+packs+DNA+anti+patches+verdicts+artifacts+cycles →
gera `proposal` (requires_approval, nunca muta). "propor próxima tarefa" = CORTAR (2 fontes de verdade vs o resolver).

**UX (prioridade #1 do GPT, FEITO):** hero mostra o foco NOMINAL "AGORA: Sala/Jantar · Sofá — pronto p/ V-Ray"
+ POR QUÊ + PRÓXIMO, não "focos ativos (1)". Múltiplos focos = principal expandido + outros como chips.

**Ordem recomendada pelo GPT:** (1) hero AGORA nominal ✅FEITO · (2) verdict estruturado (sidecar JSON) ·
(3) Auditor local único (gaps/contradições → proposals) · (4) snapshot/cache · (5) separar UI presenter do domínio.
