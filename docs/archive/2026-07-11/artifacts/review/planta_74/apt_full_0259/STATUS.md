# Apê INTEIRO @ PT_TO_M=0.0259 — estado WIP (pra validação do Felipe + consulta GPT)

Branch `chore/suite01-scale-gate`. Build: `apt_full_0259.skp` (shell 0.0259 +
`collect_boxes` de todos os cômodos). Renders: `apt_full_top_0259.png` / `_iso`.

## ✅ Conversão de escala — FECHADA no apê inteiro
Todos os sites de `pt→in`/`pt→m` hardcoded 0.0352 agora derivam do `PT_TO_M` env:
`spatial_model`, `geometry_sanity`, `furnish_apartment.bedroom_designer_boxes`,
`bedroom_designer._items_to_boxes`, `auto_camera`, `kitchen_layout`, `bathroom_layout`,
`living_room_planner`. Default 0.0352 INTACTO; 46 testes verdes; fixtures não mutados.

## ✅ 5 cômodos certos @0.0259 (geometry_sanity PASS)
SUÍTE 01 (cama queen+cabeceira+2 criados+guarda-roupa+tapete) · SUÍTE 02 · COZINHA ·
BANHO 01 · BANHO 02. Áreas batem as cotas do PDF.

## ❌ 2 cômodos WIP — CALIBRAÇÃO de brain (NÃO conversão de escala)
Domínio dos planners (sessão paralela). No render aparecem como os blocos coloridos
FLUTUANDO ACIMA do prédio (sala) + bancada na porta (lavabo):
- **SALA r002**: `living_room_planner.plan_living` dá `NO_VALID_SOFA_WALL` @0.0259 (sofá
  default 2.2m não acha parede válida na sala correta-menor) → cai no `furnish_apartment.living_boxes`
  (fallback antigo) que tem **scale-leak próprio** → móveis em coords 0.0352, fora do shell 0.0259.
  FIX = (1) env-fixar o `living_boxes`/old-brain; (2) re-tunar sofá/regras p/ a escala real.
- **LAVABO r007**: bancada bloqueia a porta (overlap 72in²) no cômodo de 1.9m² — bancada
  dimensionada p/ o inflado. FIX = bancada menor/condicional p/ lavabo pequeno.

## Próximos passos sugeridos (p/ você decidir com o GPT)
1. **Mergear** `chore/suite01-scale-gate` no PR `feat/mobiliar-bedroom-layout`→develop
   (escala fechada + 5 cômodos + Suíte 01 reviewable). Coordenar via `.ai_bridge/HANDOFF.md`.
2. **Re-calibrar** os brains sala+lavabo p/ a escala 0.0259 (sessão paralela).
3. **V-Ray premium** dos outros cômodos (o `auto_camera` já gera câmera 0.0259 correta).
4. **Round-edges** (plugin V-Ray `texRoundEdges`) p/ o WARN "arestas duras".

## Reprodução
`PT_TO_M=0.0259 python -c "import json; from tools.furnish_apartment import CONSENSUS, collect_boxes;
collect_boxes(json.loads(CONSENSUS.read_text('utf-8')))"` → boxes; depois `place_layout_skp.rb`
sobre `scale_rebuild_0259_20260608/model.skp`.
