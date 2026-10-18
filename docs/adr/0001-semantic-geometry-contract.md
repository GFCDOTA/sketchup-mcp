# ADR-0001: Contrato semântico único de geometria (geometry_intent / interaction_policy)

- **Status**: Aceito
- **Data**: 2026-08-12
- **Revisor de arquitetura**: GPT-Docker (consultado como arquiteto + revisor de software + guardião do CI, `ops/gpt-docker/`)
- **Contexto do projeto**: `sketchup-mcp`, pipeline PDF→SketchUp de apartamento mobiliado (planta_74)

## Contexto

No mesmo dia, três bugs da mesma classe foram corrigidos em três gates
determinísticos diferentes:

1. `geometry_sanity.py` rejeitava uma fita de LED como "footprint degenerado"
   (é fina por design, não é bug).
2. `geometry_sanity.py` rejeitava um vaso sanitário de cantos arredondados
   como "eixo torto" (a forma não-retangular é intencional — anatomia de
   produto real curada).
3. `furniture_overlap_gate.py` deixava um tapete de banho, agrupado dentro
   de um módulo maior ("Enxoval"), inflar a área de colisão desse módulo e
   gerar uma falsa colisão com o vaso.

Cada gate tinha sua PRÓPRIA heurística pra responder a mesma pergunta —
"essa geometria bloqueia passagem / colide com outra / pode ter forma
não-retangular?": altura Z (`circulation_gate.py`), booleans soltos
`decorative`/`smooth` + substring de `kind` (`geometry_sanity.py`), substring
de `module`/`kind` + listas de pares conhecidos (`furniture_overlap_gate.py`).
Consertar um bug num gate não consertava o mesmo bug nos outros dois.

## Decisão

Um módulo único (`core/spatial_semantics.py`) declara, por peça, um
**contrato semântico explícito**:

```python
geometry_intent: STRUCTURAL | FURNITURE | SOFT | DECORATIVE | FIXTURE
shape_policy: {rotation_allowed, non_rectangular_allowed, curved_allowed}
interaction_policy: {circulation: BLOCK|WALKABLE|OVERHEAD|IGNORE,
                     furniture_overlap: EXCLUSIVE|ALLOW|HOSTED|IGNORE}
host: {host_id, relationship: NONE|MOUNTED_ON|EMBEDDED_IN|RESTS_ON|CONTAINED_IN}
```

Um registro central por `kind`/`module` (`KIND_REGISTRY`/`MODULE_REGISTRY`)
declara a intenção — não é inferência por forma/tamanho/bbox, é uma tabela
editada por humano (mesmo espírito da tupla `decorative` que já existia em
`bathroom_layout.py`, generalizada). Os três gates agora CONSOMEM esse
contrato em vez de reimplementar a pergunta cada um à sua maneira.

Um `semantic_geometry_contract_gate.py` novo garante que toda peça relevante
tem o contrato declarado (`PASS`), ou está numa fila de migração visível
(`WARN_LEGACY_SEMANTICS` — forma simples, baixo risco) ou precisa de
declaração urgente (`FAIL_MISSING_SEMANTICS` — forma complexa sem contrato,
exatamente a classe de bug desta sessão).

## Alternativas consideradas

**Um único `collision_policy: SOLID|FOOTPRINT|IGNORE`** (proposta inicial).
Rejeitada — perde informação: um tapete precisa responder diferente pra
circulação (`WALKABLE`), overlap (`ALLOW`) e forma (`non_rectangular_allowed`).
Um único campo levaria de volta a `if kind == "tapete" and check == "overlap":
...` — o mesmo anti-padrão de substring matching que motivou este ADR.

**Inferir o contrato por shape/bbox no próprio gate** (ex.: "se tem >4
cantos, assume decorativo"). Rejeitada — é exatamente o comportamento que
causou os 3 bugs originais (inferência silenciosa por geometria).

**Reescrita completa (`Piece` dataclass + canonical envelope resolver
persistido em consensus.json normalizado)** — proposta pelo GPT como fase 3-5
de um rollout faseado. Adiada por escopo/tempo: o pipeline tem dezenas de
builders (`bathroom_layout.py`, `kitchen_layout.py`, `bedroom_designer.py`,
`furnish_apartment.py`) emitindo dicts soltos, não uma classe única — migrar
tudo de uma vez era risco de regressão desproporcional ao ganho imediato.
Fases 1-2 (contrato explícito + registro central) entregam o essencial sem
reescrever o pipeline.

## Consequências

- **Positivo**: os 3 gates agora respondem a mesma pergunta da mesma forma;
  um bug corrigido no contrato central se propaga pros 3, não precisa ser
  re-descoberto em cada um. `semantic_geometry_contract_gate` torna a
  "dívida de migração" visível (contável, não escondida).
- **Positivo**: dois gates novos (`collision_envelope_gate`,
  `optimizer_consistency_gate`) ficaram possíveis só porque o contrato
  existe — sem ele, não haveria um campo único pra perguntar "essa peça é
  sólida de propósito ou por acidente?".
- **Custo aceito**: migração é gradual — `interaction_policy`/`host` rodam
  em PARALELO aos heurísticos antigos (substring/altura Z) por enquanto, não
  os substituem. Remover o heurístico antigo é trabalho futuro (fase 2
  completa do plano do GPT), gated por `semantic_geometry_contract_gate`
  reportar zero pendência.
- **Custo aceito**: os thresholds numéricos específicos (0.90m, 0.80m etc.)
  viraram `NumericPolicy` com metadado (`core/project_policy.py`), mas ainda
  são valores de PROJETO hardcoded nesse módulo — não há mecanismo de
  override por planta/projeto ainda (seria necessário se o pipeline
  atendesse mais de uma tipologia/planta com regras diferentes).

## Ligação com implementação

| Conceito | Implementação | Teste |
|---|---|---|
| Contrato central | `core/spatial_semantics.py` | `tests/test_semantic_geometry_contract_gate.py` |
| Threshold provenance | `core/project_policy.py` | `tests/test_circulation_gate.py::test_portal_role_is_explicit_not_inferred` |
| Contrato ausente = FAIL/WARN | `tools/semantic_geometry_contract_gate.py` | `tests/test_semantic_geometry_contract_gate.py` |
| bbox visual != colisão | `tools/collision_envelope_gate.py` | `tests/test_collision_envelope_gate.py` |
| optimizer == CI | `tools/optimizer_consistency_gate.py` | `tests/test_optimizer_consistency_gate.py` |
| Portal role explícito | `tools/circulation_gate.py::_portal_kind` + campo `portal_role` | `tests/test_circulation_gate.py` |

Ver também `docs/interview-study/` para os princípios de engenharia
generalizados (fora do contexto SketchUp) e `HANDOFF.md` (2026-08-12, round 5)
para o relato completo da sessão, incluindo a consulta ao GPT-Docker.
