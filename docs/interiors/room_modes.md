# Modos estruturais de sala (A2 sintético)

> Derivado do loop com o ChatGPT (conversa "Crítica de layout sala") +
> fixtures sintéticas (`tools/make_synthetic_rooms.py`). As fixtures provaram
> que o core de layout **generaliza** pra sala retangular normal, mas há **2
> modos estruturais** que o pipeline ainda precisa conhecer. 2026-06-04.

## Fixtures sintéticas (prova de não-overfit, sem nova planta real)

`fixtures/synthetic_rooms/*.json` — salas geradas (porta no canto + porta-vidro):

| fixture | dims | área | estado |
|---------|------|------|--------|
| living_medium_rect_18m2 | 5.0×3.6 | 18 m² | ✅ `estar_ancorado` vence e valida |
| living_large_rect_28m2 | 6.2×4.5 | 28 m² | ✅ vence e valida |
| living_small_rect_10m2 | 3.6×2.8 | 10 m² | ❌ NO_VALID (sala rasa) |
| living_long_narrow | 6.5×2.5 | 16 m² | ❌ NO_VALID (sala-corredor) |

**Gate de sucesso (GPT)** por sala: core válido vence · opcional removido se
bloqueia · circulação passa · tapete ancora sofá+mesa · parede-TV ruim perde ·
layout sem poltrona aceito quando a poltrona bloqueia fluxo.

Correções de generalização já aplicadas (commit `2fc38ce`):
- **`_sofa_perp`**: sofá à distância-alvo (~2.8 m), flutua quando a sala é funda,
  encosta quando rasa. (Antes colava na parede oposta → overfit na profundidade
  da planta_74; a medium sintética dava sofá-TV 4.46 m.)
- **`SIZE_FURN` / `_room_size`**: móveis adaptam por tamanho (small/medium/large).

## Modo LONG_NARROW (`aspect_ratio > 1.80`) — "sala-corredor"

Comum em apê. Diagnóstico na long_narrow: o brain **já** escolhe a parede longa
pra TV (✓), mas rack+mesa+sofá no eixo curto (2,5 m) **invadem a parede oposta**.

Estratégia (GPT):
- sofá com eixo longo **paralelo à parede longa**; TV/rack na parede longa **oposta**;
  visada sofá-TV atravessa a **largura curta**; corredor longitudinal preservado.
- hard gates: `reject_tv_wall se short_end` (a menos que sem alternativa) ·
  `sofa_long_axis ∥ room_long_axis` · `longitudinal_path ≥ 0.80` ·
  `rack_depth ≤ 0.35` · `coffee_table_depth ≤ 0.45`.
- **se `short_dim < 2.70 m`: sem mesa de centro** (mesa lateral / narrow bench / puff).
- score: +30 sofá ∥ parede longa · +25 TV na parede longa oposta.

Implementação prática: degradação de programa (sem mesa + móveis slim quando
`short_dim` apertado), não reorientação completa — o brain já acerta a parede.

## Modo SMALL_SHALLOW (`<12 m²`, raso) — "kitnet"

Sala compacta com varanda/porta crítica. O sofá encostado bloqueia a varanda na
parede oposta.

Estratégia (GPT): **degradação de programa** — tentar o programa mínimo
(sofá + rack + tapete), só retornar NO_VALID se **nem o mínimo** passa a
circulação. Não forçar layout completo.

## Ordem (GPT)

1. **LONG_NARROW** (estrutural, prioridade) — degradação narrow + gates de forma.
2. **SMALL fallback** — degradação de programa.
3. Refinos finos.
4. (depois) outros cômodos: quarto, cozinha.
