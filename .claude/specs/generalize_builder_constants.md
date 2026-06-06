# Blueprint — generalizar as constantes do builder para qualquer planta

> **STATUS: BLUEPRINT (não-executado de propósito).** 2026-05-31.
> Decisão do gate (modo B, redteam, `a_b_c_decision_with_tradeoff` 08:11Z):
> **NO-GO em mexer no `build_plan_shell_skp.{py,rb}` agora** — é o arquivo mais
> QUENTE (fidelidade em voo) e a config per-plant **não tem consumidor** até uma
> 2ª planta existir → seria clobber + infra-pela-infra. Este doc é o **groundwork
> não-colidente**: inventário + schema + plano de swap-in, pra executar como uma
> troca rápida e limpa **quando a árvore esfriar**.

## 1. Inventário das constantes planta_74 (o que precisa virar config)

| constante | local | valor | controla | já overridável? |
|---|---|---|---|---|
| `PT_TO_M` | `build_plan_shell_skp.rb:33` | `0.19 / 5.4` | escala pts→m (âncora) | ✅ `ENV['PT_TO_M']` + lê `wall_thickness_pts` do consensus |
| nominal `0.19` (m) | `pdf_overlay_verify.py:61`, `opening_audit.py:36` | `0.19` | espessura de parede real (âncora física) | ❌ literal |
| `WALL_HEIGHT_M` | `build_plan_shell_skp.rb:37` | `2.70` | extrusão da parede | ❌ |
| `PARAPET_HEIGHT_M` | `build_plan_shell_skp.rb:39` | `1.10` | altura de mureta/peitoril (soft barrier) | ❌ |
| `DOOR_HEIGHT_M` | `build_plan_shell_skp.rb:50` | `2.10` | altura da folha de porta | ❌ |
| `DOOR_THICK_M` | `build_plan_shell_skp.rb:51` | `0.04` | espessura da folha | ❌ |
| `WINDOW_SILL_M` | `build_plan_shell_skp.rb:58` | `0.90` | peitoril (base da abertura 3D) | ❌ |
| `WINDOW_HEAD_M` | `build_plan_shell_skp.rb:59` | `2.10` | verga (topo da abertura 3D) | ❌ |
| `DEFAULT_PDF_CROP` | `compose_side_by_side.py:42` | `(0.05,0.07,0.78,0.55)` | recorte do desenho na página | ❌ tunado p/ planta_74 |
| `DEFAULT_PDF_SCALE` | `compose_side_by_side.py:37` | `2.0` | DPI do render do PDF | ❌ |
| `page_idx` | `compose_side_by_side.py:45` (+ overlays) | `0` | qual página do PDF | ❌ (assume pág. 1) |
| `brightness_thresh` | `overlay_diff.py:217` | `160` | corte de pixel "parede escura" | ⚠️ tunado p/ as cores da planta_74 |

**Já generalizado (não mexer):** descoberta de consensus (`_load_consensus` com glob `consensus*.json`) + os gates determinísticos — **provado**: `run_deterministic_gates --fixture quadrado` = PASS.

## 2. Schema proposto — `fixtures/<plant>/plant.json`

```json
{
  "schema_version": "1.0.0",
  "pdf": { "path": "<plant>.pdf", "page_idx": 0, "crop_fractional": [0.05, 0.07, 0.78, 0.55], "render_scale": 2.0 },
  "scale": { "wall_thickness_m": 0.19 },
  "heights_m": { "wall": 2.70, "parapet": 1.10, "door": 2.10, "door_thickness": 0.04, "window_sill": 0.90, "window_head": 2.10 },
  "render": { "brightness_thresh": 160 }
}
```

Defaults = os valores BR-residenciais atuais da planta_74 → **migração não-quebra**: planta_74 sem `plant.json` se comporta idêntico.

## 3. Plano de swap-in (executar QUANDO a árvore esfriar)

1. `tools/plant_config.py`: `load_plant_config(fixture)` → lê `fixtures/<plant>/plant.json`, com **fallback pros defaults planta_74** (zero mudança de comportamento sem o arquivo).
2. Ruby builder: passar `heights_m` + `scale` via ENV (o mecanismo `ENV['PT_TO_M']` já existe — replicar pra alturas) OU via um JSON lido no autorun. Sem `plant.json` → defaults atuais.
3. `compose_side_by_side.py`: aceitar `--crop` / `--page` / `--scale` lidos do `plant.json`; defaults atuais preservados.
4. Validar: `quadrado` + `planta_74` com e sem `plant.json` produzem o mesmo `.skp` de hoje (regressão), e uma 3ª planta com `plant.json` diferente respeita os novos valores.
5. **NÃO** remover os defaults planta_74 dos `--fixture` (cosmético, e remover quebra comandos de sessões em voo).

## 4. Gargalo humano (desbloqueia o consumidor real — opção C)

A config só tem ROI com uma **2ª planta real**. Isso precisa de input HUMANO (não existe extrator):
- **PDF** da 2ª planta (vetorial de preferência).
- **consensus.json** autorado/anotado por humano (walls/openings/rooms/soft_barriers) + a **âncora física de escala** (uma dimensão real conhecida → `wall_thickness_m`).

→ **Pedido ao Felipe:** qual é a 2ª planta? Manda o PDF + a dimensão-âncora, e a anotação do consensus a gente faz junto (humano no loop). Aí o swap-in (§3) vira produto de verdade.
