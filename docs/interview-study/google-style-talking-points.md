# Talking Points — histórias pra contar em entrevista (3-5 min cada)

Não são perguntas oficiais de nenhuma empresa — são as mesmas lições de
[`architecture-lessons.md`](architecture-lessons.md), reestruturadas no
formato de "conta uma vez que você resolveu um problema difícil de
arquitetura", que é como perguntas comportamentais/de sistema costumam
abrir espaço em entrevistas Senior/Staff ("me conta de uma decisão de
design que você tomou e por quê").

**Regra de uso**: fale do PRINCÍPIO primeiro, use o exemplo do apartamento
só como prova concreta de que você já implementou isso, não como o assunto
principal. Ninguém em Staff/System Design quer ouvir 10 minutos sobre
banheiro — querem ouvir sobre single source of truth, e que você tem uma
prova real de ter resolvido isso.

---

## Canonical validation (optimizer vs CI)

**Problem**: um sistema de posicionamento (optimizer) aprovava
configurações que depois falhavam na validação de produção (CI).

**Constraint**: o optimizer precisa testar MUITOS candidatos rapidamente
(busca em grade, dezenas de posições por segundo); a validação de produção
precisa ser a fonte de verdade, mesmo sendo mais cara de calcular.

**Bad approach**: dar ao optimizer uma versão "aproximada" ou "mais rápida"
da regra de validação, assumindo que as duas ficariam sincronizadas por
convenção de equipe.

**Root cause**: optimizer e CI codificavam definições DIFERENTES de "válido"
— duas implementações da mesma regra de negócio, mantidas por pessoas/
momentos diferentes, sem mecanismo que forçasse sincronia.

**Design decision**: fazer o optimizer chamar a implementação de validação
canônica DIRETO, em vez de uma aproximação — e adicionar um gate que
reavalia toda decisão de posicionamento contra o estado final, comparando
com o que foi registrado no momento da escolha.

**Trade-off**: a busca fica mais cara computacionalmente (a validação real
é mais lenta que a heurística que ela substituiu). Aceitável — correção >
velocidade quando o custo de um falso-positivo é alto (nesse caso,
detectar o erro só depois, em produção).

**Validation**: testes de regressão garantem que candidatos vencedores
foram avaliados pelo MESMO gate que a produção usa; um teste específico
prova que a reavaliação pega uma divergência simulada entre o que foi
gravado e o estado atual.

**Generalization**: aplicável a fraud engines (regra de scoring do modelo
de decisão != regra usada no teste A/B que validou o modelo), authorization
(checagem de permissão no client-side != checagem no backend), pricing
(cálculo de desconto no carrinho != cálculo no checkout), resource
scheduling (estimativa do scheduler != admission controller real).

---

## Semantic contracts over shape inference

**Problem**: um validador de geometria rejeitava objetos legítimos (forma
não-retangular intencional, rotação intencional) como "geometria quebrada".

**Constraint**: o sistema processa centenas de tipos de objeto diferentes,
com formas legitimamente variadas (retângulos, polígonos recortados,
aproximações de círculo) — não dá pra assumir "tudo é retângulo".

**Bad approach**: adicionar exceções pontuais por nome de objeto
(`if kind == "vaso": skip`) cada vez que um novo tipo de forma legítima
aparecia.

**Root cause**: o validador inferia SEMÂNTICA (essa forma é válida?) a
partir de ESTRUTURA (quantos vértices, é retângulo?) — perguntas diferentes
sendo tratadas como a mesma.

**Design decision**: separar a pergunta em contrato explícito — todo objeto
declara sua intenção (`geometry_intent`) e sua política de forma esperada
(`shape_policy`: rotação permitida? forma não-retangular permitida?
independentemente uma da outra), num registro central editado por humano.

**Trade-off**: exige migração — nem todo objeto do sistema tinha essa
declaração desde o início. Resolvido com um estado intermediário (WARN
durante migração, FAIL só pra casos de alto risco) em vez de big-bang.

**Validation**: um gate dedicado torna a cobertura mensurável (quantos
objetos têm contrato declarado vs quantos ainda dependem de default) —
rodado no sistema inteiro, não só no caso que motivou a correção.

**Generalization**: aplicável a type systems (comportamento de um valor não
deveria ser inferido só pelo tipo primitivo subjacente), domain modeling
(um desconto de 100% != erro de preço zero, mesmo com o mesmo valor
numérico), event schemas (inferir o tipo de evento pela AUSÊNCIA de um
campo é frágil).

---

## Visual representation vs operational envelope

**Problem**: um objeto pisável (tapete), aninhado dentro de um grupo maior,
inflava a área de colisão física desse grupo — gerando colisões que não
existiam fisicamente.

**Constraint**: objetos são compostos hierarquicamente (grupos contêm
sub-objetos com propósitos diferentes) — não dá pra tratar todo sub-objeto
de um grupo como tendo o mesmo comportamento físico do grupo.

**Bad approach**: excluir por nome (substring matching em "tapete"/"rug")
— funciona até o próximo tipo de objeto pisável/decorativo aparecer com um
nome diferente.

**Root cause**: a representação visual (bounding box, usada pra renderizar)
e a restrição operacional (footprint de colisão, usada pra validar) eram
tratadas como o MESMO dado — bbox virava colisão automaticamente, sem
ninguém decidir isso explicitamente.

**Design decision**: separar os dois conceitos no modelo — `collision_footprint`
só existe quando uma política EXPLÍCITA declara o objeto como sólido pra
esse propósito; nunca é derivado automaticamente do bbox visual.

**Trade-off**: mais um campo pra declarar por tipo de objeto (custo de
modelagem inicial). Aceito porque o custo de NÃO declarar (bugs recorrentes
da mesma classe, cada um exigindo investigação do zero) já era mensurável —
esse exato bug apareceu 3 vezes em 3 gates diferentes no mesmo dia antes da
correção estrutural.

**Validation**: teste de regressão prova o invariante diretamente — um
objeto marcado como "não-sólido" (SOFT/DECORATIVE) NUNCA pode ter política
de colisão sólida; violação é FAIL determinístico, não depende de revisão
manual notar.

**Generalization**: aplicável a cache size vs capacidade lógica de dados,
API payload vs entidade de negócio completa, resource request vs uso real
em orquestração de containers, hitbox visual vs zona de interação real em
sistemas de jogo/simulação física.

---

## RAG governance and source of truth

**Problem**: um sistema com RAG (retrieval-augmented generation) guardando
decisões técnicas e preferências corria risco de tratar o índice vetorial
como banco de regras de negócio.

**Constraint**: o sistema precisa de memória de longo prazo (decisões
tomadas em sessões anteriores, preferências acumuladas) que não cabe
inteiramente no contexto de uma única execução.

**Bad approach**: guardar regras de negócio ativas (thresholds numéricos,
políticas) como chunks no vector store, consultados diretamente por
processos críticos.

**Root cause**: confundir "recuperação de conhecimento relevante"
(problema que RAG resolve bem) com "fonte de verdade de comportamento
crítico" (problema que RAG resolve mal — embeddings não garantem
atualidade, só similaridade semântica).

**Design decision**: hierarquia explícita de autoridade — código/config/
testes no topo (executável, sempre atual), ADR/HANDOFF no meio (racional
documentado), RAG por último (índice de busca, pode ficar stale). Nenhum
processo crítico (CI, neste caso) depende do RAG estar disponível.

**Trade-off**: perde a conveniência de "só perguntar ao RAG" pra tudo — os
valores realmente críticos vivem em código versionado, exigindo um PR pra
mudar em vez de uma atualização de chunk. Aceito porque criticidade > 
conveniência de edição.

**Validation**: critério de aceite explícito e testável —
`rag_required_for_ci: false` — desligar RAG/LLM não impede o sistema de
decidir PASS/FAIL sozinho.

**Generalization**: aplicável a qualquer sistema agentic em produção —
agentes de suporte ao cliente citando políticas desatualizadas recuperadas
por similaridade, sistemas de recomendação tratando embeddings como
catálogo de produtos ativo, LLM ops que deixam prompt/regra de negócio
crítica só documentada em texto livre recuperável, nunca versionada como
código.
