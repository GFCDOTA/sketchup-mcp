# Interview Study — engenharia real, extraída de um bug real

Esta pasta transforma uma sessão real de debugging (CI vermelho havia
semanas no `sketchup-mcp`, um pipeline PDF→SketchUp de apartamento
mobiliado) em material de estudo pra entrevistas de engenharia Senior/Staff.

**Como usar**: cada lição aqui parte de um bug ESPECÍFICO do SketchUp, mas o
que você deve levar pra entrevista é o PRINCÍPIO. O apartamento é só o
cenário concreto — o assunto real é arquitetura de software.

## Índice

| Arquivo | O que tem |
|---|---|
| [`architecture-lessons.md`](architecture-lessons.md) | 7 conceitos de engenharia, cada um com problema real → princípio → generalização → nível de resposta (mid/senior/staff) |
| [`mindmap.md`](mindmap.md) | Mapa mental (Mermaid) partindo de "Reliable Intelligent Systems" |
| [`box-diagrams.md`](box-diagrams.md) | Diagramas de fluxo (Mermaid): optimizer vs CI divergindo, arquitetura correta, arquitetura agêntica, hierarquia de autoridade de conhecimento |
| [`interview-questions.md`](interview-questions.md) | 8 perguntas no formato pergunta → o que o entrevistador testa → resposta boa → resposta nível Staff → exemplo do projeto |
| [`google-style-talking-points.md`](google-style-talking-points.md) | Histórias estruturadas (PROBLEM/CONSTRAINT/BAD APPROACH/ROOT CAUSE/DECISION/TRADE-OFF/VALIDATION/GENERALIZATION) pra contar em 3-5 minutos numa entrevista |

## Os 7 conceitos, resumidos

1. **Single Source of Truth / Validator Reuse** — um optimizer aprovou uma
   posição de móvel que o CI reprovou. Causa raiz: duas implementações da
   MESMA regra de negócio. → `tools/optimizer_consistency_gate.py`

2. **Semantic Contracts** — um vaso com cantos arredondados foi rejeitado
   como "geometria quebrada" porque nenhum gate sabia que a forma era
   intencional. → `core/spatial_semantics.py`

3. **Visual Representation vs Operational Envelope** — um tapete inflou a
   área de colisão do móvel que o hospedava porque "footprint visual" e
   "footprint de colisão" eram tratados como sinônimos. →
   `tools/collision_envelope_gate.py`

4. **Fail Fast** — `core/scale.py` levanta `RuntimeError` explícito se a
   escala errada for usada, em vez de silenciosamente gerar geometria 36%
   maior. → ver lição 4 em `architecture-lessons.md`

5. **Base Constraint vs Regression Introduced by the System** — um corredor
   de 0.75m já estreito NA PLANTA original não pode reprovar o mesmo jeito
   que um corredor que a MOBÍLIA estreitou de 0.90m pra 0.72m. →
   `tools/circulation_gate.py` (tiers `shell_estreito`/`FAIL_FURNITURE_WORSENS_BASE_GEOMETRY`)

6. **Agent vs Skill vs RAG vs Gate** — por que este projeto tem 8 subagentes
   especializados mas NÃO criou `circulation-agent`/`bathroom-agent`.

7. **RAG Is Not Source of Truth** — por que um threshold de 0.90m nunca deve
   viver só como chunk vetorial, e o que fazer quando o RAG recupera
   conhecimento desatualizado.

## Exemplo de como uma lição é estruturada

```text
Bug real:
  optimizer aprovava posição que circulation_gate reprovava.

Princípio:
  Single Source of Truth / Validator Reuse.

Aplicação geral:
  Um sistema não deve possuir duas implementações divergentes da mesma
  regra crítica.

Entrevistas:
  System Design, Backend, Platform, Staff, Reliability.
```

Cada seção de `architecture-lessons.md` segue esse formato, com o código
real do commit ligado.
