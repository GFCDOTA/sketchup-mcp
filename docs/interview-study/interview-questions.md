# Interview Questions

8 perguntas construídas em cima dos problemas reais desta sessão. Formato:
**QUESTION** → **WHAT INTERVIEWER IS TESTING** → **GOOD ANSWER** →
**STAFF-LEVEL ANSWER** → **PROJECT EXAMPLE**.

---

### Q1. How would you prevent an optimizer and a validator from implementing different versions of the same business rule?

**What interviewer is testing**: entendimento de single source of truth em
sistemas com um caminho de "proposta" (otimização, heurística) separado do
caminho de "decisão final" (validação, CI).

**Good answer**: fazer o optimizer importar/chamar a mesma função de
validação que o CI usa, em vez de reimplementar uma versão "rápida" da regra.

**Staff-level answer**: isso sozinho não basta — a implementação pode
divergir DE NOVO no futuro (alguém adiciona um atalho no optimizer "por
performance"). A defesa real é um contrato de PROVENANCE testável: toda
decisão do optimizer registra QUAL implementação canônica validou o
candidato (nome + versão), e um gate separado reavalia essa decisão contra
o estado FINAL, comparando com o que foi gravado. Divergência vira FAIL
determinístico, não depende de code review pegar a próxima duplicação.

**Project example**: `tools/optimizer_consistency_gate.py` — 3 camadas
(implementação única, provenance persistida em
`out["placement_decisions"]`, reavaliação do gate canônico no estado
final). Achado ao vivo: `tools/correction_fixes.py` tinha uma cópia própria
da regra de colisão que quebrou quando a canônica mudou — a motivação do
gate virou realidade no mesmo dia em que foi escrito.

---

### Q2. When should a system fail fast instead of attempting recovery?

**What interviewer is testing**: julgamento sobre custo de erro silencioso
vs custo de parar.

**Good answer**: fail fast quando o estado inválido, se não detectado
imediatamente, se PROPAGA (mais dados gerados em cima do erro, decisões
tomadas confiando nele) — nesse caso, o custo de detectar tarde cresce com
o tempo.

**Staff-level answer**: a decisão não é binária "sempre falha rápido" — é
sobre se o sistema consegue distinguir "estado corrigível localmente" de
"estado que compromete a integridade de tudo que vem depois". Config
inválida no startup e escala numérica errada (que gera geometria fisicamente
errada silenciosamente) são fail-fast; um item individual malformado numa
lista de 1000 pode logar e continuar, se os outros 999 são independentes.

**Project example**: `core/scale.py` — `PT_TO_M` (escala pontos→metros) lida
uma vez por processo; usar o valor errado gera geometria 36% maior sem
NENHUM sintoma imediato (só visualmente, depois, quando um humano nota
"os móveis estão flutuando fora do shell"). Fix: `RuntimeError` explícito
comparando escala ativa vs verificada, ANTES de qualquer geometria ser
gerada.

---

### Q3. How would you distinguish legacy constraints from regressions introduced by a new system?

**What interviewer is testing**: raciocínio sobre baseline vs delta em
sistemas de validação/SLO.

**Good answer**: medir o estado ANTES da mudança (baseline) e comparar o
estado DEPOIS contra esse baseline, não contra um alvo absoluto.

**Staff-level answer**: o modelo de decisão precisa de DOIS thresholds
diferentes — um "alvo ideal" (o que se quer) e uma "tolerância de não-
piora" (quanto o sistema pode degradar um baseline já ruim antes de contar
como regressão). Confundir os dois produz dois erros opostos: ou se
bloqueia indevidamente um estado legado que ninguém pode consertar
rapidamente, ou se permite piora progressiva porque "já estava ruim mesmo".

**Project example**: `tools/circulation_gate.py`, tier `shell_estreito` —
`if empty_shell >= target: furnished must remain >= target; else:
furnished must not worsen empty_shell beyond tolerance` (`GEOMETRY_TOLERANCE_M
= 0.02m`, `core/project_policy.py`). Um corredor que a PLANTA já entrega
com 0.75m vira `PASS_WARN_BASE_GEOMETRY`, não bloqueia; o mesmo corredor
piorado pela mobília pra 0.72m vira `FAIL_FURNITURE_WORSENS_BASE_GEOMETRY`.

---

### Q4. What should be the source of truth in a RAG-based application?

**What interviewer is testing**: entendimento de que retrieval != autoridade,
comum em sistemas agentic mal desenhados.

**Good answer**: código/configuração versionada é a fonte de verdade
executável; o RAG é um índice de busca sobre documentação/decisões, não um
banco de regras de negócio.

**Staff-level answer**: definir uma hierarquia EXPLÍCITA (código/config/
testes > ADR/decisões documentadas > índice RAG > síntese do LLM) e garantir
mecanicamente que o caminho crítico (CI, autorização, pricing) nunca tem o
RAG como dependência — se o vector store cair, o sistema crítico continua
decidindo sozinho. Adicionalmente, tratar staleness como problema de
primeira classe: metadata de `status: active/superseded` no chunk, não
confiar que "mais parecido semanticamente" = "mais atual".

**Project example**: `core/project_policy.py` (não RAG) guarda os
thresholds numéricos com metadata de source/scope/applicability; o RAG do
projeto (Qdrant) guarda o RACIONAL da decisão pra busca humana, mas nenhum
gate de CI consulta o RAG pra decidir PASS/FAIL — `rag_required_for_ci:
false` é um critério de aceite literal desta sessão.

---

### Q5. When should something become an autonomous agent versus a reusable tool or workflow?

**What interviewer is testing**: disciplina de arquitetura em sistemas
multi-agente — a tendência natural é super-criar agentes.

**Good answer**: um agente se justifica quando há julgamento/iteração
genuína envolvida (a tarefa não tem resposta determinística única). Uma
operação com resposta certa/errada calculável é uma função, não um agente.

**Staff-level answer**: quatro critérios objetivos — (1) existe uma
responsabilidade AUTÔNOMA nova (não uma tarefa nova disfarçada); (2) o
owner atual é genuinamente inadequado pra essa responsabilidade; (3) a
autoridade não se sobrepõe a nenhum agente/gate existente; (4) há um
contrato claro de entrada/saída. Sem os 4, é uma skill (processo reusável)
ou um gate (invariante determinística), não um agente novo.

**Project example**: esta sessão implementou 3 gates novos
(`semantic_geometry_contract_gate`, `collision_envelope_gate`,
`optimizer_consistency_gate`) e explicitamente NÃO criou nenhum agente
(`circulation-agent`, `bathroom-agent`, `geometry-agent`) — circulação e
colisão têm resposta calculável sem ambiguidade, isso é lei (gate), não
julgamento autônomo.

---

### Q6. How do you prevent stale retrieved knowledge from overriding executable policy?

**What interviewer is testing**: profundidade na governança de RAG além do
básico "RAG não é fonte de verdade".

**Good answer**: sempre validar/reconciliar o que o RAG recupera contra o
estado atual do código antes de agir sobre isso.

**Staff-level answer**: versionar os chunks com `stable_id` (identidade
conceitual estável) + `source_commit` (proveniência) + `status: active|
superseded`; o retriever DEFAULT só busca `status=active` — uma decisão
substituída marca a anterior como superseded em vez de deixar duas
"verdades" concorrentes competindo por similaridade de embedding (que não
tem NENHUMA relação com qual é mais atual).

**Project example**: proposto (não implementado nesta sessão — ver
pendências no HANDOFF) como padrão de metadata pro RAG deste projeto; a
mitigação REAL implementada foi mover os thresholds numéricos pra fora do
RAG completamente (`core/project_policy.py`, código versionado), removendo
a superfície de staleness pro dado mais crítico.

---

### Q7. How would you design semantic metadata for entities whose physical representation does not determine their behavior?

**What interviewer is testing**: domain modeling — separar "forma" de
"significado" quando os dois não coincidem 1:1.

**Good answer**: um campo de enum/tag explícito declarando a intenção
(ex. `type: "decorative"`), setado no momento de criação, não inferido
depois por inspeção da estrutura.

**Staff-level answer**: identificar que "comportamento" muitas vezes não é
UMA dimensão — separar em múltiplos eixos ORTOGONAIS quando perguntas
diferentes exigem respostas diferentes pro mesmo objeto (ex.: um tapete
responde diferente pra "bloqueia passagem?" [circulação] vs "conta como
volume sólido?" [overlap] vs "forma é válida?" [geometria]). Um único campo
"tipo" força a modelar a UNIÃO de todas essas perguntas, que degrada pra
`if type == X and check == Y: special_case()` assim que a segunda exceção
aparece.

**Project example**: `core/spatial_semantics.py` — `interaction_policy` é
um dict POR DOMÍNIO (`circulation`, `furniture_overlap`), não um enum
único; a proposta inicial (`collision_policy: SOLID|FOOTPRINT|IGNORE`, um
campo só) foi revisada e rejeitada em favor disso durante a consulta de
arquitetura desta sessão — documentado como divergência explícita no
`HANDOFF.md`.

---

### Q8. How do you design CI gates that are strict without generating false failures on immutable legacy constraints?

**What interviewer is testing**: equilíbrio entre rigor e pragmatismo em
sistemas de gate — gate rígido demais gera "fadiga de alarme falso" e times
passam a ignorar/burlar; gate frouxo demais deixa passar regressão real.

**Good answer**: distinguir estados intermediários (WARN) de PASS/FAIL
puro, pra sinalizar débito conhecido sem bloquear indevidamente.

**Staff-level answer**: dar ao WARN um caminho de MIGRAÇÃO explícito — não
é "warn pra sempre", é "warn até uma condição objetiva de corte" (uma flag,
uma data, um contador zerando). Sem isso, WARN vira ruído permanente que
ninguém mais lê. Combinar com granularidade fina: nem todo objeto sem
contrato declarado é igualmente arriscado — geometria simples sem contrato
é baixo risco (herda um default conservador seguro); geometria complexa
(rotacionada, não-retangular) sem contrato é alto risco (o default não tem
como saber se é intencional).

**Project example**: `tools/semantic_geometry_contract_gate.py` — 3 estados
(`PASS`/`WARN_LEGACY_SEMANTICS`/`FAIL_MISSING_SEMANTICS`), onde WARN só se
aplica a formas simples (baixo risco: herdar `FURNITURE` como default é
seguro) e FAIL se aplica a formas complexas sem declaração (alto risco: é
exatamente a classe de bug real desta sessão). Rodado no apartamento
inteiro ao final: PASS com 0 WARN/0 FAIL — as ~10 pendências encontradas
foram resolvidas na hora (registradas no `KIND_REGISTRY`), não deixadas
como débito.
