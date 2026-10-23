# FP-054 F2A — auditoria da F1C e contratos do solver (2026-10-23)

## Estado de partida (develop @ 57d80b2, #396)
F1C: 23 avaliações, 20 interfaces semânticas (18 do builder do banheiro, 2 da âncora da cozinha), 0 heurísticas.

### Os 8 INVALID (findings provisórios — inventário, não correção)
| # | Cômodo | Peça | Regra | Medido | Motivo |
|---|---|---|---|---|---|
| 1 | Banho 01 `r005` | Box | `shower.entry_width` | 0,327 m | vão da porta de correr (folha 0,61 m > fixo 0,46 m; frente 1,02 m → 0,41 m nominal; 0,33 m livres) |
| 2 | Banho 02 `r006` | Box | `shower.entry_front_clearance` | 0,00 m | frente do box encostada na parede oeste (`INTERFACE_OBSTRUCTED`) |
| 3 | Banho 02 `r006` | Box | `shower.entry_width` | 0,00 m | idem |
| 4 | Banho 02 `r006` | Box | `shower.reach_path` | 0,00 m | idem |
| 5 | Banho 02 `r006` | Vaso | `toilet.front_clearance` | 0,523 m | < 0,60 |
| 6 | Lavabo `r007` | Bancada | `lavatory.front_clearance` | 0,044 m | vaso a ~4 cm na frente |
| 7 | Lavabo `r007` | Vaso | `toilet.front_clearance` | 0,032 m | bancada a ~3 cm na frente |
| 8 | Lavabo `r007` | Vaso | `toilet.reach_path` | 0,00 m | zona de uso do vaso desconectada |

### Cozinha
Sem INVALID: frente 1,09 m, alcance 1,34 m (PREFERRED). O "gargalo na entrada" do overlay é a **testemunha** de onde a passagem
limita (1,34 m > 0,90 exigido) — diagnóstico, não defeito. A F2 não fabrica defeito onde a medida passa.

## Contratos entregues (sem mudar layout)
- `core/units.py`: conversão m/cm/mm/in explícita; `pt` só com `pt_to_m` explícito; tolerâncias nomeadas.
- `core/frames.py`: `RoomFrame` (cômodo ↔ planta, rígida, testada por ida-e-volta).
- `tools/rooms/shared/spatial_solver/contracts.py`: `SolverProblem`, `SolverObject`, `DegreesOfFreedom` (discretização
  explícita), `Portal`, `SolverIssue` (erro estruturado), estados `FEASIBLE/INFEASIBLE/UNKNOWN/INVALID_INPUT`,
  `validate_problem` (13 violações cobertas).
- Políticas dos especialistas: `tools/rooms/bathroom/solver_policy.py` (deslizar ±0,40 m ao longo da parede de apoio, passo
  2 cm; box: trocar o lado da frente — `PENDING_FELIPE`) e `tools/rooms/kitchen/solver_policy.py` (bancada ancorada: sem DOF).
- `tools/rooms/shared/spatial_solver/problem.py`: monta os problemas reais dos 4 cômodos, todos válidos, sem tocar em caixas.
