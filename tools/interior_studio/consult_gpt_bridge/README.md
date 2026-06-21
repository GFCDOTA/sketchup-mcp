# consult_gpt_bridge

Ponte de pergunta/resposta ESTRUTURADA entre o **Arquiteto de Interiores** (Interior Studio, `:8782`)
e um consultor externo chamado **Consult GPT**. O objetivo é um loop real de aprendizado visual:

```
Arquiteto gera pergunta estruturada (ARCHITECT_QUESTION_CONTRACT)
  → Consult GPT responde como crítico/arquiteto (ARCHITECT_ANSWER_CONTRACT)
  → o sistema ingere e vira: regra / anti-pattern / token / atualização do Felipe Style DNA / próxima microtarefa
  → próximo ciclo gera um render melhor.
```

> **Regra central:** referência manda na LINGUAGEM visual · PDF/planta manda na GEOMETRIA · gates mandam em
> segurança/escala/circulação · **Felipe dá o PASS final**. O Consult GPT é consultor — nunca move parede,
> janela, porta, shaft, pia fixa ou elemento congelado do PDF, e o veredito visual dele é parecer, não decisão.

## Status
**Fase 0 (descoberta) + Fase 1 (contratos): FEITAS.** Storage, endpoints, ingest e backend OpenAI ainda
NÃO existem — ver `.ai_bridge/interior_consult/HANDOFF.md` para o plano de microtarefas e a ordem das fases.

## 3 níveis de operação (robusto → frágil)
1. **Manual Contract Bridge (MVP obrigatório, offline).** O `consult-liaison` monta o contrato de pergunta;
   o dashboard mostra; o Felipe copia/cola no ChatGPT; cola a resposta de volta; o sistema ingere. **Sem
   OpenAI API, sem extensão, sem automação frágil.**
2. **Local OpenAI Backend (opcional, depois).** Um backend Python chama a OpenAI API. **A chave vive SÓ em
   `OPENAI_API_KEY` (env), nunca no frontend, nunca commitada.** Se a chave não existir, o endpoint retorna
   erro amigável e sugere o Manual Bridge — nunca quebra.
3. **Chrome Helper (experimental, por último).** Só facilita copiar/colar contratos entre o dashboard local
   e uma aba do ChatGPT. NÃO rouba sessão/cookies/credenciais. Não-canônico.

## Contratos (Fase 1, prontos)
- [`contracts/architect_question_contract.v1.md`](contracts/architect_question_contract.v1.md) — template humano da pergunta.
- [`contracts/architect_answer_contract.v1.md`](contracts/architect_answer_contract.v1.md) — template humano da resposta.
- [`contracts/schemas/question_contract.schema.json`](contracts/schemas/question_contract.schema.json) — JSON Schema (draft 2020-12) da pergunta.
- [`contracts/schemas/answer_contract.schema.json`](contracts/schemas/answer_contract.schema.json) — JSON Schema da resposta.

### Modos da pergunta
`SPEC` (sem imagem, definir direção) · `JUDGE` (julgar render PASS/WARN/FAIL) · `REPAIR` (correção mínima) ·
`LEARN` (virar feedback do Felipe em memória/regra) · `COMPARE` (escolher a melhor entre 2+ versões).

## Módulos planejados (Fase 2+, ainda NÃO implementados)
| arquivo | papel | fase |
|---|---|---|
| `contracts.py` | dataclasses + validação contra os schemas | 2 |
| `store.py` | persistência em `.ai_bridge/interior_consult/{outbox,inbox,answered,ingested,failed,logs}` | 2 |
| `prompt_builder.py` | monta o `question_contract` a partir do estado do Arquiteto | 3 |
| `answer_parser.py` | parseia o `answer_contract` (md → struct) e valida | 5 |
| `ingest.py` | resposta → DNA / anti-patterns / tokens / próxima microtarefa / interior_feedback | 6 |
| `openai_client.py` | backend opcional (`OPENAI_API_KEY` em env) | 7 |

## Endpoints planejados (Fase 3+, no server do Interior Studio — NÃO num server novo)
`GET /api/consult/state` · `POST /api/consult/question` · `POST /api/consult/answer` ·
`POST /api/consult/ingest` · `POST /api/consult/ask-openai` · `GET /api/consult/latest-question` ·
`GET /api/consult/latest-answer`.

> **Decisão de arquitetura (ver HANDOFF MT-004):** os endpoints `/api/consult/*` entram no server que JÁ
> existe (`tools/studio_dashboard.py`, que serve o `:8782`), importando este pacote — NÃO num
> `tools/interior_studio/server.py` paralelo (evita conflito de porta e fragmentação do serviço). O NOC
> técnico `:8765` fica intocado.

## Como ATIVAR a OpenAI API depois (Fase 7, quando chegar a hora)
1. `export OPENAI_API_KEY=sk-...` no ambiente do server (no Docker: passar via `environment:` do compose
   ou `--env-file`, **nunca** no `dashboard.html`/JS).
2. `OPENAI_API_KEY` ausente → `POST /api/consult/ask-openai` responde `{"ok": false, "error": "...", "fallback": "manual"}`.
3. `.env` fica no `.gitignore`; nenhuma chave em HTML/JS/browser/commit.
