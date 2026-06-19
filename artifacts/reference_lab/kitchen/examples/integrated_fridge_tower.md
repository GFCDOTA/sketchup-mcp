# CARD: Torre de geladeira integrada

**Problema:** geladeira solta parece eletro jogado no canto — quebra a leitura de
"planejado" e deixa um buraco/gap feio ao lado.

**Solução:** transformar em **nicho planejado** (`loose_object → planned_niche_system`):
painel lateral (gable/filler) + armário superior **flush** sobre a geladeira + respiro
técnico no topo + material coordenado com a marcenaria. A geladeira inox fica *inset*
no nicho fendi.

**Aplicável em:** cozinha, lavanderia, torre quente (forno/micro embutidos).

**Gate:**
- `furniture_overlap_gate` — o nicho não pode sobrepor outro módulo.
- `kitchen_ergonomics::fridge_vent_gap` — respiro 2–6 cm (real: ~2,8 cm).
- não bloquear porta/circulação.

**Valores (golden sample):** geladeira `GEL_W=0.70 / GEL_D=0.66 / GEL_H=1.80`;
filler lateral 16 cm; armário acima full-depth flush (`z0 = GEL_H − 0.05`); corpo inox
[216,220,227] inset; nicho/torre fendi [224,215,199]; respiro 2,8 cm.

**Token:** `references/tokens/planned_fridge_tower.json`

**Evidência:** torre inteira à direita no [hero V-Ray](../../planta_74/furnished/kitchen_angles/cozinha_vray_hero.png). GPT: deixou de parecer "remendo".
