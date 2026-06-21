# GATE de Avaliação — Classe `sofa`

Este documento define o **GATE de avaliação da classe sofá**. Ele descreve cada
critério de aprovação, com um **critério objetivo de quando passa**, e fixa as
regras que protegem o loop contra autoaprovação falsa e contra "detalhe escondendo
forma ruim".

O GATE vale para a **classe** (`sofa`), não para um exemplar específico. Qualquer
regra que só funcione para um único sofá é considerada *overfit* e está proibida.

---

## REGRA CRÍTICA — quem julga o quê

> **O agente NUNCA autojulga `ASSET_PASS`, `SOFTNESS_PASS`, `CAIXOTAO_FAIL` nem
> "IMPROVED/SAME/WORSE".** O veredito visual é **externo** (Felipe / GPT).

- O agente **só** pode declarar PASS dos critérios **objetivos e determinísticos**:
  `PIPELINE_PASS`, `SCHEMA_PASS`, `COMPONENTS_PASS`.
- `ASSET_PASS`, `SOFTNESS_PASS`, `CAIXOTAO_FAIL`, `PROPORTION_PASS` (quando depende
  de leitura de silhueta), `DETAIL_RESTRAINT_PASS` e qualquer juízo de
  "melhorou/igual/piorou" ficam em **PENDENTE** até o review visual externo.
- **NUNCA escrever "GPT PASS" (nem equivalente) dentro do render, no nome do
  arquivo, no log ou no commit.** O render carrega a imagem e a pergunta; o veredito
  vem de fora. Estampar "GPT PASS" no próprio artefato é **autoaprovação falsa** e é
  um erro proibido (ver "Erros proibidos").
- Enquanto o review externo não chega, o estado correto a reportar é
  `PENDENTE_VISUAL_REVIEW` (análogo a `BLOCKED_VISUAL_REVIEW` quando o canal de
  review está indisponível). Não autodeclarar progresso visual.

---

## Princípios do GATE

1. **NÃO overfit** — as regras vivem na **classe** (`sofa`), nunca num exemplar.
   Se a regra precisa do nome/medida de UM sofá específico para passar, ela está
   errada.
2. **Forma antes de detalhe** — ordem de prioridade (hierarquia de avaliação):
   **silhueta → proporção → anatomia → maciez → composição → detalhe → material.**
   Um critério mais à direita NUNCA compensa falha de um critério à esquerda.
3. **O sofá precisa PARECER estofado** — volume real, **topo coroado** (almofadas
   com abaulamento, não plano), **bordas suaves**, **encosto com espessura + rake**
   (inclinação), **braço com massa**, **base recuada** sob o corpo, **costura
   sutil**.
4. **Generalização obrigatória** — casos novos têm que sair coerentes sem hardcode.
5. **Detalhe nunca esconde forma ruim** — piping/costura/material não podem ser
   usados para mascarar caixotão, encosto-placa ou braço-bloco.

---

## Critérios do GATE (na ordem de avaliação)

### 1. `PIPELINE_PASS` — *objetivo / o agente pode declarar*
O pipeline executou ponta a ponta sem erro.

**Passa quando, cumulativamente:**
- todos os scripts da classe rodam e retornam exit 0;
- o `.skp` é gerado e existe no disco no caminho esperado;
- os renders (iso/top/front, conforme o pipeline) são gerados e existem;
- os logs do build existem e não contêm exceção/traceback fatal.

Falha se faltar qualquer artefato (SKP ausente, render ausente, log ausente) ou se
houver erro de execução.

### 2. `SCHEMA_PASS` — *objetivo / o agente pode declarar*
A configuração de entrada é válida e sã.

**Passa quando:**
- todos os configs são validados pelo schema da classe (campos obrigatórios,
  tipos, unidades);
- **dimensões absurdas são rejeitadas** (fora das faixas físicas plausíveis de um
  sofá — ver `PROPORTION_PASS`) — o schema deve recusar, não "consertar em
  silêncio";
- as **famílias suportadas** (ex.: reto / com chaise / 2-3 lugares / modular) são
  reconhecidas; família não suportada é rejeitada explicitamente, não tratada como
  default.

Falha se um config inválido passa, se uma dimensão absurda é aceita, ou se uma
família desconhecida é silenciosamente aceita.

### 3. `PRIMITIVES_PASS` — *forma; veredito visual externo*
As primitivas, **isoladas**, são plausíveis como peças de estofado.

**Passa quando (review visual):**
- **assento** lê como almofada estofada, **não bloco seco**;
- **encosto** tem volume, **não placa**;
- **braços** têm leitura de estofado (massa + borda macia), não prisma;
- **costura** aparece **sutil**, acompanhando a forma.

Determinístico aqui: existência/contagem/nomeação das primitivas pode ser checada
pelo agente. A **plausibilidade** (não-bloco, não-placa) é **PENDENTE até review
visual externo**.

### 4. `COMPONENTS_PASS` — *objetivo / o agente pode declarar*
A montagem dos componentes está consistente.

**Passa quando:**
- assentos / braços / encostos / base **se encaixam** (adjacência esperada);
- **sem flutuação** — nenhum componente solto no ar (checagem de contato/gap por
  bounding box);
- **sem interpenetração grosseira** — sobreposição de volumes abaixo do limiar
  tolerado (folga/encaixe de estofado é permitido; atravessamento grosseiro não);
- todos os componentes estão **nomeados** segundo a convenção da classe.

Estes são testes geométricos determinísticos — **o agente pode declarar
`COMPONENTS_PASS`**.

### 5. `ARCHETYPE_PASS` — *forma; veredito visual externo*
Os **archetypes canônicos** da classe saem coerentes.

**Passa quando:** cada archetype canônico (configuração de referência da classe)
gera um sofá visualmente coerente, sem regressão de forma. PENDENTE até review
visual externo.

### 6. `GENERALIZATION_PASS` — *forma; veredito visual externo*
**Casos novos** (não-canônicos) também saem coerentes, **sem depender de hardcode**.

**Passa quando:** configurações novas/aleatórias dentro das faixas válidas geram
sofás coerentes; nenhuma coerência depende de valor cravado para um exemplar.
Se só os archetypes ficam bons e os casos novos quebram, **reprova** (sinal de
overfit). PENDENTE até review visual externo.

### 7. `BLOCKOUT_PASS` — *silhueta; veredito visual externo*
O blockout (massa macro) é **reconhecível como sofá**.

**Passa quando:** a silhueta macro lê imediatamente como "sofá" e a **proporção
macro** (comprimento × profundidade × altura; altura de assento; altura de encosto)
está correta. É o primeiro portão de forma. PENDENTE até review visual externo.

### 8. `ASSET_PASS` — *composição/material; SOMENTE veredito visual externo*
O resultado **parece um asset low/mid-poly apresentável**.

**Passa quando (somente review externo):** lê como asset de móvel
apresentável — **não placeholder**, **não caixa com detalhe colado**. 
**O agente NUNCA declara `ASSET_PASS`.** Sempre PENDENTE até Felipe/GPT.

### 9. `CAIXOTAO_FAIL` — *flag de reprovação; veredito visual externo*
Flag booleana de **reprovação de forma**.

**É `true` (REPROVA) quando** as formas principais ainda parecem:
- caixas empilhadas;
- almofadas sem volume;
- encosto-placa;
- braços-bloco.

`CAIXOTAO_FAIL = true` **bloqueia o GATE inteiro**, independentemente de qualquer
critério de detalhe/material. **O agente nunca seta `CAIXOTAO_FAIL = false` por
conta própria** — só o review visual externo pode limpar essa flag. Até lá:
PENDENTE.

### 10. `SOFTNESS_PASS` — *maciez; SOMENTE veredito visual externo*
A leitura de **estofado é convincente**.

**Passa quando (somente review externo):** há volume real, **bordas e arredondamento
convincentes**, topo coroado, sensação de macio. **O agente NUNCA declara
`SOFTNESS_PASS`.** Sempre PENDENTE até Felipe/GPT.

### 11. `PROPORTION_PASS` — *proporção; faixas objetivas + leitura visual*
As dimensões estão **dentro das faixas** e as **relações são plausíveis**.

**Passa quando:**
- cada dimensão está dentro da faixa física da classe (parte determinística — o
  schema/teste pode checar);
- as **relações** entre peças são plausíveis (altura de assento × altura total;
  profundidade de assento × encosto; massa de braço × corpo; recuo da base).

A checagem numérica de faixa é determinística; a **plausibilidade das relações na
silhueta** é confirmada no review visual externo.

### 12. `DETAIL_RESTRAINT_PASS` — *detalhe; veredito visual externo*
O detalhe **não domina a forma**.

**Passa quando:**
- o detalhe (costura, piping, material) é contido e a leitura primária continua
  sendo a **forma**;
- **piping não vira mangueira** (não grosso, não facetado, não flutuante);
- **costura não mascara forma ruim** — se a forma macro/maciez falham, costura
  bonita NÃO salva.

PENDENTE até review visual externo.

---

## Ordem de bloqueio (forma antes de detalhe)

A avaliação respeita a hierarquia. Um portão à esquerda reprovado **bloqueia** os à
direita — não adianta material/detalhe bons se a silhueta/proporção/maciez falham:

```
silhueta  >  proporção  >  anatomia  >  maciez  >  composição  >  detalhe  >  material
BLOCKOUT     PROPORTION    PRIMITIVES   SOFTNESS   COMPONENTS     DETAIL_     ASSET
             /SCHEMA       /ARCHETYPE   /CAIXOTAO  /ARCHETYPE     RESTRAINT
```

Se `CAIXOTAO_FAIL = true`, ou `BLOCKOUT_PASS`/`PROPORTION_PASS`/`SOFTNESS_PASS`
falham, o conjunto **reprova** mesmo com detalhe/material aprovados.

---

## Resumo: quem pode declarar PASS

| Critério                | Tipo            | Agente pode declarar? |
|-------------------------|-----------------|-----------------------|
| `PIPELINE_PASS`         | objetivo        | **SIM**               |
| `SCHEMA_PASS`           | objetivo        | **SIM**               |
| `COMPONENTS_PASS`       | objetivo        | **SIM**               |
| `PROPORTION_PASS`       | faixa objetiva  | parcial (só faixa numérica); relações → externo |
| `PRIMITIVES_PASS`       | forma           | NÃO — PENDENTE externo |
| `ARCHETYPE_PASS`        | forma           | NÃO — PENDENTE externo |
| `GENERALIZATION_PASS`   | forma           | NÃO — PENDENTE externo |
| `BLOCKOUT_PASS`         | silhueta        | NÃO — PENDENTE externo |
| `DETAIL_RESTRAINT_PASS` | detalhe         | NÃO — PENDENTE externo |
| `ASSET_PASS`            | composição      | **NUNCA** — só externo |
| `SOFTNESS_PASS`         | maciez          | **NUNCA** — só externo |
| `CAIXOTAO_FAIL`         | reprovação      | **NUNCA limpa** — só externo |

---

## Erros proibidos (reprovam na hora)

- `CAIXOTAO_FAIL` — caixas empilhadas / almofadas sem volume / encosto-placa /
  braços-bloco.
- **piping grosso / facetado / tipo mangueira / flutuante.**
- **encosto vertical tipo parede** (sem espessura, sem rake).
- **assento reto tipo caixa** (sem coroamento, sem borda macia).
- **braço monolítico** (bloco sem massa de estofado).
- **pés colados na borda** / ausência de base / ausência de recuo da base.
- **detalhe antes da forma** (costura/material entregues antes de silhueta sã).
- **hardcode de um único sofá** (regra que não generaliza = overfit).
- **autoaprovação falsa** — escrever "GPT PASS" (ou equivalente) no render, no
  nome do arquivo, no log ou no commit; autodeclarar
  `ASSET_PASS`/`SOFTNESS_PASS`/`IMPROVED` sem review visual externo.
