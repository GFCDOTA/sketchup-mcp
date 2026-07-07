# SPEC-A — Re-render da SALA no estilo black/wood/gold + corrigir exposição

- **Sessão:** 2026-06-22 · linha STUDIO · branch `feat/sofa-class-from-reference`
- **Status:** 🟢 em execução
- **ROI:** maior ganho visível do backlog (handoff studio).

## Problema (olhar antes de tweakar)
A prova V-Ray viva (`vray_pipeline_proof.png`) tem 2 defeitos:
1. **Mesa de centro ESTOURADA** (branco nuclear). Causa REAL no `.vrscene`: o tampo
   tem `diffuse=AColor(0.617,0.533,0.407)` (bege claro literal) numa superfície
   horizontal pegando a luz do céu pela janela. `apply_scene_materials` existe mas
   **nunca é chamada** → a mesa fica com o BRDF cru do export.
2. **Paleta = `modern_warm_minimal`** (beges claros), não o black/wood/gold do Felipe.

## Goal
A MESMA geometria (`runs/scenes/living_room_modern_warm_minimal`) renderizada no
estilo **BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE** (premium, não bruto, não caverna,
não fake-gold) + mesa de centro sem estourar.

## Abordagem (skin-swap, geometria CONGELADA)
Espelha os temas de cozinha (`apply_theme_black_wood_gold`): override de diffuse+BRDF
por PAPEL nos materiais `_fz_*` da cena, no `.vrscene`, SEM rebuildar o `.skp`. Reusa
o vocabulário de cor/BRDF já validado pelo GPT no DNA da cozinha (não re-litigar paleta).

Nova função `apply_scene_theme_black_wood_gold(text)` em `tools/tweak_vrscene.py`;
novo kwarg `scene_theme` em `tweak()`/`tweak_file()`/`render_scene_vray()`.

### Diretriz de material (por papel)
| papel | material `_fz_*` | tratamento |
|---|---|---|
| sofá (hero) | `sofa__seat/back/arm` | charcoal (textura mantida) + `fabric_sheen` |
| mesa centro tampo | `coffee_table__top` | **nogueira** `AColor(0.11,0.05,0.022)` + wood matte ⇒ **mata o estouro** |
| mesa centro pés | `coffee_table__leg_*` | preto metálico |
| tapete | `rug__field/border_*` | charcoal profundo (ancora o "black") |
| piso | `floor` | textura madeira mantida + satin sutil |
| luminária + mesa lateral haste/base | `floor_lamp__stem/base`, `side_table__stem/base` | **bronze/dourado discreto** (o "gold") |
| mesa lateral tampo | `side_table__top` | pedra escura |
| cortina | `curtain__fold_*` | taupe profundo (doma a janela) + haste bronze |
| quadro moldura | `wall_art__frame_*` | preto metálico |
| parede | `wall_*` | greige quente um pouco mais fundo (SEM caverna) |

### Exposição
Mesma receita da prova (iso100/f7/sh160/sky0.3) **+ `burn=0.85`** (comprime o
highlight da janela). Sem fill novo no v1 (paredes ainda claras o bastante p/ bounce) —
se ficar caverna, fill no v2.

## Aceite
- [ ] PNG novo gerado por `render_scene_vray` (~68s).
- [ ] Mesa de centro **não** estourada.
- [ ] Paleta lê black/wood/gold (sofá preto, madeira quente, bronze discreto), não caverna, não fake-gold.
- [ ] Montage before/after + pergunta ao Felipe. **Veredito visual é do Felipe** (regra chrome-only — NÃO autodeclarar IMPROVED/SAME/WORSE).

## Guard-rails (sem o gate interior-designer vivo, :8765 down)
- Paredes NÃO vão a preto (caverna). Greige quente mid.
- Gold = bronze escovado DISCRETO só nos metais (haste/base), nunca veio dourado espalhado (fake-luxury).

## Resultado (2026-06-22) — 🟡 aguardando veredito visual do Felipe
Iterei 5 renders (v2-v5 SU-free a partir do `scene_raw.vrscene` cacheado, ~45s cada;
v1 via pipeline completo). Aprendizados objetivos (mean luminance, px clipados):
- **Estouro da mesa: RESOLVIDO** — v1..v5 têm **0 px clipados** (era clipado na prova). O
  tampo virou nogueira (diffuse 0.617→0.11) ⇒ mata o highlight especular.
- **v1** (só material, sem fill): mean=26 = **caverna objetiva** → rejeitado por mim.
- **`burn`/bright_mult é multiplicador GLOBAL** (não só highlight) → abaixá-lo escurece tudo;
  ferramenta ERRADA pra tirar da caverna. Pra levantar o cômodo sem estourar a janela:
  **exposição (iso/f) + sky + fill**, não burn.
- **v5 = candidato** (mean=35, moody-premium, 0 clipado): abajur aceso ancora o canto.

### Receita v5 (reproduzível, SU-free a partir do raw cacheado)
```
tweak(raw, iso=125, fnum=6.3, shutter=160, sky=0.4, width=1500, height=1000,
      materials=True, scene_theme="black_wood_gold",
      fill_lights=[ {pos: lamp(0.64,3.64,1.45)→in, int 1.8, r 0.18m, col (1,.72,.40)},
                    {pos: sofa(2.6,3.2,2.5)→in,  int 0.9, r 0.6m,  col (1,.85,.66)} ])
```
Material/lamp-glow ficam no CÓDIGO (`apply_scene_theme_black_wood_gold`). A receita de
EXPOSIÇÃO acima é passada no call (ainda não há preset — TODO se Felipe aprovar o look).

## Aceite — status
- [x] PNG novo (`runs/scenes/living_room_modern_warm_minimal/vray_black_wood_gold_v{1..5}.png`).
- [x] Mesa **não** estourada (0 px clipados, objetivo).
- [x] Paleta black/wood/gold, abajur aceso (não caverna), bronze discreto (não fake-gold).
- [ ] **Veredito visual do Felipe** — montage `bwg_before_after.png` apresentado; aguardando.
