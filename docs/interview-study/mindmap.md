# Mind Map — Reliable Intelligent Systems

Ver [`architecture-lessons.md`](architecture-lessons.md) para o detalhe de
cada ramo (problema real → princípio → implementação → níveis de resposta).

```mermaid
mindmap
  root((Reliable Intelligent Systems))
    Source of Truth
      Canonical Gate
        optimizer e CI importam a MESMA função
        tools/circulation_gate.py::gate
      Tests
        pinam o comportamento, não a implementação
      Configuration
        core/project_policy.py — value+source+scope+applicability
      Avoid duplicated rules
        correction_fixes.py tinha cópia própria — quebrou
        extraído em iter_overlap_pairs único
    Semantic Contracts
      geometry_intent
        STRUCTURAL FURNITURE SOFT DECORATIVE FIXTURE
      shape_policy
        rotation_allowed != non_rectangular_allowed
        bug real: almofada girada vs vaso arredondado
      interaction_policy
        por domínio: circulation != furniture_overlap
        um único collision_policy perdia informação
      explicit metadata
        registro central, não inferência por forma/bbox
    Validation
      Fail Fast
        core/scale.py — RuntimeError explícito
        errado em silêncio pior que falha explícita
      CI Gates
        semantic_geometry_contract_gate
        collision_envelope_gate
        optimizer_consistency_gate
      Regression Tests
        test_soft_items_never_solid
        test_divergence_between_recorded_and_live_fails
      Base vs Introduced Constraint
        shell vazio 0.75m = herdado, não é bug
        mobília piorando 0.90m->0.72m = regressão real
        tolerância declarada (0.02m) separa os dois casos
    AI Architecture
      Agent
        QUEM — responsabilidade autônoma, critério de parada
        interior-designer interior-pm sketchup-fidelity-reviewer
      Skill
        COMO — processo repetível, sem decisão própria
        interior-project-audit consome os gates, não reimplementa
      RAG
        O QUE SABEMOS — recuperável, NUNCA autoritativo
        Qdrant: felipe_preferences knowledge_base
      Gate/Test
        LEI — determinístico, sempre verdadeiro
        circulation_gate geometry_sanity furniture_overlap_gate
      Por que NÃO circulation-agent
        circulação tem resposta certa/errada calculável
        isso é lei, não julgamento autônomo
    Knowledge Governance
      stable_id
        identificador conceitual estável entre revisões
      source_commit
        rastreia de qual commit o chunk veio
      active / superseded
        retriever default só busca active
        decisão substituída marca a antiga, não some
      hierarquia de autoridade
        CODE/TESTS > ADR/HANDOFF > RAG > LLM
        rag_required_for_ci = false SEMPRE
```
