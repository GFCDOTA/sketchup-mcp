# HANDOFF — Interior Studio · Consult GPT Bridge

> Plano de implementação do loop Arquiteto ↔ Consult GPT (pergunta/resposta estruturada).
> Escrito 2026-06-20. **Fase 0 + Fase 1 FEITAS nesta execução; o resto é TODO.**
> Regra central: referência = LINGUAGEM · PDF = GEOMETRIA · gates = SEGURANÇA · **Felipe = PASS final**.

## Estado atual (Fase 0 — descoberta)
- **Dashboard Interior Studio:** `tools/studio_dashboard.py` (servidor stdlib, **`:8782`**, em Docker —
  `docker compose up -d`, `restart unless-stopped`; UI servida INLINE do .py). **NÃO é** `tools/interior_studio/server.py`
  (esse caminho não existia). O `Dockerfile.dashboard` aponta pro arquivo atual.
- **Oráculo técnico NOC:** `tools/claude_bridge/server.py` em **`:8765`** — serviço SEPARADO, **não tocar**.
- **Endpoints atuais (:8782):** `GET /api/state` · `POST /api/ask|cycle|consensus|move|curate|flag|upload|preview|feed|forget` · `GET /img/<name>` · `GET /inbox-img/<name>`.
- **Renders:** `_renders()` lê PNGs de `artifacts/planta_74/furnished/kitchen_angles/` (hoje VAZIO), servidos por `/img/<name>`, tema inferido por `reference_db._infer_from_name`.
- **reference_db:** SQLite sobre `artifacts/reference_lab/` (cards/themes/tokens/renders). **NÃO** indexa o `references/` de topo (KB de regras/tokens).
- **Alimentar o Arquiteto (3 camadas, já existe — commit 9f66b93):** (1) `.claude/memory/felipe_style_dna.md` (DNA canônico) → (2) `references/design_rules/felipe_visual_judge_rules.json` (anti-patterns + erros marcados) → (3) `.ai_bridge/knowledge/architect.md` (feed colado). `/api/flag` grava no judge-rules; `/api/state` expõe `knowledge.dna`+`judge`.
- **Estilo da COZINHA = CONGELADO:** `KITCHEN_THEME=black_wood_gold` → `artifacts/reference_lab/themes/BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE.json` = **GOLDEN_SAMPLE_004 aprovado**. A cozinha **não** lê `interior/style_packs/` (isso é o `scene_composer.py` da SALA).
- **Backlog:** `artifacts/reference_lab/kitchen/spec/KITCHEN_TO_100.md` + Kanban `.ai_bridge/kanban.json`.

## Objetivo final
Loop fechado: o Arquiteto emite `ARCHITECT_QUESTION_CONTRACT`, o Felipe leva ao Consult GPT, a resposta
(`ARCHITECT_ANSWER_CONTRACT`) volta, é ingerida, e vira regra/anti-pattern/token/DNA/próxima-microtarefa —
rastreável e versionável, funcionando **sem internet e sem OpenAI** (MVP manual). OpenAI e Chrome são opcionais.

## Decisões de produto (travadas)
1. **`consult-liaison` é SIDECAR do Arquiteto**, não 4ª coluna. Mini-card / painel colapsável `🔌 Consult GPT Bridge`
   dentro da coluna do Arquiteto. Estados: `idle | preparing_question | waiting_felipe | waiting_answer | ingesting | learned`.
   Ele NÃO decide design, não move geometria, não substitui o Arquiteto, não gera render, não inventa preferência.
2. **"Rodar 1 ciclo" vira uma ENTIDADE `cycle`** (CYCLE-NNN) com steps PM→Team Lead→Arquiteto→Consult Liaison,
   modelos usados por step, consenso/conflito. Painel "Ciclo atual" + "Histórico de ciclos" colapsável. (track UI)
3. **Endpoints `/api/consult/*` entram no `studio_dashboard.py` existente** (importando `consult_gpt_bridge`),
   NÃO num server novo. O `:8765` fica intocado. MVP roda offline.
4. **DNA + style pack:** `felipe_style_dna.md` JÁ existe (commit 9f66b93, agora com "Sensação desejada"). O style pack
   `interior/style_packs/black_wood_gold_industrial_boutique.json` é o sistema da **SALA** (scene_composer) — MT-009 só
   faz sentido se for propagar pra sala; a cozinha já está no theme congelado. **Não duplicar** o DNA da cozinha lá.

## Fases
- **Fase 0 — descoberta** ✅ (acima)
- **Fase 1 — contratos** ✅ (templates + schemas, esta execução)
- **Fase 2 — storage** (`store.py` + árvore `.ai_bridge/interior_consult/`)
- **Fase 3 — endpoints** (`/api/consult/*` no studio_dashboard.py)
- **Fase 4 — dashboard manual bridge** (gerar/copiar pergunta; sidecar consult-liaison)
- **Fase 5 — ingestão de resposta** (`answer_parser.py`)
- **Fase 6 — aprendizado persistente** (`ingest.py` → DNA / judge-rules / tokens / próxima MT / interior_feedback)
- **Fase 7 — OpenAI API backend OPCIONAL** (`openai_client.py`, chave só em env)
- **Fase 8 — Chrome helper EXPERIMENTAL**

---

## Microtarefas — Consult GPT Bridge

### MT-001 — Descobrir estrutura atual ✅
- **Objetivo:** mapear dashboard/server/endpoints/renders/reference_db reais.
- **Arquivos:** (leitura) `tools/studio_dashboard.py`, `tools/reference_db.py`, `docker-compose.yml`.
- **Critério:** seção "Estado atual" preenchida com paths reais. · **Teste:** confere com o repo. · **Risco:** baixo. · **Status:** DONE.

### MT-002 — Criar templates de contrato ✅
- **Objetivo:** templates humanos + JSON Schemas de pergunta/resposta.
- **Arquivos:** `tools/interior_studio/consult_gpt_bridge/contracts/architect_{question,answer}_contract.v1.md` + `contracts/schemas/{question,answer}_contract.schema.json` + `consult_gpt_bridge/README.md`.
- **Critério:** os 5 arquivos existem, schemas válidos, modos SPEC/JUDGE/REPAIR/LEARN/COMPARE documentados. · **Teste:** `python -c "import json,glob; [json.load(open(p,encoding='utf-8')) for p in glob.glob('tools/interior_studio/consult_gpt_bridge/contracts/schemas/*.json')]"`. · **Risco:** baixo. · **Status:** DONE.

### MT-003 — Criar storage local (Fase 2)
- **Objetivo:** `store.py` cria/gerencia a árvore e nomeia `<timestamp>_<slug>`.
- **Arquivos:** `consult_gpt_bridge/store.py`, `consult_gpt_bridge/contracts.py` (dataclasses+validação); dirs `.ai_bridge/interior_consult/{outbox,inbox,answered,ingested,failed,logs}` (com `.gitkeep`) e `.ai_bridge/interior_feedback/{approved,rejected,corrections,golden_samples,anti_patterns}` + `references/felipe/{inbox,approved,rejected,anti_patterns}`.
- **Critério:** salvar pergunta gera `.json`+`.md` no outbox; validação contra schema. · **Teste:** unit `pytest` round-trip save/load. · **Risco:** médio (paths). · **Status:** TODO.

### MT-004 — Criar endpoints consult (Fase 3)
- **Objetivo:** `/api/consult/{state,question,answer,ingest,ask-openai,latest-question,latest-answer}` NO `studio_dashboard.py`, importando `consult_gpt_bridge`.
- **Arquivos:** `tools/studio_dashboard.py` (do_POST/do_GET), `consult_gpt_bridge/prompt_builder.py`.
- **Critério:** `GET /api/consult/state` retorna o shape do brief; `POST question/answer` persistem. · **Teste:** curl/Invoke-RestMethod round-trip; `docker compose restart`. · **Risco:** médio (não quebrar endpoints atuais). · **Status:** TODO.

### MT-005 — Exibir latest question no dashboard (Fase 4)
- **Objetivo:** sidecar `🔌 Consult GPT Bridge` na coluna do Arquiteto: status + última pergunta + botão copiar.
- **Arquivos:** `tools/studio_dashboard.py` (UI inline + JS).
- **Critério:** pergunta gerada aparece e tem botão "copiar pergunta". · **Teste:** visual no `:8782`. · **Risco:** baixo. · **Status:** TODO.

### MT-006 — Permitir colar answer no dashboard (Fase 4)
- **Objetivo:** textarea + botão "colar resposta" → `POST /api/consult/answer`.
- **Arquivos:** `tools/studio_dashboard.py`.
- **Critério:** resposta colada é salva no inbox. · **Teste:** colar exemplo, ver arquivo. · **Risco:** baixo. · **Status:** TODO.

### MT-007 — Ingerir answer_contract (Fase 5)
- **Objetivo:** `answer_parser.py` (md→struct, valida schema) + `POST /api/consult/ingest`.
- **Arquivos:** `consult_gpt_bridge/answer_parser.py`, `ingest.py` (esqueleto), `studio_dashboard.py`.
- **Critério:** extrai veredito + top_fix + dna_updates + anti_patterns + next_microtask. · **Teste:** unit com um answer de exemplo. · **Risco:** médio (parsing tolerante a markdown do GPT). · **Status:** TODO.

### MT-008 — Atualizar Felipe Style DNA (Fase 6)
- **Objetivo:** `ingest.py` aplica `dna_updates` em `.claude/memory/felipe_style_dna.md` SEM duplicar regra.
- **Arquivos:** `consult_gpt_bridge/ingest.py`, `.claude/memory/felipe_style_dna.md`.
- **Critério:** regra nova é anexada; regra repetida é ignorada (dedupe). · **Teste:** ingerir 2× a mesma regra → 1 entrada. · **Risco:** médio. · **Status:** TODO (o DNA já existe; falta o aplicador idempotente).

### MT-009 — Criar style pack (Fase 6, CONDICIONAL)
- **Objetivo:** `interior/style_packs/black_wood_gold_industrial_boutique.json` p/ o `scene_composer` renderizar a SALA no estilo escuro.
- **Arquivos:** `interior/style_packs/black_wood_gold_industrial_boutique.json`.
- **Critério:** `scene_composer.load_style_pack("black_wood_gold_industrial_boutique")` carrega. · **Teste:** import + load. · **Risco:** baixo. · **Status:** TODO **só se** propagar pra SALA (a cozinha já usa o theme congelado — não duplicar lá).

### MT-010 — Gerar pergunta MODE=JUDGE para render existente (Fase 4)
- **Objetivo:** `prompt_builder.build_judge(render, theme, frozen, mutable)` produz um `question_contract` válido.
- **Arquivos:** `consult_gpt_bridge/prompt_builder.py`.
- **Critério:** o exemplo `kitchen_skin_001` (JUDGE) sai válido contra o schema. · **Teste:** valida com o schema. · **Risco:** baixo. · **Status:** TODO.

### MT-011 — Testar fluxo manual completo (Fase 4-6)
- **Objetivo:** ponta-a-ponta offline: gerar→copiar→(ChatGPT)→colar→ingerir→DNA/anti-pattern/próxima MT.
- **Arquivos:** —. **Critério:** os 10 itens de "Critério de pronto" do brief passam. · **Teste:** roteiro manual no `:8782`. · **Risco:** médio. · **Status:** TODO.

### MT-012 — Criar backend OpenAI opcional (Fase 7)
- **Objetivo:** `openai_client.py` + `POST /api/consult/ask-openai` (chave SÓ em `OPENAI_API_KEY`).
- **Arquivos:** `consult_gpt_bridge/openai_client.py`, `studio_dashboard.py`.
- **Critério:** com chave responde; sem chave retorna `{ok:false, fallback:"manual"}` sem quebrar. · **Teste:** rodar sem env (erro amigável) e com env. · **Risco:** médio. · **Status:** TODO.

### MT-013 — Proteger API key (Fase 7)
- **Objetivo:** chave nunca no HTML/JS/commit; `.env` no `.gitignore`; doc de ativação.
- **Arquivos:** `.gitignore`, `consult_gpt_bridge/README.md`, `docker-compose.yml` (env-file).
- **Critério:** `grep -ri "sk-"` no front = 0; `.env` ignorado. · **Teste:** scan. · **Risco:** ALTO se vazar. · **Status:** TODO.

### MT-014 — Documentar Chrome helper experimental (Fase 8)
- **Objetivo:** só documentar o helper (copiar/colar contrato); não rouba sessão/cookies; não-canônico.
- **Arquivos:** `consult_gpt_bridge/README.md` (+ futura `chrome_helper/README.md`).
- **Critério:** doc deixa claro escopo e limites. · **Teste:** revisão. · **Risco:** baixo. · **Status:** TODO.

---

## Microtarefas — track UI (Ciclos · Consult Liaison · polish)
> Independente do bridge; melhora o entendimento da "fábrica". Pode rodar em paralelo às fases 2-6.

### MT-UI-001 — Criar entidade `cycle`
- **Objetivo:** cada clique em "rodar ciclo" gera `cycle_id`; cada msg dos agents carrega `cycle_id`; histórico salvo.
- **Arquivos:** `tools/studio_dashboard.py` (`_cycle`), `tools/studio_log.py` (campo `cycle`), `.ai_bridge/cycles.json`.
- **Critério:** `/api/state.cycles.{current,history}` existe. · **Teste:** rodar ciclo, ver cycle_id. · **Risco:** médio. · **Status:** TODO.

### MT-UI-002 — Painel "Ciclo atual"
- **Objetivo:** painel central abaixo das colunas: timeline PM→Lead→Arquiteto→Consult Liaison, status/resumo/modelos por step.
- **Arquivos:** `tools/studio_dashboard.py`. · **Critério:** mostra os 4 no mesmo ciclo. · **Teste:** visual. · **Risco:** baixo. · **Status:** TODO.

### MT-UI-003 — Histórico colapsável de ciclos
- **Objetivo:** cards `CYCLE-NNN — status — MT` que expandem mostrando a conversa do ciclo.
- **Arquivos:** `tools/studio_dashboard.py`. · **Critério:** abrir/fechar; msgs agrupadas por ciclo. · **Teste:** visual. · **Risco:** baixo. · **Status:** TODO.

### MT-UI-004 — Sidecar Consult Liaison
- **Objetivo:** mini-card na coluna do Arquiteto com status + última pergunta/resposta + copiar/colar.
- **Arquivos:** `tools/studio_dashboard.py` (depende de MT-004/005/006). · **Critério:** os estados do liaison aparecem. · **Teste:** visual. · **Risco:** baixo. · **Status:** TODO.

### MT-UI-005 — Medir uso de modelos
- **Objetivo:** `model_usage` por agent/ciclo + WARN quando um agent concentra >80% das decisões críticas num modelo.
- **Arquivos:** `tools/studio_dashboard.py`, `tools/studio_log.py`. · **Critério:** `/api/state.model_usage` + `consensus_warnings`. · **Teste:** simular 12 DeepSeek → WARN. · **Risco:** médio. · **Status:** TODO.
- **Regra:** decisão `visual_critical` (material/luz/composição/PASS-WARN-FAIL/style-DNA/anti-pattern/render-final/aprovação de cômodo) exige ≥2 modelos locais OU justificativa OU acionar consult-liaison.

### MT-UI-006 — Padronizar labels/status
- **Objetivo:** header de agent em CSS grid (`36px 1fr auto auto`); `.status-pill{min-width:64px}`; `.model-status{min-width:58px}`; cards de subagente com altura consistente; chat agrupado por ciclo.
- **Arquivos:** `tools/studio_dashboard.py` (CSS+render). · **Critério:** headers alinhados, pills largura fixa. · **Teste:** visual. · **Risco:** baixo. · **Status:** TODO.

---

## Requisitos de qualidade (invariantes)
1. Não quebrar o `:8765`. 2. Não misturar NOC com Interior Studio. 3. MVP funciona sem internet/OpenAI.
4. OpenAI só opcional. 5. Chave só em env. 6. Nenhuma chave no front. 7. Sem arquivo gigante à toa.
8. Contratos legíveis. 9. Aprendizado versionável. 10. Toda decisão gera rastreabilidade.

## Próximo passo
Fase 2 (MT-003: `store.py` + árvore de storage). Só depois Fase 3 (endpoints). OpenAI (Fase 7) e Chrome
(Fase 8) por último. O track UI (MT-UI-*) pode começar em paralelo a partir de MT-UI-001.
