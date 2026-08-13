# Architecture Lessons

Sete conceitos de engenharia, cada um ancorado num bug real desta sessão
(2026-08-12, `sketchup-mcp`). Formato: **Bug real** → **Princípio** →
**Aplicação geral** → **Implementação** → **Níveis de resposta** (como um
mid/senior/staff engineer resolveria a MESMA coisa).

---

## 1. Single Source of Truth / Validator Reuse

**Bug real**: a busca de posição da mesa de jantar (`tools/furnish_apartment.py`)
testava candidatos com uma heurística de proximidade ("mais perto do
centroide da área livre = melhor"). O CI validava a posição final com
`circulation_gate.py` (erosão geométrica + conectividade real). As duas
implementações discordavam — o optimizer aprovava posições que o CI
reprovava, gerando o mesmo padrão clássico de "passou local, falhou CI".

Pior ainda: durante a correção, descobri que `tools/correction_fixes.py`
tinha uma TERCEIRA cópia da regra de colisão (`_overlapping_module_pairs`),
que quebrou silenciosamente (`ValueError`) quando a implementação canônica
mudou de forma — prova ao vivo de que duplicar uma regra sempre cobra o
preço, só a demora varia.

**Princípio**: quando duas partes de um sistema decidem se algo é "válido"
(um optimizer que escolhe, um validador que aprova), elas precisam consumir
a MESMA implementação — nunca reimplementações paralelas, mesmo que
"equivalentes na teoria".

**Aplicação geral**: validação de frontend duplicando regra de negócio do
backend; múltiplos microservices reimplementando a mesma regra de pricing/
fraude/elegibilidade; um scheduler que estima "cabe no nó" com uma fórmula
diferente do admission controller que decide de verdade.

**Implementação**: `tools/furnish_apartment.py` (busca) importa e chama
`tools.circulation_gate.gate()` DIRETO — não uma cópia, não uma aproximação.
`tools/optimizer_consistency_gate.py` formaliza isso como invariante testável:
toda decisão de posicionamento carrega `canonical_gate` (qual implementação
foi usada) e é REAVALIADA contra o estado final, não confia no resultado
gravado no momento da escolha. `tools/furniture_overlap_gate.py::
iter_overlap_pairs()` foi extraído como núcleo único depois que
`correction_fixes.py` provou, ao quebrar, que a duplicação já existia.

**Níveis de resposta**:
- *Mid*: conserta o cálculo que o optimizer usa pra bater com o do CI.
- *Senior*: faz optimizer e CI importarem a MESMA função; adiciona teste de
  regressão que roda os dois caminhos e compara.
- *Staff*: define o **limite de política canônica** (`canonical_gate` como
  campo obrigatório de provenance), cria um gate que FALHA se qualquer
  decisão de posicionamento não referenciar a implementação canônica — e
  isso pega automaticamente a PRÓXIMA duplicação futura, não só a de hoje.

---

## 2. Semantic Contracts (o que a geometria SIGNIFICA != o que ela PARECE)

**Bug real**: um vaso sanitário com cantos arredondados (anatomia de produto
real, curada) foi rejeitado por `geometry_sanity.py` como "eixo torto" — o
gate inferia "geometria válida" a partir da FORMA (retângulo = ok, qualquer
outra coisa = suspeito). Uma almofada girada 12° pro efeito "jogada" caiu na
MESMA checagem, por um motivo completamente diferente (rotação, não forma).

**Princípio**: comportamento não deve ser inferido só a partir da estrutura
física. "Isso É um X" (semântica/intenção) é uma pergunta diferente de
"isso PARECE um X" (geometria/forma) — um sistema que confunde as duas
adivinha, e adivinhação eventualmente erra.

**Aplicação geral**: type systems (um `int` que representa um ID de usuário
não deveria aceitar operações aritméticas só porque "parece" um número);
domain modeling (um desconto de 100% não é o mesmo que um erro de preço
zero, mesmo que o valor no banco seja idêntico); metadata contracts / event
schemas (um evento `UserDeleted` não deveria ser inferido só porque um campo
ficou null).

**Implementação**: `core/spatial_semantics.py` — todo objeto declara
`geometry_intent` (STRUCTURAL/FURNITURE/SOFT/DECORATIVE/FIXTURE) e
`shape_policy` (rotação permitida? forma não-retangular permitida?)
EXPLICITAMENTE, por um registro central (`KIND_REGISTRY`), não por inferência
de forma. `tools/semantic_geometry_contract_gate.py` torna a ausência de
declaração um estado visível (`WARN_LEGACY_SEMANTICS`/`FAIL_MISSING_SEMANTICS`),
não um "provavelmente está bem".

**Níveis de resposta**:
- *Mid*: adiciona um `if kind == "vaso": skip_check()`.
- *Senior*: adiciona um campo `decorative: bool` que os gates checam.
- *Staff*: separa a pergunta em DUAS dimensões ortogonais (`geometry_intent`
  responde "o que é", `shape_policy` responde "que forma é esperada") —
  porque a Senior-solution (`decorative: bool`) sozinha ainda conflaria
  "vaso arredondado" (forma) com "almofada girada" (rotação), o MESMO
  bug com um disfarce diferente.

---

## 3. Visual Representation vs Operational Envelope

**Bug real**: um tapete de banho, geometricamente aninhado dentro de um
módulo maior chamado "Enxoval", foi somado ao footprint desse módulo pra
checagem de colisão — o bbox VISUAL do conjunto virou, sem ninguém decidir
isso explicitamente, o footprint de COLISÃO. Resultado: "Enxoval × Vaso"
reportado como 35% sobreposto — colisão que não existe fisicamente (tapete é
pisável).

**Princípio**: representação (como algo é desenhado/medido) e restrição
operacional (como algo se comporta pra uma finalidade específica — colisão,
circulação, orçamento de memória) são coisas DIFERENTES que só coincidem por
acaso, nunca por definição.

**Aplicação geral**: tamanho do cache != capacidade lógica de dados que ele
representa; payload de uma API != entidade de negócio completa (um campo
omitido no JSON não significa que o valor é null no domínio); resource
*request* de um container (o que foi pedido) != uso real (o que está sendo
consumido) — a causa raiz de praticamente todo incidente de "OOM
inesperado" em Kubernetes; bounding box de uma hitbox de jogo != zona real
de interação (uma espada tem alcance maior que seu sprite).

**Implementação**: `tools/collision_envelope_gate.py::resolve_envelope()` —
`collision_footprint` só existe se `interaction_policy.furniture_overlap ==
"EXCLUSIVE"` foi DECLARADO; nunca é derivado automaticamente do bbox visual.
O teste `test_soft_items_never_solid` prova a regressão: um item marcado
`geometry_intent=SOFT` com política de sólido é um FAIL estrutural, não um
detalhe.

**Níveis de resposta**:
- *Mid*: exclui "tapete" da checagem de colisão por nome (substring match).
- *Senior*: adiciona um campo `walkable: bool` no tapete.
- *Staff*: separa `visual_bbox` de `collision_footprint` como conceitos
  DIFERENTES no modelo de dados, com uma política explícita decidindo
  quando um deriva o outro — porque a Senior-solution ainda quebra pro
  PRÓXIMO tipo de objeto pisável/decorativo que alguém adicionar (foi
  exatamente isso que aconteceu: o mesmo bug, achado em kinds diferentes,
  3 vezes no mesmo dia, antes da correção Staff).

---

## 4. Fail Fast

**Bug real** (não desta sessão, mas do mesmo pipeline — `core/scale.py`):
`PT_TO_M` (conversão pontos-PDF → metros) é lida UMA vez por processo, no
primeiro import. Rodar com a escala errada não gera um erro — gera
geometria 36% maior, silenciosamente, sem nenhum sintoma até um humano
notar visualmente que os móveis "flutuam fora do shell". A correção foi um
`RuntimeError` explícito (`core/scale.py::assert_pt_to_m_for_source`) que
compara a escala ativa contra a verificada, e recusa continuar se divergir.

**Princípio**: um resultado ERRADO em silêncio é estritamente pior que uma
falha explícita — a falha silenciosa se propaga (métricas erradas, decisões
erradas tomadas em cima dela, dados corrompidos persistidos) antes que
alguém perceba; a falha explícita para no ponto exato do erro.

**Aplicação geral**: validação de configuração no startup (não no primeiro
request que a usa); migração de banco que verifica compatibilidade de
schema ANTES de aplicar, não depois; deploy de infraestrutura que falha o
apply em vez de aplicar parcialmente; um parser que rejeita input malformado
em vez de "fazer o melhor possível" com ele.

**Implementação**: `core/scale.py` (módulo já existente, referência pro
princípio); o padrão se repete nesta sessão em `tools/circulation_gate.py`
— o gate nunca "estima" se um portal está conectado, ele erode a geometria
e testa conectividade real; se não há dados suficientes (`len(portais) < 2`),
reporta erro explícito em vez de assumir PASS.

**Níveis de resposta**:
- *Mid*: adiciona um comentário avisando sobre a ordem de import.
- *Senior*: adiciona validação no ponto de uso.
- *Staff*: torna o estado inválido IRREPRESENTÁVEL ou IMEDIATAMENTE FATAL —
  a escala errada não vira um warning que alguém pode ignorar, vira uma
  exceção que impede QUALQUER geometria errada de ser gerada.

---

## 5. Base Constraint vs Regression Introduced by the System

**Bug real**: a sala combinada (living+dining) tem um trecho da PLANTA
original (não da mobília) com só 0.75-0.95m de largura livre — um gargalo
que já existia no PDF, antes de qualquer móvel entrar. A primeira hipótese
(errada) foi tratar isso como "achado arquitetônico, não dá pra consertar,
documentar e seguir". A hipótese CORRETA, provada empiricamente (testando
com o cômodo vazio), era que a mobília — não a planta — fechava a
circulação; o gargalo da planta sozinho ainda permitia conectividade.

**Princípio**: um sistema não deve ser responsabilizado por uma restrição
PRÉ-EXISTENTE que ele não criou, mas TAMBÉM não pode piorar essa restrição
sem que isso conte como regressão. As duas coisas — "herdei isso quebrado"
e "eu quebrei isso" — precisam de vereditos DIFERENTES no mesmo sistema de
gate.

**Aplicação geral**: legacy systems com débito técnico pré-existente (o time
atual não é culpado pelo débito herdado, mas É responsável por não
aumentá-lo); SLOs com baseline (uma API que sempre foi lenta p99=800ms não
"quebrou o SLO" se continuar em 800ms, mas quebra se subir pra 1200ms);
regressão de performance em migração (comparar contra o baseline ANTES da
mudança, não contra um alvo absoluto arbitrário).

**Implementação**: `tools/circulation_gate.py` — tier `shell_estreito`:
se o shell VAZIO já não sustenta o target, o veredito vira
`PASS_WARN_BASE_GEOMETRY` (não bloqueia) a menos que a mobília piore o
gargalo além de uma tolerância (`GEOMETRY_TOLERANCE_M`, `core/project_policy.py`).
O modelo lógico exato:
```python
if empty_shell >= target:
    furnished must remain >= target
else:
    furnished must not worsen empty_shell beyond tolerance
```

**Níveis de resposta**:
- *Mid*: relaxa o threshold global até o gate passar.
- *Senior*: adiciona uma exceção pro cômodo específico.
- *Staff*: modela as DUAS perguntas separadamente (o shell vazio sustenta o
  alvo? a mobília piorou o que já existia?) como parte do CONTRATO do gate,
  não como exceção pontual — qualquer cômodo futuro com um gargalo herdado
  automaticamente ganha o comportamento certo, sem precisar de outra exceção.

---

## 6. Agent vs Skill vs RAG vs Gate

**Contexto real**: este projeto tem 8 subagentes especializados
(`interior-designer`, `interior-pm`, `interior-orchestrator`,
`sketchup-fidelity-reviewer`, `test-engineer`, `java-architect`, etc.) mais
um RAG (Qdrant) guardando preferências e decisões técnicas. Ao formalizar os
3 gates novos desta sessão, a tentação óbvia seria criar `circulation-agent`
ou `bathroom-agent`. Não foi feito.

**Princípio** (framing usado nesta sessão, validado por revisão de
arquitetura):
```text
Agent = QUEM   — dono de uma responsabilidade autônoma, toma decisão, tem critério de parada
Skill = COMO   — processo repetível, sem estado próprio de decisão
RAG   = O QUE SABEMOS — conhecimento recuperável, nunca autoritativo
Gate/Test = LEI — o que precisa ser verdade sempre, determinístico
```
Um agente novo só se justifica quando existe uma responsabilidade AUTÔNOMA
nova (não uma tarefa nova) — E o owner atual é inadequado — E a autoridade
não se sobrepõe a nenhum agente existente — E há um contrato claro de
entrada/saída.

**Por que `circulation-agent` seria errado**: "verificar circulação" não é
uma responsabilidade autônoma — é uma CAPACIDADE determinística
(`tools/circulation_gate.py`, uma função pura `gate(con, boxes, room_id) ->
dict`). Um agente implica julgamento, iteração, possivelmente falha
ambígua. Circulação tem resposta certa/errada, calculável sem ambiguidade —
isso é lei (gate), não agente.

**Aplicação geral**: times que criam um "microservice" pra cada função em
vez de uma biblioteca compartilhada cometem o mesmo erro em escala maior —
confundem "isso é uma operação" com "isso precisa de um dono autônomo".

**Implementação**: `tools/circulation_gate.py`, `tools/geometry_sanity.py`,
`tools/furniture_overlap_gate.py`, e os 3 novos desta sessão são todos
FUNÇÕES PURAS chamadas por agentes/skills existentes — não agentes.
`.claude/skills/interior-project-audit/SKILL.md` foi atualizado pra
REFERENCIAR esses gates (GATE 1/3/4 do skill agora rodam os comandos
determinísticos antes do julgamento humano/GPT), em vez de um agente novo
reimplementar o julgamento.

**Níveis de resposta**:
- *Mid*: cria um agente pra cada funcionalidade nova.
- *Senior*: cria uma skill reutilizável em vez de um agente.
- *Staff*: mantém um registro EXPLÍCITO de ownership (`agent_registry`,
  proposto mas não implementado nesta sessão — ver pendências no HANDOFF)
  onde cada capacidade tem exatamente UM dono primário, prevenindo que dois
  agentes decidam a mesma coisa de formas diferentes no futuro.

---

## 7. RAG Is Not Source of Truth

**Contexto real**: este projeto tem um RAG (Qdrant, coleções
`felipe_preferences` e `knowledge_base`) guardando decisões técnicas e
preferências de design. A pergunta natural depois de formalizar os 3 gates
seria: "isso deveria virar chunk no RAG?".

**Princípio**: RAG é um ÍNDICE DE RECUPERAÇÃO, não um banco autoritativo de
comportamento. A hierarquia de autoridade:
```text
CODE / CONFIG / TESTS   (fonte executável — o que realmente roda)
        ↓
ADR / HANDOFF            (fonte de decisão e racional — POR QUE)
        ↓
RAG / Qdrant              (índice pra ACHAR essas fontes)
        ↓
LLM                        (síntese em cima do que foi recuperado)
```
Se o Qdrant recuperar "o threshold é 0.90m" mas o código atual diz 0.85m, o
CÓDIGO vence — sempre. Retrieval pode ficar stale (o chunk foi indexado
antes da última mudança); código não pode (é o que está rodando agora).

**O que vale virar RAG, o que não vale** (teste usado nesta sessão): *"se eu
apagar esse chunk amanhã, o comportamento correto ainda está garantido pelo
código/teste?"* Se sim, não duplica a implementação — só guarda a DECISÃO e
o racional:

- **Vale RAG/ADR**: "Portais de circulação passaram de classificação por
  largura medida pra papel semântico declarado, porque a sala r002 provou
  que largura física não identifica função arquitetônica" (a decisão e o
  PORQUÊ — não é recuperável só olhando o código).
- **NÃO precisa virar RAG** (é implementação, recuperável pelo Git): "o grid
  search usa passo de 6 polegadas" (detalhe de implementação, muda sem
  aviso, o código É a fonte).

**Governança de staleness**: chunks técnicos deveriam carregar metadata
`stable_id` + `source_commit` + `status: active|superseded` — o retriever
default só busca `status=active`; uma decisão substituída marca a antiga
`superseded` em vez de deixar duas "verdades" concorrentes no índice
vetorial (o embedding mais parecido com a pergunta pode ser o mais
DESATUALIZADO, não há garantia de que similaridade semântica = atualidade).

**Aplicação geral**: qualquer sistema RAG-based em produção que trata o
vector store como banco de configuração (não como índice de busca) tem esse
risco — de agent frameworks recuperando políticas de negócio desatualizadas
a chatbots de suporte citando documentação antiga porque o embedding "soa
parecido" com a pergunta.

**Implementação nesta sessão**: os thresholds numéricos foram pra
`core/project_policy.py` (CÓDIGO, com metadata de source/scope/
applicability) — não pro RAG. O RACIONAL da decisão (por que 0.80m pra
destino terminal, não 0.90m) foi pro `HANDOFF.md` (ADR informal) e
`docs/adr/0001-semantic-geometry-contract.md` (ADR formal). Nenhum dos 3
gates novos depende do RAG pra rodar — `rag_required_for_ci: false` é
literal: desligar Qdrant/GPT/Claude não impede o CI de determinar
PASS/FAIL sozinho.

**Níveis de resposta**:
- *Mid*: guarda a regra de negócio como texto no vector store porque "é
  mais fácil consultar".
- *Senior*: guarda a regra no código, mas ainda deixa o RAG com uma cópia
  "pra referência rápida" sem controle de qual é a verdade.
- *Staff*: define a hierarquia de autoridade explicitamente, com mecanismo
  de invalidação (`status: superseded`) — e garante que o sistema crítico
  (CI, neste caso) NUNCA tem o RAG como dependência no caminho crítico.
