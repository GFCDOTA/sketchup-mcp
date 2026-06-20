# CAMA — DesignIntentSpec da CLASSE procedural

> 3a classe do programa (2026-06-12). Executável: `tools/bed_class.py`;
> geometria: `bed_builder` estendido (base_style plinth/legs/box, reveal
> paramétrico, saia, overhang da cabeceira — defaults neutros).
> Criado-mudo = **constraint satélite** neste ciclo (não classe completa).

## DNA da classe

1. **Tamanhos são SKUs BR discretos** — 0.88/1.38/1.58/1.93 × 1.88/1.88/1.98/2.03.
   Colchão NUNCA se interpola (sabotagem width=1.20 FAIL).
2. **O colchão domina a silhueta:** `thickness/sleep_surface ∈ [0.28, 0.60]` —
   abaixo é tablado (colchão esmagado), acima é colchão-no-chão.
3. **Cabeceira nunca trono:** `above/width ≤ 0.55`; e a DERIVAÇÃO respeita —
   `hb_above = min(0.78, 0.52·W, arquétipo+nível)` (solteiro não usa cabeceira
   de casal). Total do chão ≤ 1.40.
4. **Leveza da base (anti bloco-maciço):** plinth exige reveal ≥ 0.06; legs
   exige pés ≥ 0.08; box exige SAIA ou pés ≥ 0.10. Box flush puro = caixote.
5. **Planta humana:** `length/width ∈ [1.0, 2.2]` (king ~1.05, solteiro ~2.1).

## Arquétipos

| | platform (japandi) | upholstered | box |
|---|---|---|---|
| surface | 0.38 baixa | 0.57 | 0.62 alta |
| colchão | 0.20 firme | 0.25 | 0.28 |
| cabeceira | 0.24 madeira fina | 0.50 estofada 0.14 + wings | 0.38 |
| base | plinto reveal 0.10 | pés 0.18 | box + saia |

## Criado-mudo (satélite — `nightstand_satellite_gate`)

- topo do criado ≈ topo do colchão (`±0.08`); **o alvo é DERIVADO da cama**:
  platform → criado ~0.38m; upholstered ~0.57; box ~0.62. Provado: criado
  padrão 0.55 numa platform FALHA (primeira constraint ENTRE classes do programa).
- profundidade ≤ 0.45 (circulação lateral); posição canônica não colide com
  colchão/cabeceira.

## Anti-patterns (sabotagens provadas)

colchão esmagado · cabeceira-trono · bloco maciço (box flush) · colchão
interpolado · cama-mesa (surface 0.78) · king curto · criado desnivelado.

## FASE 0 — diagnóstico do builder que existia

Anatomia boa (plinto+estrado+colchão+cabeceira+travesseiros+manta), mas sem
teoria: validate raso, hardcodes (reveal 0.08 fixo), sempre plinto, sem
arquétipos, `mattress_inset` declarado e não usado. Upgrades subiram pro
builder/spec (base_style/leg_height/reveal/skirt/headboard_overhang) com
defaults neutros — exemplar histórico byte-idêntico.
