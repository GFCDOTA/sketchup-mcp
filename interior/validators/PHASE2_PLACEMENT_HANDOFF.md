# Fase 2 — Placement (cama/guarda-roupa/criado): handoff

> Slice DETERMINÍSTICA (sem SketchUp/V-Ray). O que entrou nesta branch e o que
> falta pra etapa VISUAL (que precisa do SU livre + olho do Felipe).

## Feito nesta slice (`feat/bed-wardrobe-placement`)
- **Cobertura de teste do `bed_placement_gate`** — antes o gate cobria
  guarda-roupa/criado na lógica, mas as fixtures só exercitavam **cama**.
  Estendi `_fixtures()` com:
  - `guarda-roupa bloqueando porta` → **FAIL** (também fere circulação).
  - `guarda-roupa sem frente livre` → **WARN** (`WARDROBE_PLACEMENT=FAIL`, soft).
  - `criado solto (longe da cama)` → **WARN** (`NIGHTSTANDS=WARN`).
- **`tests/test_bed_placement_gate.py`** — 9 testes pytest determinísticos:
  quarto válido PASS; cama (hard) FAIL; guarda-roupa/criado (soft) WARN com a
  dimensão certa; **sofá sem regressão** (`plan_living(r002)=OK`); determinismo.
- Verde: **41 passed** (novo + `test_bedroom_layout` + `test_synthetic_bedrooms`).

## Já existia (NÃO foi reconstruído — evitar duplicação)
- `interior/planners/placement_brain.py` — **FurniturePlacementBrain** base
  (`place_against_wall`: candidatos/score/hard-reject/slide, genérico).
- `tools/bedroom_layout.py` — placement real de cama (cabeceira em parede limpa,
  evita janela) + criados flanqueando + guarda-roupa (frente livre, evita porta).
- `interior/planners/living_room_planner.py` — **SofaBrain** (sofá ↔ TV, marco GPT).
- gates: `bed_placement_gate`, `wardrobe_gate`, `nightstand_gate`, `sofa_placement_gate`,
  `validation_report`.

## Regras encodadas no gate (mapeamento p/ as "LL por objeto")
- **LL-BED-001** cabeceira em parede LIMPA (`head_clean`) + cama ancorada + não bloqueia porta.
- **LL-BED-002** cama eixo-alinhada (não rotacionada aleatória) = ORIENTATION.
- **LL-WARDROBE-001** guarda-roupa sem frente livre (clearance `CLEAR_M=0.55`) = FAIL.
- **LL-NIGHTSTAND-001** criado tem que flanquear a cama (≤0.45m) senão "solto".

## Falta pra etapa VISUAL (NÃO feito aqui — precisa SU livre + olho do Felipe)
1. **Build `.skp`** do quarto a partir do layout validado (`place_bedroom_skp.rb` /
   `build_furniture_skp.rb`) — precisa SketchUp (não roda headless confiável aqui).
2. **Render** top / iso / close-up (SU básico ou V-Ray).
3. **GPT visual validation** (PASS/WARN/FAIL no render) — o gate determinístico
   **NÃO substitui** o veredito visual (regra negative-dogfood: olho do Felipe).
4. **Promoção** runs/ → artifacts/ só DEPOIS do visual PASS.

## Como rodar a camada determinística
```
python -m interior.validators.bed_placement_gate r000        # runner (fixtures)
python -m pytest tests/test_bed_placement_gate.py -q          # 9 testes
```
