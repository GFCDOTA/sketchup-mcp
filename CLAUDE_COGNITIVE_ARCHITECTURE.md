# Claude Cognitive Architecture — sketchup-mcp

> **O que é isto:** mapa prático de COMO o Claude carrega contexto, decide e executa
> dentro deste repositório. Baseado em **leitura real** dos arquivos do `.claude/` e nas
> referências cruzadas encontradas (grep). Onde não há evidência, está marcado **UNKNOWN**.
> Auditado em **2026-06-05** (read-only; nenhum código alterado).
>
> **Como verificar:** todo item cita o arquivo-fonte. Abra o path e confira o trecho.
> Se este doc divergir do `.claude/CLAUDE.md`, **o CLAUDE.md vence** (é a fonte viva).

---

## TL;DR (modelo mental em 60 segundos)

1. Toda sessão começa lendo `CLAUDE.md` → que **importa** (`@`) uma lista fixa: **constitution → memory → specs → evals → plans**. Isso é **sempre carregado**.
2. **Skills** NÃO são importadas — são **auto-descobertas**: a *descrição* de cada uma fica disponível e a skill "acende" quando a tarefa casa o gatilho.
3. Várias specs são **on-demand** ("sob demanda, não auto-load") — só entram quando relevantes.
4. Em conflito entre documentos, **a Constitution vence** (regra explícita). Quebrar uma **Hard Rule** = **RED** = parar/pedir.
5. O **objetivo único** é um `.skp` fiel ao PDF, versionado em `artifacts/<plant>/`. Tudo o mais (testes, renders, gates, docs) só vale se servir a isso (Constitution #1/#8). O **PDF vence a inferência do agente** (#3). O único gate **humano** é o **Visual Review**.

---

# PARTE 1 — MAPA REAL DE CARREGAMENTO

## 1.1 Como o carregamento funciona (3 mecanismos distintos)

| Mecanismo | O que é | Quando carrega |
|---|---|---|
| **`@import`** (auto) | Linhas `@.claude/...` no `CLAUDE.md` | **Toda sessão**, na ordem listada |
| **Auto-discovery** (skills) | `.claude/skills/*/SKILL.md` | Descrição disponível sempre; **corpo** carrega ao **acionar** |
| **On-demand** (specs/docs) | Lista "Specs sob demanda (não auto-load)" | **Só quando relevante** à tarefa |

Evidência: `.claude/CLAUDE.md` — seções "Load order", "Skills" ("Auto-discovered em `.claude/skills/*/SKILL.md`") e "Specs sob demanda (não auto-load)".

## 1.2 Sequência de auto-load (sempre, nesta ordem)

```
Sessão inicia
  ↓
CLAUDE.md (corpo: missão + Hard Rules + "Oracle de decisão")   ← entry point
  ↓  @import:
1. .claude/constitution.md            ← princípios não-negociáveis (#1..#8)
  ↓  memory/ (estado + regras vivas):
2. project_context.md                 ← identidade + pipeline + fixtures
3. current_state.md                   ← snapshot do dia (DECAI RÁPIDO)
4. operational_rules.md               ← loop GREEN/YELLOW/RED + quando parar
5. git_workflow.md                    ← develop-first, gh, branch naming
6. multi_agent_coordination.md        ← worktrees, fetch sequencial, handoff
7. artifact_policy.md                 ← .skp é o deliverable; promotion
8. lessons_learned.md                 ← LL-001..LL-037 (anti-burrice)
9. deprecated_context.md              ← o que NÃO seguir mais
  ↓  specs/ (o "como deve ser"):
10. product_goal.md                   ← objetivo: .skp fiel ao PDF
11. fidelity_gate.md                  ← o que conta como "fiel"
12. skp_artifact_layout.md            ← paths/naming/metadata do .skp
13. skp_proof_of_progress_gate.md     ← "No SKP, no progress" (Constitution #8)
  ↓  evals/:
14. eval_strategy.md
15. fidelity_rubric.md
  ↓  plans/:
16. active_work.md
17. next_actions.md
  ↓
[Skills: descrições já disponíveis — corpo só ao acionar]
  ↓
Task do usuário → Execution
```
Evidência: bloco "Load order" em `.claude/CLAUDE.md` (lista `@.claude/...`).

## 1.3 On-demand (NÃO auto-load — só quando relevante)

`perfect_reference_strategy.md` · `sdd_and_harness_engineering.md` · `repository_hygiene.md` ·
`specs/templates/*` · `evals/regression_matrix.md` · `plans/roadmap.md` · `plans/stopped_work.md` ·
`docs/index.md` · `docs/audits/*`.
Evidência: seção "Specs sob demanda (não auto-load)" em `.claude/CLAUDE.md` ("consultados quando relevantes, não importados sempre").
> Nota: `gate_framework_and_audit.md`, `generalize_builder_constants.md` e `generalize_any_plant.md` **não estão na lista auto-load** nem na lista on-demand explícita → entram só por referência/relevância (ver Parte 5).

## 1.4 Obrigatório vs opcional vs depende

| Classe | Itens | Por quê |
|---|---|---|
| **Obrigatório (sempre)** | CLAUDE.md + todos os `@import` (1–17 acima) | Auto-load fixo |
| **Depende do gatilho** | Skills | Acionadas por frase/contexto da task |
| **Depende da task** | Specs on-demand, templates, docs/audits | Lidas quando o trabalho toca o tema |
| **Depende de verificação** | current_state.md | "decai rápido" → reconferir com git/gh |

---

# PARTE 2 — INVENTÁRIO DOS ARTEFATOS COGNITIVOS

## A) BOOTLOADER

| Arquivo | Função | Momento | Impacto |
|---|---|---|---|
| `CLAUDE.md` (raiz → `@.claude/CLAUDE.md`) | Entry point: missão, Hard Rules, ordem de carga, "Oracle de decisão" | Toda sessão, 1º | **CRÍTICO** |
| `.claude/constitution.md` | 8 princípios load-bearing; "se conflita com outro .md, **este vence**" | Toda sessão, logo após | **CRÍTICO** |

**Hard Rules (verbatim, `.claude/CLAUDE.md`)** — quebrar = **RED**:
1. **NEVER invent walls / rooms / openings** (consensus é a verdade).
2. **NEVER carve windows full-height** (preserva peitoril/verga; doors/passages 2D full-height).
3. **NEVER mutate input fixtures** (`fixtures/quadrado/`, `fixtures/planta_74/`) sem aprovação humana.
4. **NEVER push direto em `main`** (PRs `feature/`,`chore/` → `develop`).
Outras críticas: `--mode headless` proibido em dev local; `/runs/` é scratch (promover pra `artifacts/`); develop-first; multi-agent nunca assume exclusividade.

**Constitution — os 8 (resumo + quote-chave; fonte `.claude/constitution.md`)**:
1. **SKP é o artefato principal** — "entregável final é o `.skp` versionado em `artifacts/<plant>/`".
2. **Sem `.skp` versionado, não há sucesso canônico** — "PNG bonito mas sem `.skp` … é incompleta".
3. **PDF / ground truth vence inferência** — "quando há conflito … o PDF vence. Honesto > completo".
4. **Spec precisa virar teste + harness + artifact** — "Spec sem teste é ADR de prateleira".
5. **Cleanup não é progresso sem ROI** — "Cleanup em loop sem trigger é bikeshed".
6. **Slice complete IS a valid stop** — continuar só com próximo ROI ligado a SKP/fidelidade/gate/PR/milestone.
7. **Multi-agent exige fetch → worktree → reconcile** — "Nunca assumir exclusividade".
8. **No SKP, no progress** — toda SKP-affecting PR entrega `.skp` final + renders + `regression_summary.md`.

## B) MEMÓRIA (`.claude/memory/` — todos auto-loaded)

| Arquivo | Função (quote) | Quem consulta | Status |
|---|---|---|---|
| `project_context.md` | "Contexto estável… identidade + pipeline + fixtures canônicas" | CLAUDE.md, specs, skills, LL | **ATIVO** |
| `current_state.md` | "Snapshot: 2026-05-28 … decai rápido" | next_actions, multi-agent-handoff | **ATIVO mas STALE** (8 dias; por design — avisa pra reverificar via git/gh) |
| `operational_rules.md` | GREEN/YELLOW/RED + quando parar | Constitution #6, specs, skills | **ATIVO** |
| `git_workflow.md` | develop-first, `gh`, branch naming, ops destrutivas proibidas | deprecated_context, repo-governance | **ATIVO** |
| `multi_agent_coordination.md` | "Princípio raiz: nunca assumir exclusividade" | Constitution #7, skills, `.ai_bridge/HANDOFF` | **ATIVO** |
| `artifact_policy.md` | "O `.skp` é o artefato humano mais importante" + promotion | Constitution #1/#8, specs, skills | **ATIVO** |
| `lessons_learned.md` | "Aprendizados permanentes… LL-001..LL-037" | specs, skills, audits | **ATIVO (mais fresco: 2026-06-02)** |
| `deprecated_context.md` | "Instruções que **NÃO** devem mais orientar" | git_workflow, LL | **ATIVO** (lista superseded — ver Parte 5) |

Exemplo real de influência: `operational_rules.md` define os 7 critérios RED → é o que faz o Claude **parar e perguntar** (creds, ação destrutiva, mudança de objetivo, merge vermelho, falta de artefato obrigatório…). `current_state.md` se auto-protege: o cabeçalho manda reverificar com git antes de qualquer decisão remota.

## C) SPECS (`.claude/specs/`)

| Spec | Load | Quando ativa / quem usa | Status |
|---|---|---|---|
| `product_goal.md` | auto | objetivo do produto; toda decisão de artefato | **CRÍTICO** |
| `fidelity_gate.md` | auto | define "fiel" (2 eixos: self-check booleano + julgamento humano); skills de fidelidade | **CRÍTICO** |
| `skp_artifact_layout.md` | auto | paths/naming/metadata; promotion SOP (rewrite do sidecar) | **ALTO** |
| `skp_proof_of_progress_gate.md` | auto | "No SKP, no progress"; hard-block de PR | **CRÍTICO** (Constitution #8) |
| `sdd_and_harness_engineering.md` | on-demand | ao criar feature que toca contrato (define SDD + Harness) | **ALTO** |
| `repository_hygiene.md` | on-demand | ao limpar repo (anti-cleanup-sem-trigger) | **MÉDIO** |
| `perfect_reference_strategy.md` | on-demand | estratégia de verdade (truth-cards) — pasta ainda TODO | **MÉDIO** |
| `gate_framework_and_audit.md` | não-listado | design do gate/audit-core (`:8765`, audit.jsonl) — **implementação delegada/não construída** | **PROPOSTO** |
| `generalize_builder_constants.md` | não-listado | BLUEPRINT (não-executado de propósito; espera "árvore esfriar") | **BLUEPRINT** |
| `generalize_any_plant.md` | não-listado | DRAFT (2026-05-31, não commitado; revisão do Felipe) | **DRAFT** |
| `templates/{artifact_contract,feature_spec,regression_summary}_template.md` | on-demand | ao criar feature/spec/summary | **ATIVO** |
| `templates/fidelity_spec_template.md` | on-demand | gerar README de fidelidade | **BAIXA-REF** |

## D) SKILLS (`.claude/skills/*/SKILL.md` — auto-descobertas; 11 no total)

| Skill | Gatilho (resumo) | Saída |
|---|---|---|
| `pdf-to-skp-pipeline` | toca `consensus.json` / `build_plan_shell_skp.{py,rb}` / "gerar SKP" | `.skp` em `runs/`, renders, `geometry_report.json` |
| `fidelity-review` | "review SKP", "fidelity check", "validar contra planta" | checklist walls/rooms/openings; escala p/ humano |
| `generate-and-compare-skp-after-change` | "melhora/corrige fidelity/wall/janela…" (PÓS-mudança no builder) | `.skp` novo + `regression_summary.md` em `artifacts/review/` |
| `skp-visual-self-correction` | `model.skp`, "visual review", "FP-030"; regra: **o usuário NÃO é o detector visual** | `visual_findings.json`, loop até 3 tentativas |
| `skp-artifact-management` | `artifacts/<plant>/`, "promote SKP", "build provenance" | promove p/ `artifacts/`, reescreve sidecar |
| `gpt-auto-consult-gate` | 9 triggers de decisão real (LL-024); A/B/C, oracle≠final… | consulta `:8765`; grava em `.ai_bridge/questions|responses` |
| `repo-governance` | "abrir PR", "merge develop", "branch cleanup", "develop-first" | PR via `gh` contra develop; cleanup |
| `gh-autopilot` | "abrir/mergear PR", "gh auth", "nunca deixar PR aberto" | commit→PR→merge→cleanup (gotchas do token GFCDOTA) |
| `multi-agent-handoff` | `git worktree`, ".ai_bridge", "branch que apareceu" | pre-flight fetch→rev-parse; isolamento worktree |
| `autonomous-fidelity-loop` | "não pare", "loop contínuo", "trabalha sozinho na planta" | log por ciclo (PROGREDINDO/PATINANDO/BLOCKED), heartbeat |
| `interior-design` | "mobiliar", "decorar", `furnish_plan`, `interior-designer` | variantes `planta_74_vN.skp` mobiliadas |

Todas têm gatilho claro (nenhuma "skill morta"). Skills são subordinadas à Constitution/Hard Rules.

## E) GOVERNANÇA (controla o que pode/não pode)

- **`git_workflow.md`** — develop-first; PR só via `gh` (`--repo GFCDOTA/sketchup-mcp --base develop --body-file -`); checks de merge (pytest verde, sem conflito, sem delete de fixture canônica); `branch -D` proibido sem OK; **ops destrutivas proibidas** (force push, `--no-verify`, `reset --hard` não-local, `rebase -i`, set global user.name/email).
- **`multi_agent_coordination.md`** — nunca assumir exclusividade; **fetch sequencial** (não paralelo a rev-parse); commit/branch out-of-band detectado → **parar e reconciliar**; worktrees isoladas; handoff em `active_work.md`/`.ai_bridge/`.
- **`operational_rules.md`** — GREEN (executa direto) / YELLOW (executa + PR + review) / **RED (para e pergunta)**; "slice complete IS a valid stop"; override verbal "NÃO PARE".
- **`repo-governance`** (skill) — operacionaliza o git_workflow em PR/branch/merge.

---

# PARTE 3 — CICLO DE VIDA DE UMA TASK

## 3.1 Fluxo concreto: "Corrija a fidelidade da planta_74"

```
Usuário: "corrige a fidelidade da planta_74"
  ↓ [auto-load já ativo: CLAUDE.md + Constitution + memory + specs]
1. Constitution #1/#3  → .skp é o alvo; PDF vence inferência
2. product_goal.md     → "fiel ao PDF, revisável, versionado"
3. fidelity_gate.md    → o que medir (walls/rooms/openings + self-check)
4. SKILL acionada: generate-and-compare-skp-after-change  (gatilho "corrige fidelity")
     ↳ usa pdf-to-skp-pipeline pra BUILD
  ↓
5. build: tools/build_plan_shell_skp.py  (consensus.json → .skp em runs/)   [Hard Rule #1: não inventar]
6. compara before/after: geometry_report.json + renders
7. SKILL: skp-visual-self-correction → detectores DETERMINÍSTICOS (overlay_diff / opening_host_audit)
     ↳ se mudou APARÊNCIA → sobe pro HUMANO (Visual Review) — IMPROVED/SAME/WORSE nunca é auto
8. gate: skp_proof_of_progress_gate.md → exige .skp final + renders + regression_summary.md
9. artifact_policy.md + skp_artifact_layout.md → promove p/ artifacts/review/<plant>/<branch>/final/ (reescreve sidecar)
10. operational_rules.md → YELLOW (toca contrato): commit + PR contra develop, marca review
11. (decisão real? ex. oracle≠final) → gpt-auto-consult-gate consulta :8765 (modo B)
  ↓
Artefatos produzidos: .skp + renders top/iso + geometry_report.json + regression_summary.md + (PR)
```

## 3.2 Fluxo concreto: "Abre um PR disso"

```
"abrir PR" → SKILL repo-governance / gh-autopilot
  ↓
git_workflow.md: fetch→status→rev-parse (sequencial)  [multi_agent: reconciliar se out-of-band]
  ↓
gh pr create --repo GFCDOTA/sketchup-mcp --base develop --body-file -   [Hard Rule #4: nunca main]
  ↓
checks: pytest verde · target develop · sem conflito · sem delete de fixture
  ↓
(merge) → cleanup: branch -d + push --delete   [branch -D proibido sem OK]
```

---

# PARTE 4 — MATRIZ DE USO

| Arquivo | Quando usa | Frequência | Impacto | Classe |
|---|---|---|---|---|
| `CLAUDE.md` | toda sessão | altíssima | crítico | **CRÍTICO** |
| `constitution.md` | toda sessão / todo conflito | alta | crítico | **CRÍTICO** |
| `operational_rules.md` | toda decisão (GREEN/YELLOW/RED) | alta | crítico | **CRÍTICO** |
| `product_goal.md` | toda decisão de produto | alta | crítico | **CRÍTICO** |
| `fidelity_gate.md` | toda task de fidelidade | alta | crítico | **CRÍTICO** |
| `skp_proof_of_progress_gate.md` | toda SKP-affecting PR | alta | crítico | **CRÍTICO** |
| `artifact_policy.md` | ao gerar/promover artefato | média | alto | **ALTO** |
| `skp_artifact_layout.md` | ao promover `.skp` | média | alto | **ALTO** |
| `git_workflow.md` | todo commit/PR/branch | média-alta | alto | **ALTO** |
| `multi_agent_coordination.md` | antes de mutação remota | média | alto | **ALTO** |
| `project_context.md` | onboarding/pipeline | média | alto | **ALTO** |
| `lessons_learned.md` | antes de repetir algo | média | alto | **ALTO** |
| `sdd_and_harness_engineering.md` | ao criar feature de contrato | ocasional | médio | **MÉDIO** |
| `repository_hygiene.md` | ao limpar repo | ocasional | médio | **MÉDIO** |
| `perfect_reference_strategy.md` | estratégia de verdade | rara | médio | **MÉDIO** |
| `current_state.md` | início de sessão (com ressalva) | média | **baixo-confiável** (stale) | **BAIXO** |
| `templates/*` | ao criar spec/feature/summary | rara | médio | **MÉDIO** |
| `gate_framework_and_audit.md` | design do gate (não construído) | rara | médio (futuro) | **PROPOSTO** |
| `generalize_builder_constants.md` | swap-in futuro (blueprint) | nunca (ainda) | baixo (futuro) | **BLUEPRINT** |
| `generalize_any_plant.md` | draft sob revisão | nunca (ainda) | baixo (futuro) | **DRAFT** |
| `evals/regression_matrix.md`, `plans/roadmap.md`, `plans/stopped_work.md`, `docs/audits/*` | quando relevante | rara | baixo-médio | **MÉDIO/BAIXO** |

---

# PARTE 5 — O QUE ESTÁ MORTO / REDUNDANTE / SUPERSEDED

> Regra: **nada é apagado** — só evidência. "Sem refs" = grep não achou referência de entrada fora do próprio arquivo.

**Superseded (marcado em `deprecated_context.md`):**
1. **PR manual via browser** → superseded por `gh` (`git_workflow.md`). Quote: "Não há mais motivo pra preferir browser manual."
2. **Pipelines V3–V6.x** → podados (PR #184); viviam em repos externos.
3. **`consume_consensus.rb` (entities.clear! + rebuild)** → superseded por edição in-place via push_pull (LL-001).

**Não-construído / proposto (design existe, implementação não):**
- `gate_framework_and_audit.md` — **PROPOSTO/DELEGADO**: audit-core + gate registry "delegado ao loop autônomo", ainda não construído.

**Blueprint / Draft (parados de propósito, sem refs de entrada):**
- `generalize_builder_constants.md` — **BLUEPRINT** ("não-executado de propósito; quando a árvore esfriar"). Sem inbound refs.
- `generalize_any_plant.md` — **DRAFT** (não commitado; revisão do Felipe). Sem inbound refs executáveis.

**Stale (por design, não morto):**
- `current_state.md` — snapshot de **2026-05-28** (8 dias na data da auditoria). Não é bug: o arquivo manda reverificar com git/gh.

**Baixa referência (não morto, mas pouco usado):**
- `templates/fidelity_spec_template.md` — sem inbound grep claro (gerador de README).

**Nenhum arquivo verdadeiramente órfão/dead encontrado** — todos têm âncora (auto-load, ref de skill, ou intenção constitucional). Os "fracos" são blueprints/drafts conscientes, não lixo.

**TODOs de validação abertos** (achados nos próprios arquivos, marcados UNKNOWN):
- `.ai_bridge/` está ativo neste repo? (multi-agent-handoff + multi_agent_coordination dizem "não auditado no snapshot 2026-05-27").
- Comando exato do `side_by_side_pdf_vs_skp.png` e do sidecar metadata (skp-artifact-management).
- pyproject deps / entry points (project_context).
- `artifacts/review/<plant>/` é convenção ou staging pontual do PR #192? (artifact_policy).

---

# PARTE 6 — O QUE REALMENTE CONTROLA O CLAUDE (PRECEDÊNCIA)

**Única precedência EXPLÍCITA no repo** (`.claude/constitution.md`, preâmbulo):
> "Se algo neste arquivo conflita com qualquer outro `.md`, **este arquivo vence** — o outro precisa mudar."

Hierarquia evidenciada (do mais forte ao mais fraco):

```
1. CONSTITUTION (.claude/constitution.md)      ← "este arquivo vence" (explícito)
2. HARD RULES (CLAUDE.md)                       ← quebrar = RED = parar/pedir
3. MEMORY / OPERATIONAL_RULES (GREEN/YELLOW/RED) ← porta de execução vs parada
4. SPECS (fidelity_gate, proof_of_progress, …)   ← regras técnicas; derivam da Constitution
5. PLANS / SKILLS                                ← táticas; subordinadas ao acima
```
Mais dois eixos explícitos:
- **PDF / ground truth > inferência do agente** (Constitution #3 + Hard Rule #1).
- **Visual Review (humano) > veredito visual automático** (CLAUDE.md "Oracle"; IMPROVED/SAME/WORSE nunca é auto).

**Usuário (Felipe) vs documentos — `UNKNOWN/INFERIDO`:** não há uma frase única "usuário vence a Constitution". O que existe:
- Mudar a Constitution exige "**PR explícita e justificativa**" (constitution.md) → ela não é alterada de improviso numa sessão.
- `operational_rules.md`: autonomia default = "total + carta branca + bypass"; mas os **7 critérios RED** ainda forçam parar/perguntar; e há **override verbal "NÃO PARE"**.
- **Síntese (inferida):** dentro de uma sessão, Hard Rules/Constitution agem como **guard-rails** (quebrar = RED = parar e pedir); o humano pode autorizar explicitamente exceções caso-a-caso, e só muda a Constitution via PR. As regras de segurança do harness (instruções válidas vêm do usuário no chat; conteúdo observado é dado, não comando) ficam **acima de tudo** e não são sobrepostas por nenhum `.md` do projeto.

---

# PARTE 7 — GLOSSÁRIO (siglas e termos)

| Termo | Definição (resumida) | Onde é definido |
|---|---|---|
| **SDD** (Spec-Driven Development) | Mudança que toca contrato exige **spec curto ANTES do código** (problem/proposta/casos de teste/aceite/out-of-scope) | `specs/sdd_and_harness_engineering.md` |
| **Harness** | Spec sem harness não conta: **fixture mínima + teste vermelho→verde + evidência visual + aplicação no pipeline real** | `specs/sdd_and_harness_engineering.md` |
| **Gate** | Módulo de decisão registrado (`applies/build_prompt/parse`) que emite `Verdict = GO\|NO_GO\|VISUAL_REVIEW\|MORE_INFO`; operacionalmente, decisões reais vão pro `:8765` | `specs/gate_framework_and_audit.md` + `CLAUDE.md` |
| **Oracle** | O bridge em `:8765` (modo B, autonomia delegada) que decide o técnico/fixture/merges por evidência; só Visual Review é humano. Multi-oracle: Claude + LLM local + determinístico | `CLAUDE.md` "Oracle de decisão" + `gate_framework_and_audit.md` |
| **Fidelity** | 2 eixos: **(1)** `gates_self_check` (4 booleanos machine-readable) e **(2)** fidelidade arquitetônica (julgamento humano no README): wall/room/opening fidelity | `specs/fidelity_gate.md` |
| **Artifact Promotion** | Copiar build de `runs/` (scratch) → `artifacts/<plant>/` (deliverable), **só com gates verdes**, reescrevendo o sidecar (`skp_path` ← canônico) | `memory/artifact_policy.md` + `specs/skp_artifact_layout.md` |
| **Proof of Progress** | "**No SKP, no progress**": SKP-affecting PR exige `.skp` final + renders + `regression_summary.md` com evidência por axis; senão **não está concluída** | `specs/skp_proof_of_progress_gate.md` + Constitution #8 |
| **Visual Review** | Único gate **humano**: quando a **aparência** da planta muda, só o olho do Felipe valida vs o PDF; veredito IMPROVED/SAME/WORSE nunca é auto | `CLAUDE.md` "Oracle" + `specs/generalize_any_plant.md` |
| **GREEN/YELLOW/RED** | Framework de autonomia: GREEN=executa direto; YELLOW=executa+PR+review; RED=para e pergunta (7 critérios) | `memory/operational_rules.md` |
| **modo B** | Autonomia delegada pelo Felipe: oracle decide tudo menos o olho na planta | `CLAUDE.md` + `gate_framework_and_audit.md` |
| **LL-NNN** | Lições permanentes numeradas (LL-001..LL-037), cada uma custou tempo/PR/rework | `memory/lessons_learned.md` |
| **FP-NNN** | Specs de feature (ex. FP-030 Visual Oracle Gate) sob `docs/specs/` | `specs/templates/feature_spec_template.md` |
| **`.ai_bridge/`** | Protocolo de coordenação entre agentes (HANDOFF, questions/responses, audit.jsonl) — **status neste repo: UNKNOWN/TODO** | `multi_agent_coordination.md` (não auditado) |
| **`/runs/` vs `artifacts/`** | `runs/` = scratch (gitignored, descartável); `artifacts/<plant>/` = deliverable humano versionado | `memory/artifact_policy.md` |

---

## Apêndice — limites desta auditoria

- Baseada em leitura do `.claude/` + grep de referências em **2026-06-05**. Arquivos podem ter mudado depois.
- Itens marcados **UNKNOWN / PROPOSTO / BLUEPRINT / DRAFT** não foram inventados — são o que os próprios arquivos declaram.
- A precedência **usuário vs Constitution** é **inferida** (não há regra única explícita) — ver Parte 6.
- Para a verdade viva, `.claude/CLAUDE.md` + `.claude/constitution.md` mandam; este doc é um mapa, não a fonte.
