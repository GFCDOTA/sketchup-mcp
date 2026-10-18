# Classificação do conhecimento — sketchup-mcp

> Fase A da consolidação (ver `.claude/plans` / handoff da sessão de
> 2026-08-11). Este documento é a base para a Fase B decidir o que entra no
> RAG unificado (`tools/knowledge_api.py`, ainda não implementado) e o que
> fica fora. Não é uma lista exaustiva de arquivos — é uma classificação
> conceitual aplicada às fontes reais já identificadas na auditoria técnica
> da `develop`.

## As 6 categorias

| Categoria | Definição | Pergunta-teste |
|---|---|---|
| **Conhecimento recuperável** | Fato ou regra estável, útil pra responder uma pergunta futura fora do contexto em que foi criado. | "Se eu perguntar isso daqui a 3 meses, essa fonte ainda responde certo?" |
| **Log** | Registro operacional de execução (o que rodou, quando, com que resultado bruto). Útil pra debug/auditoria, não pra responder pergunta de design. | "Isso é sobre o SISTEMA rodando, ou sobre a CASA?" |
| **Estado atual** | Snapshot do estado presente de algo (geometria, cena, gate). Substituído a cada rodada — não tem valor histórico por si só. | "Esse arquivo é sobrescrito na próxima execução?" |
| **Decisão histórica** | Um "isso foi escolhido, por este motivo, nesta data" — sobrevive à mudança de estado. | "Isso captura um PORQUÊ, não só um O QUÊ?" |
| **Preferência** | Gosto pessoal do Felipe, não-obrigatório, pode mudar, nunca é regra técnica. | "Isso é sobre o que ELE GOSTA, ou sobre o que é EXIGIDO?" |
| **Regra obrigatória** | Constraint técnica/normativa que não pode ser violada por gosto. | "Uma preferência pode legitimamente contradizer isso?" |

## Aplicação às fontes reais do repo

| Fonte | Categoria | `KnowledgeType` (Fase A) | Entra no RAG unificado? |
|---|---|---|---|
| `.claude/memory/felipe_style_dna.md` | Preferência | `PREFERENCE` | Sim — já é fonte de `rag_freshness.SOURCES` (`style_dna`) |
| `references/tokens/*.json` | Conhecimento recuperável | `REFERENCE` | Sim — já indexado (`token`) |
| `references/design_rules/felipe_visual_judge_rules.json`, `furniture_rule_cards.json` | Regra obrigatória | `TECHNICAL_RULE` | Sim — já indexado (`design_rule`) |
| `references/felipe/anti_patterns/*.json` | Regra obrigatória | `TECHNICAL_RULE` | Sim — já indexado (`anti_pattern`) |
| `references/felipe/verdicts/*.json` | Decisão histórica | `HUMAN_VERDICT` | Sim — já indexado (`human_verdict`) |
| `fixtures/planta_74/semantic_zones.json` | Regra obrigatória (mapeamento espacial normativo) | `TECHNICAL_RULE` | Sim — já indexado (`semantic_zones`) |
| `.ai_bridge/learning_patches/*.json` | Decisão histórica (quando `status=applied`) | `PROJECT_DECISION` | Sim — já indexado (`learning_patch`); **drafts não aplicados não deveriam pesar como decisão firmada** — ver nota abaixo |
| `fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json` | Fato estrutural imutável, não "conhecimento" no sentido deste enum | *(sem tipo — deliberadamente fora)* | Já indexado como `consensus` no `rag_freshness.SOURCES`, mas **não recebe `KnowledgeType`** — é geometria de planta, não algo que se "prefere" ou "decide", é dado de entrada fixo |
| `HANDOFF.md` (raiz do repo) | **Misto** — narra decisão histórica + log operacional + estado da sessão no mesmo arquivo | — | **Não entrar cru.** Precisa de extração seletiva (Fase B): só os parágrafos de decisão ("por que fizemos X") viram `PROJECT_DECISION`; o resto ("rodei pytest, deu 1258 passed") é log, fica de fora |
| `ITERATIONS.md` (`artifacts/estudio_banheiro/`) | **Misto** — tabela `Iter/Nota/Veredito/Mudanças` é decisão histórica + veredito humano; texto solto ao redor é log de sessão | — | A **tabela estruturada** vira `HUMAN_VERDICT`/`ITERATION_RESULT` (idealmente via o schema novo `IterationResult`, Fase E, não via embedding cru de markdown); o texto de sessão fica de fora |
| `artifacts/estudio_banheiro/iterations/gates.json` | Estado atual (snapshot único de `geometry_sanity`, sem `iteration_id`) | — | **Não** — é estado, substituído a cada rodada, sem valor recuperável isolado. Só tem valor se amarrado a um `IterationResult` (Fase E) |
| `artifacts/estudio_banheiro/iterations/scene.json` | Estado atual (câmera/placements da cena corrente) | — | **Não**, mesmo motivo acima |
| `felipe_preferences` (Qdrant, via `rag_chat.save_preference`) | Preferência | `PREFERENCE` | Sim, mas **continua em collection própria** (Princípio 2 permite múltiplas collections) — agregada pela mesma API, não pelo mesmo índice físico |
| `ops/estudio-front/chat_history.json` | Log (histórico de conversa bruto) | — | **Não** — é log de sessão de chat, não conhecimento de design |
| `ops/estudio-front/status.json` | Estado atual | — | **Não** |
| Renders individuais (`artifacts/**/*.png`) | Artefato, não texto — fora do escopo deste RAG textual | — | Não (RAG de imagem é outro problema, não coberto aqui) |

## Nota sobre `learning_patch` com `status=draft`

`tools/interior_studio/learning_patch.py` confirma 3 estados possíveis:
`draft` (proposto, não aprovado), `applied` (aprovado e já refletido no DNA),
`rejected`. Um patch em `draft` **não é uma decisão firmada** — é uma
proposta pendente de humano. Recomendação para a Fase B: filtrar
`learning_patch` no indexador para só entrar como `PROJECT_DECISION` quando
`status in {"applied", "rejected"}` (rejeitado também é decisão — "isso foi
considerado e recusado, por este motivo" tem valor recuperável); `draft`
fica de fora do corpus até virar uma das duas.

## O que isso NÃO resolve (fica para a Fase B)

Este documento classifica — não implementa extração/ingestão. A Fase B
precisa decidir, arquivo a arquivo dos casos "mistos" (`HANDOFF.md`,
`ITERATIONS.md`), a heurística de extração (seção por seção? só as tabelas?
um parser dedicado?). Este doc só define o alvo: o que deveria virar
conhecimento recuperável versus o que deveria continuar sendo lido só por
humanos.
