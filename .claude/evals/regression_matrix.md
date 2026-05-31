# Regression matrix — sketchup-mcp

Mapa **feature × gate**: quando uma feature mexe em X, quais
gates devem ser exercitados pra confirmar que nada regrediu.

> Este arquivo nasceu majoritariamente TODO. Cada PR que toca
> builder / consensus / kind_v5 deve adicionar uma linha aqui
> antes de mergear, pra que a matriz vire um histórico real.

## Como ler

| Coluna | Significado |
|---|---|
| Feature / area | O que mudou |
| Camada 1 (testes) | Quais `tests/test_*.py` cobrem |
| Camada 2 (`gates_self_check`) | Quais dos 4 booleans podem regredir |
| Camada 3 (rubric) | Quais dimensões da rubric podem regredir |
| Evidência exigida | Artefato visual mínimo pra PR |

## Matriz inicial (TODO completar)

### Feature: novo `kind_v5` ou ajuste em opening routing

| Camada | Cobertura mínima |
|---|---|
| 1 | `test_window_aperture_contract.py`, `test_window_aperture_geometry.py` |
| 2 | `default_material_faces_zero` (group novo pode esquecer material) |
| 3 | C1 (routing), C2 (soft barriers), C3 (wall_gap) |
| Evidência | side-by-side da fixture micro + planta_74 |

### Feature: mudança no shell polygon (extrude / canonicalise)

| Camada | Cobertura mínima |
|---|---|
| 1 | `test_wall_shell_canonical.py`, `test_build_plan_shell.py`, `test_wall_stub_canonicalization.py` |
| 2 | `plan_shell_group_exists`, `wall_shell_is_single_group` |
| 3 | A1, A2, A3, B1 |
| Evidência | side-by-side planta_74 + render iso |

### Feature: novo gate em `gates_self_check`

| Camada | Cobertura mínima |
|---|---|
| 1 | Novo teste em `tests/` que falha sem o gate |
| 2 | TODO — adicionar boolean novo no `geometry_report.json` schema 1.x.0 |
| 3 | nenhuma (gate é só Camada 2) |
| Evidência | report JSON antes / depois |

### Feature: nova planta (consensus + fixture)

| Camada | Cobertura mínima |
|---|---|
| 1 | Smoke test análogo a `test_quadrado_canonical_smoke.py` |
| 2 | Todos 4 booleans |
| 3 | A, B, C, D completas — primeira passada cria baseline |
| Evidência | artifact promovido completo (6 arquivos + README) |

## Histórico (linha por PR relevante)

| PR | Data | Feature | Gates exercitados | Resultado |
|---|---|---|---|---|
| #193 | 2026-05-26 | FP-026 residual wall stub elimination | A1, A2, Camada 1 (`test_wall_stub_canonicalization`) | OK |
| #192 | 2026-05-26 | junction-aware endpoint extension | A2 | OK |
| #191 | 2026-05-25 | refresh planta_74 + room fidelity baseline | A, B, Camada 2 | WARN justificado (B1) |
| #185 | — | commit canonical planta_74 SKP | A, C, D | baseline inicial |

## Anti-padrões

- **Feature sem linha aqui**: não merge sem registrar
- **Linha sem evidência**: matriz vira fofoca, não rastreabilidade
- **WARN sem justificativa**: WARN é status válido só com prose

## TODO

- [ ] Completar matriz por classe de feature (consensus schema
      change, soft barriers, materials, render path, etc.)
- [ ] Adicionar coluna "automated check?" pra Camada 2 quando CI
      rodar build canônico
- [ ] Vincular linhas históricas a `docs/specs/FP-NNN_*.md`
