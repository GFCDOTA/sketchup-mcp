# Centralização de Escala — fonte única `core/scale.py` (2026-06-09)

Branch `chore/centralize-scale-source` (off develop). **Infra/fundação — ZERO produto.**
Mata a doença de múltiplas fontes de verdade pra escala (a causa de "shell 0.0259 / móvel
0.0352 / gate em outra escala" que queimou sessões inteiras).

## Antes → Depois
| | Antes (em develop) | Depois |
|---|---|---|
| Quem define `PT_TO_M` | `spatial_model.py` (`0.19/5.4`) | **só `core/scale.py`** (env-driven) |
| Quem define `PT_TO_IN` | 6 arquivos (`(0.19/5.4)*39.37` espalhado) | **só `core/scale.py`** (`PT_TO_M*M_TO_IN`) |
| Helper `M(m)` | 2 cópias (`bedroom_layout`, `layout_candidates`) | **`core/scale.py`** (re-export) |
| Gate anti-duplicação | nenhum | `repo_health_gate.py` check #5 |

## `core/scale.py` — a fonte única
```
PT_TO_M   pt→m   = float(env['PT_TO_M'] or 0.19/5.4)   # override por env/config; default = wall-thickness
M_TO_IN   m→in   = 39.3700787402                         # constante FÍSICA (scale-independente)
PT_TO_IN  pt→in  = PT_TO_M * M_TO_IN
M(m)/to_pt(m) = m/PT_TO_M · to_m(pt)=pt*PT_TO_M · to_in(pt)=pt*PT_TO_IN · m_to_in(m)=m*M_TO_IN
```
**0.0259 NÃO é hardcoded** — é o anchor aprovado do planta_74, entra via `PT_TO_M=0.0259` no env. Default 0.0352 não muda cego.

## Arquivos migrados (develop) — só importam de `core.scale` agora
`spatial_model.py` (re-export, mantém `from tools.spatial_model import PT_TO_M`) ·
`bathroom_layout.py` · `furnish_plan.py` · `kitchen_layout.py` · `place_bedroom_skp.py` ·
`place_layout_skp.py` (PT_TO_IN) · `bedroom_designer.py` (local pt_to_in) ·
`bedroom_layout.py` · `layout_candidates.py` (M()).

## Gate (check #5 do `repo_health_gate.py`)
Proíbe, fora de `core/scale.py`: definição nível-módulo de `PT_TO_M`/`PT_TO_IN` **e** o literal
`0.19/5.4` (em código; comentários/docstring do próprio gate são exceção). **Roda como pytest.**
Isso FORÇA qualquer branch futura a migrar — inclusive as feature branches abaixo, no merge.

## Verificação
- **Default 0.0352 byte-idêntico** (`PT_TO_M=0.035185…`, `PT_TO_IN=1.3852`) — **500 testes passam**, 0 regressão.
- **`PT_TO_M=0.0259` propaga** sem cópia local (`kitchen.PT_TO_IN=1.0197`, `M(1)=38.6`).
- **grep final**: nenhuma definição de escala fora de `core/scale.py`.
- **gate PASS**.
- **Verificação adversarial (workflow 3-agente): 3× CONFIRMED** — semântica (M()=m→pt, alturas `*39.37`=m→in, corners=PT_TO_IN=pt→in, zero inversão); completude+gate (só `core/scale.py` define; gate bloqueia nova def); comportamental (default `0.035185` byte-idêntico, `0.0259` propaga `1.0197`, imports limpos).
- **Follow-up (não-bug, consistência)**: 5 arquivos usam o literal `39.3700787402` (m→in) em vez de `M_TO_IN` importado (kitchen_layout 2×, bathroom_layout, place_layout_skp, place_bedroom_skp, bedroom_designer). Math correta; migrar p/ `M_TO_IN` numa próxima passada de limpeza.

## Pendente p/ feature branches (o gate força no merge)
Estes têm definição de escala local e NÃO estão em develop ainda — ao mergear, o gate os reprova
até migrarem pra `core.scale` (mesmo padrão): `auto_camera`, `geometry_sanity`, `sofa_builder`
(atenção: o `PT_TO_IN=39.37` dele é **m→in** = `M_TO_IN`, NÃO pt→in), `living_room_planner`,
`placement_brain`, `bed_placement_gate`, `sofa_placement_gate`, `compute_room_cam`,
`furnish_apartment` (pt_m local na mobiliar). E `chore/suite01-scale-gate` (meu env-fix) converge aqui.

## Ruby (inventário, NÃO tocado — regra do Felipe)
`build_plan_shell_skp.rb:35` `PT_TO_IN = PT_TO_M * M_TO_IN` — já lê `ENV['PT_TO_M']` (single-source-ish
via env). SU/V-Ray pesado fica pra outra slice; aqui só inventário.

## Aceite
✅ grep só `core/scale.py` define PT_TO_M/PT_TO_IN · ✅ demais importam · ✅ 0.0259 propaga ·
✅ testes verdes · ✅ gate PASS · ✅ este report · ✅ sem tocar SU/V-Ray/furniture/layout/camera/render.
