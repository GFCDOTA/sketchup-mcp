# planta_74 — REBUILD em escala correta PT_TO_M=0.0259 (APROVADO Felipe 2026-06-08)

> Felipe aprovou 0.0259 (cota/overlay > render). Este é o rebuild + validação.
> **NÃO promovido ao canônico** `artifacts/planta_74/planta_74.skp` ainda —
> aguarda coordenação com a sessão paralela antes do PR (regra dele, passo 6).

## Artefatos (este diretório)
- `model.skp` — shell em escala correta. **SHA256 `b7101037b7521f03b58bcea5d7cef1dedf8087319ea5215a8ec6eef27529260e`**
- `model_top.png` / `model_iso.png` / `model_floors_top.png` — renders pós-build
- `geometry_report.json` — gates self-check
- `_shell_polygon.json` — geometria intermediária (PDF points, scale-independent)

## Reprodução exata
```bash
PT_TO_M=0.0259 .venv/Scripts/python.exe -m tools.build_plan_shell_skp \
  fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json \
  --out artifacts/review/planta_74/scale_rebuild_0259_20260608/model.skp \
  --force-skp
```
(O `.rb` lê `ENV['PT_TO_M']` em `build_plan_shell_skp.rb:33`; default 0.0352 **intacto** —
quadrado_demo e outros não mudam. Fixture NÃO mutado.)

## Validação de escala — tabela de cotas (a prova decisiva)
Confirmado no build: `model_top.png.proj.json` traz `pt_to_in = 1.0197 = 0.0259 × 39.37`. ✅

| cômodo | cota impressa PDF | @0.0352 (ANTES) | @0.0259 (DEPOIS) | veredito |
|---|---|---|---|---|
| **SUÍTE 01** (r000) | 5.45 × 4.00 | 7.41 × 5.43 ❌ | **5.46 × 4.00** | **PASS** (≈ exato) |
| SUÍTE 02 (r003) | 2.40 × 3.20 | 3.25 × 4.39 ❌ | **2.39 × 3.23** | PASS |
| COZINHA (r004) | 2.90 | 3.90 ❌ | **2.87** | PASS |
| LAVABO (r007) | 1.55 × 1.20 | 2.04 × 1.61 ❌ | **1.50 × 1.18** | PASS |

Área bbox (c/ paredes): ANTES **183 m²** (irreal p/ um "74") → DEPOIS **~99 m²**. Fator 1.359×.

## SUÍTE 01 primeiro (passo 4 do Felipe) — **PASS**
- Cota PDF 5.45 × 4.00 → build 5.46 × 4.00 (erro < 0.2%).
- Geometria fiel (mesma consensus que já bate o overlay PDF; só o anchor pt→m mudou).

## Gates determinísticos (geometry_report.json)
`plan_shell_group_exists` ✅ · `wall_shell_is_single_group` ✅ ·
`floors_separated_from_walls` ✅ · `default_material_faces_zero` ✅

## Integridade da geometria (model_top.png)
Paredes, 8 cômodos (cozinha/sala/terraço/suíte01/suíte02/banho01/banho02/lavabo) e portas
com arco — todos presentes e posicionados como no overlay PDF. O rebuild **não** alterou a
geometria relativa (é PDF-points × PT_TO_M); só o tamanho absoluto, agora correto.

## Por que NÃO há "render before/after" lado a lado
Render framed faz zoom-to-fit → ANTES e DEPOIS ficam **visualmente idênticos** (foi exatamente
por isso que a escala 1.36× passou batido por semanas). A prova de escala é a **cota/overlay**
(acima), não o render. (Consistente com `visual_regression_20260530T180822Z/decision.md`.)

## Veredito (matriz de fidelidade) — **PASS**
Geometria alinha ao PDF; cotas reproduzidas; portas presentes/orientadas; sem cômodo falso;
report determinístico e cota concordam. Escala era o único bug confirmado → **corrigida**.

## Próximo (gated)
1. Coordenar com a sessão paralela (passo 6) → promover ao canônico + PR.
2. Só DEPOIS: V-Ray/material/round-edges na escala certa (resolve o WARN de arestas duras).
