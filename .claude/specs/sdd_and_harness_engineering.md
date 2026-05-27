# Spec-Driven Development + Harness Engineering — sketchup-mcp

Como aplicar SDD e harness pra evitar que feature vire demo
bonita sem caminho de volta pro produto.

## SDD — Spec antes de mudança relevante

Mudança que toca contrato (kind_v5 routing, schema de consensus,
formato de `geometry_report.json`, nova fidelidade dimension)
exige **spec curto** ANTES do código.

Local: `docs/specs/<FP-NNN>_<short_slug>.md` (convenção FP-NNN do
repo, ver PRs #186, #189, #193).

Conteúdo mínimo:

```md
# FP-NNN: <título>

## Problema
1-3 parágrafos. O que está errado / faltando.

## Proposta
O comportamento novo / mudança de contrato.

## Casos de teste
Lista de casos que o harness vai cobrir. Inclui fixture.

## Critério de aceite
O que conta como sucesso. Idealmente verificável por teste.

## Out of scope
O que esta mudança NÃO faz.
```

## Harness — teste prova o comportamento

Spec sem harness não conta. Cada feature relevante precisa:

1. **Fixture mínima** sob `fixtures/<plant_or_micro>/`. Quadrado
   é o exemplo canônico.
2. **Teste automatizado** sob `tests/` que falha sem a feature e
   passa com.
3. **Evidência visual** quando aplicável: render + side-by-side.
4. **Aplicação no pipeline real** quando passar — caso contrário
   é só prova de paradigma.

## Contract suite atual

Os 6 testes que pinam o contrato vivo:

| Teste | Pina |
|---|---|
| `tests/test_quadrado_canonical_smoke.py` | Canonical success gate |
| `tests/test_wall_shell_canonical.py` | No notches / no slivers |
| `tests/test_window_aperture_contract.py` | window vs door routing |
| `tests/test_window_aperture_geometry.py` | SKP-level invariants (skip sem SU) |
| `tests/test_build_plan_shell.py` | Pure-Python primitive coverage |
| `tests/test_wall_stub_canonicalization.py` | FP-026 stub elimination |

Todos Python-only — não exigem SU pra rodar. Testes SKP-level
fazem skip clean quando não há `.skp` disponível.

## Fluxo spec → teste → artefato

```
1. Identify gap / opportunity
   ↓
2. Spec curto em docs/specs/FP-NNN_*.md
   ↓
3. Fixture micro em fixtures/<micro>/
   ↓
4. Teste vermelho em tests/test_<feature>.py
   ↓
5. Implementação em tools/build_plan_shell_skp.{py,rb}
   ↓
6. Teste verde
   ↓
7. Aplicar na planta real (planta_74)
   ↓
8. Side-by-side PDF vs SKP
   ↓
9. Promote pra artifacts/<plant>/ se mudou fidelidade
   ↓
10. PR contra develop com spec + teste + artifact
```

## Anti-padrões

### Harness fake

Teste que sempre passa, teste que mocka o que deveria ser
verificado, teste que cobre só happy path conhecido. Não conta.

### Spec sem harness

Doc que define comportamento mas nada falha quando o
comportamento quebra. Vira ADR de prateleira.

### Harness sem aplicação na planta real

Micro-fixture verde + planta_74 ignorada = demo bonita. Critério
de fechamento da feature exige aplicação real OU rejeição
justificada.

### Gates mínimos antes de PR

```bash
python -m pytest tests/ -q
git -C <repo> status --short          # diff revisado
git -C <repo> log --oneline -1        # commit message correto
```

Build SKP local se mudou builder. Não dispensar evidência visual
quando aplicável.

## TODO — validar contra repo

- [ ] Confirmar lista exata de testes (rodar `pytest --collect-only`)
- [ ] Confirmar se há lint / type check obrigatório
      (`ruff`, `mypy` no pyproject?)
- [ ] Verificar se há CI workflow no `.github/workflows/` e que
      gates rodam lá
