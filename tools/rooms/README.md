# Módulos de cômodo

> Gerado por `python -m tools.navigation.rooms_index --write` a partir dos perfis de especialista, do catálogo de
> capacidades e dos arquivos versionados. Não editar à mão.

Regras: um dono por comportamento; cômodo não importa outro cômodo; o que dois cômodos usam vai para `shared/`;
capacidade só existe com símbolo + teste (+ prova L2 para `L2_PASS`). Ver `.claude/rules/rooms-and-capabilities.md`.

## Cozinha — `tools/rooms/kitchen/`

- **Papel:** planeja e constrói · estado do perfil `LEGACY_PROVIDER_PRESENT`
- **Escopo:** Cozinha: layout linear em caixas/pecas com a pia presa a parede oeste do PDF; gabinete parametrico de frentes lisas e porta Shaker (moldura + painel rebaixado) sobre ele. Gavetas e ferragens ainda NAO existem como capacidade.
- **Capacidades:** `kitchen.layout.galley` (L2_PASS); `kitchen.sink-anchor-guard` (L1_PASS); `kitchen.ergonomics.audit` (UNTESTED); `kitchen.cabinet.plain-fronts` (L2_PASS); `shared.cabinet.parametric` (L2_PASS, shared); `kitchen.cabinet.shaker-door` (L2_PASS); `shared.cabinet.front.shaker` (L2_PASS, shared)
- **Lacunas:** `bind.kitchen.drawer` — gaveta e ferragens: nao ha builder de caixa de gaveta nem fixture L2; so existe a recipe; `bind.kitchen.countertop` — tampo separado com chanfro: sem builder nem fixture; `bind.kitchen.sink-cutout` — recorte de cuba e canal umido: sem builder nem fixture
- **Fragmentos do especialista:** `cabinetry`, `countertop_and_sink`, `ergonomics`, `layout_and_placement`, `reference_truth`
- **Arquivos (29):**
  - raiz do módulo: `README.md`, `__init__.py`, `anchor_rules.py`, `functional_interfaces.py`, `layout.py`, `solver_policy.py`, `specialist.md`, `specialist.v1.json`
  - `capabilities/`: `__init__.py`, `bake_theme.py`, `cabinet.py`, `cabinet_flow.py`, `ruby/recolor_kitchen_theme.rb`, `ruby/render_kitchen_angles.rb`, `shaker.py`, `shaker_flow.py`, `vray.py`
  - `fragments/`: `cabinetry.fragment.v1.json`, `countertop_and_sink.fragment.v1.json`, `ergonomics.fragment.v1.json`, `layout_and_placement.fragment.v1.json`, `reference_truth.fragment.v1.json`
  - `knowledge/`: `index.v1.json`
  - `planning/`: `__init__.py`, `cabinet_placement.py`, `preview.py`
  - `validation/`: `__init__.py`, `ergonomics.py`, `wall_regression.py`

## Sala — `tools/rooms/living/`

- **Papel:** planeja e constrói · estado do perfil `LEGACY_PROVIDER_PRESENT`
- **Escopo:** Sala de estar e jantar da planta: sofa, rack/painel de TV, mesa. Planeja em caixas/pecas sobre o shell; nao altera paredes, portas nem janelas.
- **Capacidades:** `living.layout.boxes` (L1_PASS); `living.sofa.class` (L1_PASS); `living.sofa.gate` (L1_PASS)
- **Fragmentos do especialista:** `case_goods`, `layout`, `sofa`
- **Arquivos (42):**
  - raiz do módulo: `__init__.py`, `armchair_class.py`, `coffee_table_class.py`, `components.py`, `dining_table_class.py`, `furnishing.py`, `planner.py`, `rack_class.py`, `sofa_class.py`, `specialist.md`, `specialist.v1.json`
  - `capabilities/`: `__init__.py`, `make_synthetic_rooms.py`, `ruby/render_sala_eyelevel.rb`, `ruby/sofa_premium_harness.rb`, `ruby/sofa_premium_integrate.rb`, `ruby/sofa_program/build_sofa_3seat_v1.rb`, `ruby/sofa_program/build_sofa_eval_suite.rb`, `ruby/sofa_program/build_sofa_from_config.rb`, `ruby/sofa_program/configs/sofa_archetypes.json`, `ruby/sofa_program/configs/sofa_eval_cases.json`, `ruby/sofa_program/configs/sofa_schema.json`, `ruby/sofa_program/configs/sofa_vray_material_spec.json`, `ruby/sofa_program/sofa_components.rb`, `ruby/sofa_program/sofa_generator.rb`, `ruby/sofa_program/sofa_primitives.rb`, `ruby/sofa_program/sofa_vray_render.rb`, `sofa_class_matrix.py`, `sofa_fabric_material.py`, `sofa_furnish_fase1_compare.py`, `sofa_premium_harness.py`, `sofa_venezia_compare.py`, `sofa_venezia_room.py`
  - `fragments/`: `case_goods.fragment.v1.json`, `layout.fragment.v1.json`, `sofa.fragment.v1.json`
  - `knowledge/`: `index.v1.json`
  - `planning/`: `__init__.py`, `layout_candidates.py`
  - `validation/`: `__init__.py`, `sofa_gate.py`, `sofa_placement_gate.py`

## Quarto — `tools/rooms/bedroom/`

- **Papel:** planeja e constrói · estado do perfil `LEGACY_PROVIDER_PRESENT`
- **Escopo:** Quartos e suites: cama, criados-mudos e guarda-roupa. Planeja em caixas/pecas sobre o shell; nao altera a arquitetura.
- **Capacidades:** `bedroom.layout.boxes` (L1_PASS); `bedroom.bed.build` (L1_PASS); `bedroom.wardrobe.build` (L1_PASS); `bedroom.wardrobe.gate` (L1_PASS)
- **Fragmentos do especialista:** `bed`, `layout`, `nightstand`, `wardrobe`
- **Arquivos (21):**
  - raiz do módulo: `__init__.py`, `bed_class.py`, `designer.py`, `furnishing.py`, `layout.py`, `layout_decisions.py`, `specialist.md`, `specialist.v1.json`
  - `capabilities/`: `__init__.py`, `make_synthetic_bedrooms.py`, `place_bedroom_skp.py`
  - `fragments/`: `bed.fragment.v1.json`, `layout.fragment.v1.json`, `nightstand.fragment.v1.json`, `wardrobe.fragment.v1.json`
  - `knowledge/`: `index.v1.json`
  - `validation/`: `__init__.py`, `bed_gate.py`, `bed_placement_gate.py`, `nightstand_gate.py`, `wardrobe_gate.py`

## Banheiro — `tools/rooms/bathroom/`

- **Papel:** planeja e constrói · estado do perfil `LEGACY_PROVIDER_PRESENT`
- **Escopo:** Banheiros e lavabo: louca e acessorios; sem marcenaria. Planeja em caixas/pecas sobre o shell.
- **Capacidades:** `bathroom.layout.boxes` (L1_PASS); `bathroom.wet-room.guard` (L1_PASS)
- **Fragmentos do especialista:** `layout`, `vanity`, `wet_room`
- **Arquivos (14):**
  - raiz do módulo: `__init__.py`, `layout.py`, `solver_policy.py`, `specialist.md`, `specialist.v1.json`, `validation.py`
  - `capabilities/`: `__init__.py`, `estudio_banheiro_scene.py`, `render_banho_auto.py`, `render_banho_vray.py`
  - `fragments/`: `layout.fragment.v1.json`, `vanity.fragment.v1.json`, `wet_room.fragment.v1.json`
  - `knowledge/`: `index.v1.json`

## Serviço — `tools/rooms/service/`

- **Papel:** planeja e constrói · estado do perfil `COMPOSITE_SERVICE_AND_TERRACE`
- **Escopo:** Area de servico e terracos como no consensus (conjunto composto): armarios, tanque e maquinas em caixas/pecas.
- **Capacidades:** `service.layout.boxes` (L1_PASS)
- **Fragmentos do especialista:** `layout`
- **Arquivos (6):**
  - raiz do módulo: `__init__.py`, `layout.py`, `specialist.md`, `specialist.v1.json`
  - `fragments/`: `layout.fragment.v1.json`
  - `knowledge/`: `index.v1.json`

## Closet — `tools/rooms/closet/`

- **Papel:** reusa outro cômodo — reusa `bedroom` · estado do perfil `NO_INDEPENDENT_BRAIN_USE_BEDROOM_JOINERY`
- **Escopo:** Closet: reaproveita a marcenaria do quarto (guarda-roupa); portas de correr nao tem builder. Sem brain proprio.
- **Capacidades:** nenhuma própria (não se inventa brain sem capacidade provada)
- **Lacunas:** `bind.closet.sliding` — closet reaproveita a marcenaria do quarto; portas de correr nao tem builder
- **Fragmentos do especialista:** `sliding_doors`
- **Arquivos (5):**
  - raiz do módulo: `__init__.py`, `specialist.md`, `specialist.v1.json`
  - `fragments/`: `sliding_doors.fragment.v1.json`
  - `knowledge/`: `index.v1.json`

## Home office — `tools/rooms/home_office/`

- **Papel:** reusa outro cômodo — reusa `bedroom` · estado do perfil `NO_INDEPENDENT_BRAIN_USE_BEDROOM_DESIGNER`
- **Escopo:** Home office: reaproveita o designer de quarto; sem builder proprio de mesa/prateleira.
- **Capacidades:** nenhuma própria (não se inventa brain sem capacidade provada)
- **Lacunas:** `bind.home_office.desk` — home office reaproveita o designer de quarto; sem builder proprio
- **Fragmentos do especialista:** `desk`
- **Arquivos (5):**
  - raiz do módulo: `__init__.py`, `specialist.md`, `specialist.v1.json`
  - `fragments/`: `desk.fragment.v1.json`
  - `knowledge/`: `index.v1.json`

## Varanda — `tools/rooms/balcony/`

- **Papel:** só consultivo · estado do perfil `NO_INDEPENDENT_BRAIN_COMPOSITE_SERVICE`
- **Escopo:** Varanda/pergolado/floreira: apenas conhecimento consultivo. Nao ha brain independente: a varanda vive no conjunto de servico do consensus.
- **Capacidades:** nenhuma própria (não se inventa brain sem capacidade provada)
- **Lacunas:** `bind.balcony.pergola` — varanda e advisory: nao ha brain independente (esta dentro do conjunto de servico)
- **Fragmentos do especialista:** `pergola_and_planters`
- **Arquivos (5):**
  - raiz do módulo: `__init__.py`, `specialist.md`, `specialist.v1.json`
  - `fragments/`: `pergola_and_planters.fragment.v1.json`
  - `knowledge/`: `index.v1.json`

## Circulação — `tools/rooms/circulation/`

- **Papel:** só valida · estado do perfil `VALIDATION_ONLY`
- **Escopo:** Corredores, hall e portais: somente validacao (faixa de passagem). Nao posiciona moveis.
- **Capacidades:** `circulation.gate` (L1_PASS)
- **Fragmentos do especialista:** `gate`
- **Arquivos (5):**
  - raiz do módulo: `__init__.py`, `specialist.md`, `specialist.v1.json`
  - `fragments/`: `gate.fragment.v1.json`
  - `knowledge/`: `index.v1.json`
