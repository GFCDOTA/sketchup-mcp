# Sistema Agêntico Autônomo — retrospectiva 2026-05-31 + roadmap + RAG bebê-spec

> O que começou como *"dá pra você abrir/conversar com outra sessão?"* virou um **sistema
> agêntico que trabalha a fidelidade da planta sozinho, com guarda-corpos.** Doc de captura
> + arquitetura + oportunidades + spec bebê de RAG-grounding.

## TL;DR — o que isso virou
Um **agente autônomo (agentic AI)** que: consulta um **oráculo** (Claude headless via gate
HTTP `:8765`) nas decisões; **verifica com detectores determinísticos** (não confia em
opinião); **chama o humano só no que ele não sabe julgar** (`VISUAL_REVIEW` — aparência da
planta); **commita / mergeia / limpa branch sozinho** (gh-autopilot); **registra lição**; e
**não para à toa**. **NÃO é RAG. NÃO é "um LLM".** O LLM é o *motor*; o sistema é a
**engenharia em volta** — e é ela que separa "brinquedo que alucina" de "coisa que roda
sozinha sem corromper".

## A jornada (de um gate a um sistema)
1. **Semente:** "dá pra conversar com outra sessão?"
2. **Bridge Claude↔Claude:** o gate consulta por **HTTP `:8765`** (não arquivo). Subimos um
   **server `claude -p`** atrás do `:8765` → o Claude responde as consultas da sessão de
   trabalho, na assinatura, **sem API key**.
3. **Watchdog:** loop que distingue **progresso vs patinagem** (git/artifacts).
4. **Modo B (autonomia delegada):** o oráculo decide TUDO menos o visual; único gate humano
   = `VISUAL_REVIEW`. (Provado: o oráculo se RECUSOU a auto-aprovar mutação de fixture até a
   gente flipar pra B — e mesmo em B reserva o visual. Auto-proteção sadia.)
5. **Skill `autonomous-fidelity-loop`:** o loop canônico, com **log por ciclo**.
6. **O ciclo fechou SOZINHO:** a sessão regenerou o consensus (#28), flaggou `VISUAL_REVIEW`,
   o Felipe aprovou (**IMPROVED**), e ela **promoveu a fixture canônica** sozinha (pytest 246,
   janelas painel→aperture vazado). Loop humano-no-meio fechado **sem kick**.
7. **gh-autopilot:** auth via `GH_TOKEN` (fine-grained PAT), **gotcha dos 366 dias da org**,
   auto-merge + cleanup de branch. Auto-land provado (push direto, `Contents:RW`).
8. **Specs:** `gate_framework_and_audit` (gates modulares + audit core + worker + multi-oracle)
   — e a sessão **já está implementando** (file-fetch §6.3 landado).

## A arquitetura (padrões com nome)
| Padrão | No nosso sistema |
|---|---|
| **Agente + tool use** | Claude Code que edita/commita/testa/mergeia |
| **Control loop** | sense → decide → act → **verify** → log → repeat (com stop honesto) |
| **LLM-as-advisor + determinístico-as-judge** | o gate aconselha; o detector julga |
| **Human-in-the-loop (HITL)** | `VISUAL_REVIEW` pro que a máquina não sabe (visual) |
| **Blackboard / memória por arquivo** | `.ai_bridge` / HANDOFF |
| **Self-improvement por memória escrita** | `lessons_learned` (não é weight-learning) |
| **Multi-agente** | sessão de trabalho + oráculo + overseer + humano |

## O que roda sozinho HOJE × precisa de humano
- **Sozinho:** decisão técnica (gate), correção do determinístico, commit, PR-via-push,
  merge, cleanup de branch, registro de lição, parada honesta.
- **Humano (de propósito):** `VISUAL_REVIEW` (aparência / fixture canônica), `gh auth` (1×),
  o OK do worker lights-out.

## Limites honestos (não fingir)
- **Peer-Claude NÃO é check independente** (mesmo viés de modelo) → por isso o multi-oracle.
- **Visual não se autojulga** (negative_dogfood: PASS confiante com parede apagada).
- **"Aprender" = memória escrita**, não rede neural.
- **Sessão parada precisa de um turno** (até o worker existir).
- **Lights-out (worker) é o maior passo de autonomia** → exige OK explícito.

## Oportunidades / roadmap (por ROI)
1. **Worker headless** (gate-spec fatia 5) → fim das paradas; o loop se re-lança sozinho.
2. **Multi-oracle** → independência real (Claude + ChatGPT + local + determinístico).
3. **PRODUTO — generalizar pra QUALQUER planta** (hoje é planta_74-específico). O salto que vale.
4. **Representação visual** do planta_74 (porta/vidro/legibilidade — via `VISUAL_REVIEW`).
5. **RAG-grounding** (spec abaixo).

> 🧭 **Bússola:** o motor é MEIO; o FIM é o `.skp` **fiel ao PDF, pra qualquer planta.**
> Não virar meta-eterno construindo infra-de-infra.

---

## Spec bebê — RAG-grounding
**Problema:** o oráculo (e o agente) é **cego a artefato** → chuta fato (errou a previsão de
render porque não via a geometria). O `file-fetch` (gate spec §6.3, já landado) é o bebê
**manual**. RAG **automatiza**: recupera o contexto certo e embasa a resposta.

**Design — local, grátis, sem API key (alinha com o modo de operação):**
- **Fontes a indexar:** `fixtures/*/consensus*.json`, `geometry_report.json`,
  `.claude/memory/lessons_learned.md`, HANDOFF, `.claude/specs/*`, docstrings de `tools/*.py`,
  texto extraído do `planta_74.pdf`.
- **Embeddings locais:** `sentence-transformers` (ex.: all-MiniLM) ou embeddings do Ollama —
  **sem chave de API**.
- **Store:** `chroma` ou `faiss` local (arquivo gitignorado).
- **Retrieve:** a pergunta do gate / a tarefa do loop → **top-k chunks** relevantes.
- **Inject:** prepend os chunks no prompt do oráculo/agente → ele responde **embasado**.

**Fatias (cada uma = commit + teste + audit):**
1. `tools/rag_index.py` — chunk + embed + store (idempotente, re-index on change).
2. `tools/rag_query.py` — query → top-k (CLI + import).
3. Plugar no gate: antes de `build_prompt`, recuperar top-k e anexar → vira o §6.3 **automático**.
4. Plugar no loop: cada fatia recupera lições/specs relevantes antes de agir.
5. Teste: golden queries (pergunta conhecida → chunk esperado).

**Não-objetivos (bebê):** sem re-ranking fancy, sem multi-hop, sem grafo. Começa simples:
embeddings locais + top-k + inject. Cresce **se** provar valor — e o **audit-core** mede isso
(replay/diff: resposta com RAG ficou melhor?).

**Por que casa com o resto:** RAG mata o limite honesto #2 do gate (cego a artefato); o
audit-core mede se ajudou; **multi-oracle + RAG = oráculo embasado E independente.** É a
evolução natural do file-fetch — o bebê vira adulto.
