# ARCHITECT_ANSWER_CONTRACT v1

## Metadata
question_id: `sofa_spec_001` · consultant: `Consult GPT` · mode: `SPEC` · asset: `sofa` ·
cycle: `CYCLE-003 / MT-SOFA-003` · theme: `BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE` · verdict: `PASS_WITH_CONSTRAINTS`

## Veredito
`PASS_WITH_CONSTRAINTS`
A referência Venezia é uma boa base para reconstruir a classe sofá porque resolve o problema central do
sofá-caixa: tem perfil baixo, couro grafite/slate, pernas finas de ferro preto, costura aparente, almofadas
com volume e linguagem modern-industrial. Para o apê compacto de 74m², a classe deve usar a Venezia como
referência formal, mas não copiar a dimensão integral sem checar circulação.

## SOFA_BUILD_SPEC

Arquétipo principal: `industrial_boutique_slim_leather_sofa`
Sofá industrial boutique premium, couro grafite/slate, assento profundo, almofadas volumosas, braços
médios/baixos suavizados, encosto baixo levemente inclinado, pernas finas de ferro preto. Confortável,
premium e leve, nunca bloco quadrado.

### Dimensões — 3 lugares compacto premium
```json
{"type":"3_seat_compact","width_cm":205,"depth_total_cm":88,"seat_depth_usable_cm":58,"seat_height_cm":43,
 "back_height_total_cm":76,"backrest_visible_height_from_seat_cm":33,"backrest_angle_deg":10,"arm_height_cm":58,
 "arm_width_cm":15,"seat_cushion_thickness_cm":16,"back_cushion_thickness_cm":12,"leg_height_cm":14,"leg_thickness_cm":3}
```
Faixas: `{"width_cm":[198,213],"depth_total_cm":[84,90],"seat_depth_usable_cm":[56,61],"seat_height_cm":[42,45],"back_height_total_cm":[74,78],"arm_height_cm":[56,61],"arm_width_cm":[14,17]}`

### Dimensões — 2 lugares compacto
```json
{"type":"2_seat_compact","width_cm":165,"depth_total_cm":86,"seat_depth_usable_cm":57,"seat_height_cm":43,
 "back_height_total_cm":76,"backrest_visible_height_from_seat_cm":33,"backrest_angle_deg":10,"arm_height_cm":58,
 "arm_width_cm":14,"seat_cushion_thickness_cm":16,"back_cushion_thickness_cm":12,"leg_height_cm":14,"leg_thickness_cm":3}
```
Faixas: `{"width_cm":[155,175],"depth_total_cm":[82,88],"seat_depth_usable_cm":[55,60],"seat_height_cm":[42,45],"back_height_total_cm":[74,78],"arm_height_cm":[56,61],"arm_width_cm":[13,16]}`

### Proporção braço ↔ assento ↔ encosto
Ler como 4 sistemas separados: pés/base leve + assento volumoso + encosto macio + braços contidos.
```json
{"arm_width_ratio":"0.07-0.09","seat_visual_mass_ratio":"0.45-0.55","back_visual_mass_ratio":"0.22-0.30",
 "leg_void_height_ratio":"0.15-0.18","arm_height_vs_back":"arm <= back_top"}
```
Braço não domina; assento > braço; encosto com volume/inclinação (não parede reta); pernas criam vão/sombra;
preservar profundidade útil antes de reduzir conforto.

### Assento
```json
{"seat_cushions":2,"cushion_top_crown_cm":2.5,"front_edge_radius_cm":4,"seam_gap_cm":1.2,"piping_radius_cm":0.8,"seat_surface":"slightly_crowned_not_flat"}
```
2 almofadas grandes (3 lugares); separação sutil; borda frontal arredondada; topo com leve abaulamento; nunca plano chapado.

### Encosto
```json
{"backrest_angle_deg":10,"back_cushion_thickness_cm":12,"back_top_radius_cm":3,"back_panel_offset_from_seat_cm":4,"back_style":"low_slightly_reclined_cushioned"}
```
Não vertical tipo parede; inclinação 8°–12°; topo suavizado; altura baixa/moderna; almofada traseira com espessura.

### Braços
```json
{"arm_height_cm":58,"arm_width_cm_3seat":15,"arm_width_cm_2seat":14,"arm_outer_radius_cm":3,"arm_top_radius_cm":3.5,"arm_front_chamfer_cm":2,"top_stitch_offset_cm":2}
```
Médio/baixo, não bloco; bordas suavizadas; top stitch quebra a massa; estofado, não caixa estrutural; não mais alto que o topo do encosto.

### Base e pés
```json
{"base_type":"thin_black_iron_legs","leg_height_cm":14,"leg_profile":"round_or_square_slim","leg_thickness_cm":3,"front_leg_inset_cm":10,"side_leg_inset_cm":12,"rear_leg_inset_cm":8,"plinth":"forbidden_in_this_variant"}
```
Pernas finas de ferro preto; vão inferior visível; pernas recuadas; plinto proibido nesta variante; não encostar no chão como bloco.

### Raios, chanfros e softness
```json
{"global_soft_edge_cm":2,"seat_front_radius_cm":4,"arm_radius_cm":3,"back_top_radius_cm":3,"cushion_crown_cm":2.5,"forbid_perfect_90_degree_blocks":true}
```

### Tokens de material
```json
{"upholstery":{"token":"slate_graphite_top_grain_leather","color_rgb":[48,50,50],"roughness":0.42,"sheen":0.18,"notes":"couro grafite/slate premium, sem brilho plástico"},
 "legs":{"token":"matte_black_iron","color_rgb":[18,18,18],"roughness":0.55,"metallic":0.7},
 "stitching":{"token":"subtle_top_stitch","color_rgb":[68,68,66],"contrast":"low"},
 "pillows_optional":{"token":"dark_warm_bolster_or_lumbar","allowed":true,"max_count":2}}
```
Compatibilidade BLACK_WOOD_GOLD: peça escura premium; SEM dourado no sofá; metal preto/grafite (não bronze);
couro não-plástico; coadjuvante premium da sala, não peça chamativa.

### Ajuste para sala compacta
```json
{"compact_priority":["preserve_seat_depth","reduce_width_if_needed","keep_legs_visible","avoid_chaise_initially","never_block_circulation"]}
```
Priorizar 2 lugares se circulação apertar; 3 lugares só se parede/nicho permitir; prof. total ideal < 90 cm;
reduzir largura antes de profundidade útil; nunca prof. útil < 54 cm; evitar chaise nesta 1ª versão.

## dna_updates
```json
[
  {"scope":"sofa","rule":"Sofá industrial premium para Felipe deve ser derivado de referência real, com assento profundo, braços contidos, encosto baixo levemente inclinado e pés finos em metal escuro."},
  {"scope":"sofa","rule":"Evitar sofá-caixa: todo sofá precisa ter leitura clara de assento volumoso, braço suavizado, encosto confortável e base leve."},
  {"scope":"material","rule":"Couro grafite/slate funciona bem no BLACK_WOOD_GOLD quando tem roughness controlado e não parece plástico brilhante."},
  {"scope":"compact_living","rule":"Em sala compacta, preservar profundidade útil do assento e reduzir largura antes de sacrificar conforto visual."}
]
```

## anti_patterns
```json
[
  {"id":"sofa_box_block","rule":"Sofá não pode parecer cubo com braços e encosto verticais."},
  {"id":"armrest_too_chunky","rule":"Braço não pode dominar o volume visual nem parecer bloco estrutural."},
  {"id":"flat_cushion","rule":"Almofada não pode ser plano chapado; precisa crown, espessura e borda suavizada."},
  {"id":"wall_backrest","rule":"Encosto não pode ser parede vertical; precisa inclinação e almofada."},
  {"id":"floor_block_base","rule":"Nesta variante, sofá não pode encostar no chão como bloco; precisa pés e vão inferior."},
  {"id":"plastic_black_leather","rule":"Couro preto/grafite não pode parecer plástico brilhante."},
  {"id":"fake_industrial_brutal","rule":"Industrial não pode virar bruto, pesado ou tosco; precisa boutique premium."}
]
```

## build_spec_constraints
```json
{"must_have":["visible_thin_black_iron_legs","slate_graphite_leather","real_cushion_volume","low_or_medium_arms","slightly_reclined_back","subtle_top_stitch","rounded_or_chamfered_edges"],
 "must_not_have":["boxy_block_body","oversized_armrests","flat_seat_planes","vertical_wall_back","heavy_floor_plinth","chrome_legs","glossy_plastic_black"]}
```

## Próxima microtarefa
Título: `MT-SOFA-004 — Construir sofá industrial boutique baseado na referência Venezia`
Descrição: Reconstruir a classe sofá usando a SOFA_BUILD_SPEC acima, gerando variações 2 e 3 lugares, com comparação lado a lado contra o sofá antigo quadrado.

## Prompt curto para próximo render
Gerar sofá industrial boutique premium baseado na referência Venezia: couro grafite/slate, braços médios/baixos
suavizados, assento profundo com volume real, encosto baixo levemente inclinado, costura/top stitch sutil e
pernas finas de ferro preto com vão inferior. Evitar sofá-caixa, braços gigantes, almofada plana, plinto pesado
e couro preto brilhante. Comparar lado a lado com o sofá antigo quadrado.
