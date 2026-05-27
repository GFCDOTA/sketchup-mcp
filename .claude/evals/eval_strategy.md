# Eval strategy — sketchup-mcp

Como o projeto **mede** se está entregando o objetivo da
constituição (`.skp` fiel ao PDF). Eval ≠ teste. Teste prova que
um pedaço de código se comporta como spec; eval mede se o
sistema inteiro está no rumo certo pro humano.

## Três camadas de medição

### Camada 1 — Contract suite (testes automatizados)

Cobertura: primitivas Python + invariantes SKP-level.

Files: `tests/test_*.py` (6 arquivos pinando o contrato).

Gate: `python -m pytest tests/ -q` exit 0.

O que mede: o **builder** não regrediu. **Não** mede fidelidade
arquitetônica do `.skp` resultante.

### Camada 2 — `gates_self_check` (machine-readable, no report)

Cobertura: 4 booleans de integridade estrutural do SKP no
`geometry_report.json`:

- `plan_shell_group_exists`
- `wall_shell_is_single_group`
- `floors_separated_from_walls`
- `default_material_faces_zero`

Gate: todos `true`. Detalhe em
[`specs/fidelity_gate.md`](../specs/fidelity_gate.md) § Eixo 1.

O que mede: **estrutura do SKP** (não há walls quebradas, não há
faces sem material). Não mede se a wall está no lugar certo.

### Camada 3 — Rubric humano (julgamento visual + dimensional)

Cobertura: wall_fidelity / room_fidelity / opening_fidelity como
prose, baseado em side-by-side PDF vs SKP.

Local: `artifacts/<plant>/README.md` § Status, e
[`evals/fidelity_rubric.md`](fidelity_rubric.md) com critérios.

Gate: humano em PR review aprova.

O que mede: **fidelidade arquitetônica real**. É o gate final.

## Pipeline de eval por feature

```
Spec curto (docs/specs/FP-NNN_*.md)
   ↓
Fixture micro (fixtures/<plant_or_micro>/)
   ↓
Teste vermelho → Camada 1 OK
   ↓
Build SKP local → Camada 2 OK
   ↓
Side-by-side render → Camada 3 review humano
   ↓
Aplicar na planta real (planta_74)
   ↓
Promote pra artifacts/<plant>/
   ↓
PR contra develop
```

Sem passar pelas 3 camadas + promoção, feature **não é done**.

## Regressão

Toda PR que toca builder / kind_v5 routing / consensus schema
DEVE:

1. Manter Camada 1 verde
2. Manter Camada 2 OK (rodar build canônico de quadrado +
   planta_74 e confirmar `gates_self_check`)
3. Atualizar Camada 3 (side-by-side, README) se houver mudança
   visual

Ver [`evals/regression_matrix.md`](regression_matrix.md) pra
matriz feature × gate.

## Anti-padrões

- **Eval cosmético**: refactor que mantém Camada 1 verde mas não
  melhora Camada 3 não conta como avanço de produto
- **Eval inflado**: criar 50 testes triviais novos não melhora
  fidelidade — Camada 1 mede builder, não SKP
- **Eval circular**: usar o próprio output do builder como ground
  truth do teste (tem que ter pinned reference em
  `docs/specs/_assets/`)
- **Skip Camada 3**: aprovar PR só com testes verdes sem
  side-by-side é demo bonita

## TODO

- [ ] Definir métrica numérica pra Camada 3 (e.g. dimensional
      delta entre PDF measure e consensus, room count vs label
      count) — hoje é só prose
- [ ] Integrar Camada 2 ao CI (rodar build canônico no GitHub
      Actions e falhar PR se algum `gates_self_check = false`)
- [ ] Documentar critério de aceite por classe de feature em
      `evals/regression_matrix.md`
