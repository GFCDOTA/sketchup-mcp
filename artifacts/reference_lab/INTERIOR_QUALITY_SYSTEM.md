# INTERIOR_QUALITY_SYSTEM — contrato de qualidade de interiores

> A cozinha provou que qualidade **não vem só de render bonito** — veio de PDF anchor +
> componentização + ergonomia + linguagem + golden sample + GPT critic + PASS do Felipe.
> Este é o contrato pra repetir isso em TODOS os cômodos. **A máquina garante que não fica
> ERRADO; este sistema mede se fica BOM.**

## A régua (quem garante o quê)
```
Gates                  = impedem merda objetiva (espaço/ergonomia/colisão/circulação)
Golden sample          = mantém a LINGUAGEM (black_wood_gold = GOLDEN_SAMPLE_004)
GPT critic             = pega feiura óbvia (luz chapada, branco, bloco solto)
Felipe                 = aprova o GOSTO (PASS final)
Arquiteto/marceneiro   = valida a EXECUÇÃO real (fora do escopo do código)
```

## Ordem obrigatória (NÃO inverter)
```
1. layout / ancoragem / circulação   <- primeiro
2. mobiliário (qualidade dos móveis)
3. linguagem (black_wood_gold)
4. V-Ray (render premium)
```
**Regra de ouro: NÃO propagar estética em cima de layout ruim.** Cômodo FAIL no scorecard não
recebe linguagem/V-Ray até corrigir forma.

## Quality Scorecard (por cômodo) — `tools/interior_quality_scorecard.py`
7 dimensões, cada uma **PASS / WARN / FAIL** (`PASS`=segue · `WARN`=bom, polir · `FAIL`=não estilizar):

| # | dimensão | o que mede | gate |
|---|---|---|---|
| 1 | **layout / zonas** | o cômodo tem as zonas que o tipo exige (estar+jantar; cama+roupa; preparo/cocção/lavar) | `room_zone_gate` |
| 2 | **ancoragem** | rack/guarda-roupa/torre flush em parede; peça de centro isenta | `furniture_wall_anchor_gate` |
| 3 | **componentização** | cada móvel selecionável, nomeado, nada colado no shell | (deterministico) |
| 4 | **qualidade do móvel** | módulo que deveria ser detalhado não pode ser cubo proxy (parts<3) | `furniture_quality_gate` |
| 5 | **planned-niche candidatos** | objeto solto/proxy que deveria virar sistema planejado | `planned_niche_candidate_gate` |
| 6 | **linguagem / golden sample** | paleta/material coerente com GOLDEN_SAMPLE_004 | `golden_sample_style_gate` |
| 7 | **render / apresentação** | flat prova forma; V-Ray prova material; herói = premium | (visual: GPT/Felipe) |

Dimensões 1–5 são **determinísticas** (rodam sem humano). 6 começa determinística (paleta) e
fecha visual. 7 é GPT/Felipe. Combina com os gates antigos (geometry_sanity, furniture_overlap,
kitchen_ergonomics, + os 8 de `gates/reference_system_gates.md`).

## Os 5 gates novos (a sala provou que faltavam)
- **furniture_wall_anchor_gate** — rack/TV/guarda-roupa flutuando reprova; peça de centro (mesa
  de centro/tapete/jantar/ilha) é isenta. (sala: Rack TV 15cm = WARN não-flush)
- **room_zone_gate** — zonas exigidas por tipo. (sala: jantar AUSENTE = FAIL)
- **furniture_quality_gate** — proxy/cubo onde devia ser detalhado. (sala: Rack TV parts=1 = WARN)
- **planned_niche_candidate_gate** — objeto solto que vira sistema. (sala: Rack TV → painel de TV)
- **golden_sample_style_gate** — paleta vs GOLDEN_SAMPLE_004 (placeholder até o tema entrar).

## Resultado do baseline da sala (demonstração)
`SALA r002 (LIVING) -> OVERALL: FAIL` — layout_zonas FAIL (sem jantar), ancoragem/qualidade/niche
WARN (rack proxy quase-flutuando). **→ corrigir forma ANTES de black_wood_gold.** Ver
[`living_room/LIVING_ROOM_BASELINE_AUDIT.md`](living_room/LIVING_ROOM_BASELINE_AUDIT.md).

## Estratégia híbrida (custo × qualidade)
```
1. Cozinha            = GOLDEN_SAMPLE_004 (feito)
2. Sala              = cômodo-herói (polish profundo) — é vizinha da cozinha, não pode cair
3. Suíte master      = 2º herói
4. Banheiros/lavabo/  = "gated-good" (scorecard PASS/WARN + spot-check do Felipe), sem hero V-Ray
   quartos secundários
```
A máquina garante o PISO (scorecard). O golden sample garante a DIREÇÃO. O GPT a CRÍTICA. O Felipe
o GOSTO. O marceneiro a EXECUÇÃO. Felipe não vira gargalo de 7 cômodos.
