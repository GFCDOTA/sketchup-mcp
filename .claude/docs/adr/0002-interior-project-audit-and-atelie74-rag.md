# ADR-0002 — Interior Project Audit (buildability gate) + Ateliê 74 (chat com RAG)

- **Status:** Accepted / LIVE
- **Data:** 2026-08-09 → 2026-08-10
- **Deciders:** Felipe (owner) + Claude (modo B — autonomia delegada) + GPT-Docker (consulta técnica)
- **Escopo:** duas peças novas de arquitetura que nasceram na mesma sessão longa —
  (1) um gate de **buildability** pro trabalho de interiores (skill + agent),
  (2) um assistente de chat com **memória vetorial (RAG)** embutido no painel
  local do estúdio. Não cobre o pipeline PDF→SKP em si (ver ADR-0001).

---

## Contexto

O BANHO 01 (planta_74, tema STONE_MONOLITH) já tinha passado pelo veredito
visual do GPT/Felipe e estava "aprovado" (9.2–9.6). Mas uma auditoria mais
rigorosa — pedida ao GPT-Docker vestindo o papel de arquiteto real, com
browsing de referência construída antes de opinar — revelou que **aprovação
visual não é o mesmo que projeto executável**: vãos de teto abertos, luz
decorativa não-embutida, acessórios sem identidade de produto, aperto
dimensional não conferido. A regra que emergiu dessa consulta:

> **"Render bonito nunca pode transformar projeto tecnicamente incompleto em
> aprovado."**

Em paralelo, o painel local do estúdio (`ops/estudio-front/`, iFood-style,
já existente) precisava de duas coisas que o Felipe pediu explicitamente
durante a sessão: (a) mostrar **o que o agente está fazendo agora**, ao vivo
(não só histórico), e (b) um jeito de ele **conversar e ensinar seu gosto**
sem precisar chamar o Claude toda vez — virando **memória persistente e
consultável**, não uma lista estática de regras hardcoded.

## Decisão

### 1. `interior-project-audit` (skill) + `interior-project-auditor` (agent)

Um pipeline de **12 gates sequenciais** que separa 3 sinais nunca misturados:

```yaml
design_score: 0..10          # estética/conceito
visualization_score: 0..10   # qualidade do render
execution_status: PASS | WARN | FAIL   # construtibilidade
```

`execution_status: FAIL` **bloqueia** `DESIGN_LOCKED` mesmo com nota visual
alta. Gates: benchmark de referência real → geometry truth → product reality
(SKU real, não genérico) → assembly fit (conjunto, não peça isolada) →
ergonomia com fonte obrigatória → MEP (hidráulica/elétrica, nunca inventada)
→ wet area → fabrication → design intent (mata feature cujo propósito é só
"ficar bonito no render") → lighting as function → auditoria 360° (hero
sozinho não representa o cômodo) → project close.

Postura obrigatória (pedido explícito do Felipe): **"olhos de águia"**
(escrutínio ativo, não espera o óbvio) + **consultoria de loja de
mobiliados** (todo FAIL/WARN vem com sugestão de produto/solução concreta,
não só o diagnóstico).

**Resultado real, não hipotético:** rodar essa auditoria (via `general-purpose`
seguindo a persona, já que o agent nomeado só carrega em sessão nova do
harness) achou e um fix subsequente **corrigiu**:
- bug de escala 1.36× silencioso (`core/scale.py::assert_pt_to_m_for_source`,
  guard fail-fast — pegou 3 arquivos de teste que só passavam por sorte de
  ordem de import);
- causa raiz do "céu vazando no teto" (buffer geométrico com join_style
  `round` gerando polígono degenerado → `add_face` do SketchUp retornando
  `nil` → erro engolido em silêncio pelo `rescue StandardError` do `.rb`);
- gap vertical de 20cm entre painel de parede e teto (mesma família de bug).

### 2. Ateliê 74 — chat com memória vetorial (RAG) no painel local

Arquitetura (ver diagrama de fluxo em `docs/diagrams/`):

```
Fontes de conhecimento (texto)
    → chunk (1200 chars / 150 overlap)
    → embedding (Ollama nomic-embed-text, 768d)
    → Qdrant (vector DB, já rodava no projeto pro RAG de fidelidade)
    → retriever (busca por similaridade, 2 coleções em paralelo)
    → modelo de chat (Ollama llama3.1:8b) monta a resposta com o contexto
    → Felipe conversa, e clica "salvar" no que quer virar memória permanente
```

**Duas coleções Qdrant, deliberadamente separadas:**
- `felipe_preferences` — gosto pessoal, só cresce quando o Felipe clica
  "salvar" explicitamente (nunca automático).
- `knowledge_base` — regras técnicas + decisões anteriores do projeto
  (`felipe_visual_judge_rules.json`, a skill `interior-project-audit`,
  `HANDOFF.md`, `ITERATIONS.md`), indexadas por `knowledge_ingest.py`.
- Nenhuma das duas mexe no `rag_chunks` (RAG de fidelidade do pipeline
  PDF→SKP, ADR-0001) — são domínios diferentes, coleções diferentes.

**Decisão de modelo de chat:** `llama3.1:8b`, não o modelo Ollama chamado
`interior-designer` que já existia na máquina. Motivo: aquele modelo tem
Modelfile fixado pra sempre devolver JSON de layout de móveis (uso interno
do `furnish_apartment.py`) — testado e confirmado que não serve pra
bate-papo solto.

**Rebrand:** o painel virou "Ateliê 74" (era só "Estúdio — planta_74", sem
identidade). Paleta trocada duas vezes a pedido do Felipe: primeiro pra
BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE (a mesma linguagem dos renders — achou
"coisa de veio"), depois pra dark moderno estilo dashboard (Linear/Vercel:
preto quase puro + accent único indigo elétrico, sans-serif, sem gradiente
dourado).

## Consequências

**Positivas:**
- Buildability agora é um eixo auditável e travado por teste automático
  (`test_ceiling_polygon_is_valid_simple`, `test_wall_panels_reach_ceiling_no_gap`)
  — não depende mais só de olho humano encontrar por acaso.
- O painel deixou de ser só um dashboard de leitura e virou um canal de
  captura de preferência de baixo atrito — Felipe ensina gosto conversando,
  não preenchendo formulário.
- Reuso deliberado de infra que já existia (Qdrant, Ollama) em vez de nova
  dependência — zero pacote novo no `requirements`.

**Riscos assumidos conscientemente:**
- Qdrant e Docker Desktop **não sobem sozinhos com o Windows** hoje — se a
  máquina reiniciar, alguém precisa religar o Docker Desktop antes do chat
  funcionar (o container em si tem `restart: unless-stopped`, mas depende do
  daemon estar de pé). Decisão consciente de não configurar autostart nesta
  sessão (mudaria a política "sobe por sessão, sem watchdog" herdada do
  aprendizado do NOC — ver `LESSONS-NOC.md`) sem pedido explícito.
- `knowledge_base` hoje só tem texto já existente no repo (regras + decisões).
  **Não há nenhum PDF real indexado ainda** — `tools/pdf_knowledge/` tem o
  extrator pronto (`ingest_pdfs.py`, usa `pypdf`) e `knowledge_ingest.py` tem
  `index_jsonl()` esperando o output dele, mas falta o Felipe fornecer PDFs
  reais em `references/pdfs/` pra fechar esse elo.
- Light slot vertical do BANHO 01 permanece sem embutir de verdade — decisão
  consciente de não arriscar um refactor 3D numa feature cuja permanência no
  projeto nem está decidida (recomendação do GPT-Docker, aceita).

## Referências

- `HANDOFF.md` (raiz do repo) — estado detalhado sessão a sessão.
- `.claude/skills/interior-project-audit/SKILL.md`
- `.claude/agents/interior-project-auditor.md`
- `ops/estudio-front/rag_chat.py`, `knowledge_ingest.py`
- `core/scale.py::assert_pt_to_m_for_source`
- `docs/diagrams/2026-08-09-session-mindmap.md`,
  `docs/diagrams/2026-08-09-rag-flowchart.md`
