# KITCHEN_TO_100 — roteiro pra cozinha planta_74 a 100%

> **Papel:** BACKLOG CURATOR do `KITCHEN_MATERIAL_SPEC_LAB`. Consolida 5 auditorias
> adversariais (geometria/módulos · material/render · ergonomia/layout · spec×modelo ·
> pipeline/persistência) num roteiro ORDENADO e acionável.
>
> **Verdade de base:** Felipe foi explícito — *"a cozinha NÃO está finalizada, falta
> muito detalhe, MUITA ponta solta"*. Este doc NÃO declara nada pronto. É a lista do que
> está ERRADO e do que FALTA, em ordem de ataque.
>
> **Regra de congelamento (GOLDEN_SAMPLE_004):** geometria / pia / layout / módulos estão
> CONGELADOS. Toda microtarefa marcada **`[GEO]`** mexe em geometria congelada e **exige
> OK explícito do Felipe** antes de tocar. Tarefa **`[PELE]`** (material/luz/medidor/gate/
> pipeline/doc) pode ser atacada JÁ.
>
> ```
> referência = LINGUAGEM · PDF = POSIÇÃO · gates = SEGURANÇA · Felipe = PASS
> ```

---

## 0. Achado de maior valor antes de qualquer coisa (ler primeiro)

Várias auditorias reportaram **"geladeira com cor errada [201,203,207] inox claro"** como
ALTA. Conferindo a fonte real, o quadro é mais sutil — e isso muda a prioridade:

- A cor de geometria (`kitchen_layout.py:31 RGB_GELADEIRA=[201,203,207]` e
  `:65 _KC["geladeira"]=[216,220,227]`) é **placeholder de FORMA**. No render V-Ray ela é
  **sobrescrita pelo tema**.
- `tweak_vrscene.py:141-148`: com `KITCHEN_GELADEIRA=black` (variantes B/C), a geladeira já
  vira **preto fosco antidigital `metalness=0`** (≈`[36,36,38]`, exatamente o spec D8). O
  filler genérico cream também **já foi forçado a preto** (`:135`).
- **Conclusão:** o "bloco brilhante" que o Felipe vê em B **não é a geladeira** (essa já está
  preta no tema B) — é **iluminação insuficiente no lado direito** (a coluna some no escuro) e
  **falta de eletros modelados**. Logo a prioridade #1 real é **LUZ**, não recolorir a geladeira.
- **Ação de cor que sobra:** alinhar o placeholder de geometria pra preto (higiene, evita
  regressão se alguém renderizar SEM tema). É P3 baixa, não ALTA. Ver MT-15.

> **Lição reutilizável #L1:** *o RGB de geometria é placeholder de forma; o tema V-Ray vence.*
> Não tratar "cor de geometria errada" como bug de aparência sem antes confirmar se há tema
> ativo sobrescrevendo. Auditar a CADEIA (geometria → vray_export tex_map → tweak_vrscene tema),
> não só o primeiro arquivo.

---

## 1. FASE PELE — fechável SEM liberar geometria (ATACAR PRIMEIRO)

Tudo aqui é material / luz / textura / medidor / gate / pipeline / doc. **Não precisa de OK
do Felipe pra geometria** (precisa do veredito VISUAL dele no fim, via gate GPT, por ser
mudança de aparência — `gpt-review-gate`).

### 1A. Luz e render (o gargalo visual do moody) — `[PELE]`

| # | O quê | Onde | Conserto |
|---|---|---|---|
| **MT-01** | **Fill light no lado direito (leste).** Coluna da geladeira some no escuro em B — lê como "buraco preto", não eletro premium. Rig só cobre o oeste (KEY+FILL2). | `tools/kitchen_vray.py:77-93` (fills) | Adicionar `FILL3` LightSphere lado leste (~`190,650,60`), intensity ~15-18, radius ~24. Re-render B. Verificar coluna definida. |
| **MT-02** | **Paredes/teto chapados puro-preto** = "vácuo de estúdio", perde profundidade. | `tools/vray_export.rb:150-153` (`KITCHEN_WALLS` default `[40,40,44]`) | Subir `KITCHEN_WALLS` p/ `[60,60,65]` (cinza escuro real, não void) OU ruído procedural discreto. Re-render B. |
| **MT-03** | **LED linear pode estar descentrado** vs pia/cooktop — wash assimétrico ("luz de palco"). | `tools/kitchen_vray.py:88-92` (LightRectangle `center y=648`, `u_size=50`) | Confirmar `y_pia`/`y_cooktop` por inspeção do SKP; recentralizar `center` em `(y_pia+y_cooktop)/2`; ajustar `u_size` ao vão útil. |

### 1B. Material / textura (realismo da pele) — `[PELE]`

| # | O quê | Onde | Conserto |
|---|---|---|---|
| **MT-04** | **Backsplash B usa `stone_gold.png` por default** se `KITCHEN_STONE_TEX` não for passado → tema dark não diferencia, veio "grita". D7 pede veio CONTROLADO. | `tools/vray_export.rb:77` (default `stone_gold.png`) + `kitchen_vray.py` | Criar `dark_gold_controlled.png` (veio 30-40% menos saturado). Passar `KITCHEN_STONE_TEX=dark_gold_controlled.png` explícito ao render B. |
| **MT-05** | **Sem hierarquia tampo×backsplash** — tampo `reflect=0.16`, backsplash `0.18`, quase idênticos. Backsplash é zona de "olhar", devia ser um toque mais reflexivo. | `tweak_vrscene.py:150-154` | Subir backsplash `reflect` p/ `0.20-0.22` (um degrau acima do tampo). |
| **MT-06** | **Piso chapado/neutro no render** ("flutuando"), sem textura de cimento queimado matte. D9 = porcelanato cimento grafite médio acetinado. | `kitchen_vray.py` (sem `KITCHEN_FLOOR` setado nas variantes) + `vray_export.rb:135-136` | Gerar/usar `cimento_graphite_matte.png`; setar `KITCHEN_FLOOR=` no render; scale grande `[80,80]`. (Piso CONTÍNUO sala+cozinha é `[GEO]`, ver MT-19 — aqui é só TEXTURA do piso já existente no render.) |
| **MT-07** | **MAT_SATIN (laca Fendi) parece plástico** — `reflect=0.05` quase matte puro, sem micro-brilho de laca premium. (Só relevante p/ temas claros/A; B/C já põem armário preto.) | `tweak_vrscene.py:41` (`satin`) | Subir `reflect` 0.05→0.12-0.15 e `reflect_glossiness` 0.58→0.62-0.68. Validar que não regride o tema B. |
| **MT-08** | **Coifa inox dark pode sumir** no fundo preto (`kc_inox` diffuse `[0.05]` + reflect `0.28`). Confirmar se coifa é 100% preto ou preto+trim inox. | `tweak_vrscene.py:137-139` | Decidir via spec §5: se trim inox, subir reflect p/ `[0.35]`+gloss `0.68` (lê metal); se 100% preto, manter. |

### 1C. Medidores / gates / validação (pega regressão sem render) — `[PELE]`

| # | O quê | Onde | Conserto |
|---|---|---|---|
| **MT-09** | **`fridge_vent_gap` PASSA falso** — mede `GEL_W*100 - fridge_body_w` ≈ 2.8cm, range `(2,6)` aprova, MAS spec exige ≥3cm/LADO (6cm total). O gate aceita o que o spec reprova. | `kitchen_ergonomics.py:74` + `ERGO:30` | Endurecer: range `(6,12)` total OU medir por-lado e exigir ≥3. Vai virar WARN/FAIL na geometria atual (70cm) — **é o sinal que justifica MT-16 `[GEO]`**. |
| **MT-10** | **Circulação reporta PASS falso** — chama `sanity_room` (door-clearance), NÃO mede largura do triângulo de trabalho (≥1.2m geladeira↔cooktop). | `kitchen_ergonomics.py:109` | Adicionar medida `circulation_width_m` = dist. centro-geladeira↔centro-cooktop no eixo da parede; WARN se <1.2m; reportar separado do door-clearance. |
| **MT-11** | **Sem check torneira↔aéreo** — torneira gourmet alta pode bater no aéreo baixo (spec §8 alerta). | `kitchen_ergonomics.py` (novo) / `kitchen_layout.py:176` | Adicionar assert: `AEREO_Z0 − topo_torneira ≥ 0.35m` senão WARN. |
| **MT-12** | **Sem check respiro topo geladeira** (≥5cm topo, fridge.md §5) nem altura mínima do `aereo_fridge` (≥0.20m). | `kitchen_layout.py:363-369` (aereo_fridge) | Adicionar asserts WARN: respiro topo ≥0.05m; altura aereo_fridge ≥0.20m. (lógica, não muda geometria existente.) |
| **MT-13** | **Sem check cooktop↔pia** (separação térmica/respingo ≥0.5m). | `kitchen_ergonomics.py` (novo) | Medir dist. centro-cooktop↔centro-pia; WARN se <0.5m. |
| **MT-14** | **`hood_clearance` comentário confuso** (mistura under-cabinet 45-65 com chaminé 70-80). Mede 55cm = PASS correto, só o comentário engana. | `kitchen_ergonomics.py:27` | Trocar comentário p/ `(slim integrated: 45-65; range-hood tradicional: 70-80)`. Sem mudança de lógica. |
| **MT-15** | **Wire dos gates de cozinha no pipeline determinístico** — `run_deterministic_gates.py` não roda `kitchen_ergonomics` / `cave_check` / `fake_luxury_check` / `maintenance_check` (cuba preta, D5) / `continuity_check`. Mudança de material não dispara gate. | `tools/run_deterministic_gates.py:42-108` | Conditional: se `fixture==planta_74 e room==r004`, rodar também os gates de cozinha + os 3 por-variante do D5/KITCHEN_DECISIONS. Feature flag no argparse. |

### 1D. Higiene de cor de placeholder — `[PELE]` (baixa)

| # | O quê | Onde | Conserto |
|---|---|---|---|
| **MT-16** | **Alinhar RGB placeholder da geladeira a preto** (higiene anti-regressão se renderizar SEM tema). NÃO é o bug visual (ver §0). | `kitchen_layout.py:31,65` | `RGB_GELADEIRA`/`_KC["geladeira"]` → `[36,36,38]`. Atualizar comentário `:54-56` (paleta antiga "clara quente" → BLACK_WOOD_GOLD) e `tampo`/`backsplash` `_KC` p/ `[30,29,32]`+veio `[150,128,86]` (doc/anti-regressão; o tema já manda no render). Cuba `_KC["cuba"]`→preto coordenado. |

### 1E. Persistência / rastreabilidade do método — `[PELE]`

| # | O quê | Onde | Conserto |
|---|---|---|---|
| **MT-17** | **Variantes A/B/C sem registro canônico** — env vars soltos, sem JSON de params/verdicts/aprovação. Felipe muda de ideia → zero rastreabilidade. | novo: `artifacts/reference_lab/kitchen/KITCHEN_VARIANT_MATRIX.json` | Documentar cada variante: env vars, render params, gate verdicts, status (approved/pending). Loader `kitchen_preset_loader.py` opcional p/ `--preset A|B|C` sem editar código. |
| **MT-18** | **`.claude/scratch/kitchen_vray.py` DUPLICADO** (5.5K, idêntico ao `tools/`, referenciado por `batch_theme_render.py`). Edição em um não propaga. | `tools/kitchen_vray.py` (fonte viva) vs `.claude/scratch/kitchen_vray.py` | Apontar `tools/` como canônico; remover/ignorar a cópia scratch (ou documentar propósito). Conferir que `batch_theme_render.py` aponta p/ `tools/`. |
| **MT-19** | **GOLDEN_SAMPLE_004 sem snapshot geométrico imutável** — DECISIONS declara freeze mas não há `geometry_report.json` de referência pra diff. | novo: `artifacts/reference_lab/GOLDEN_SAMPLE_004_FROZEN_GEOMETRY.json` | Extrair consensus+geometry_report do .skp bakeado como linha de base. Regra: change vs este arquivo = `touches_frozen_geometry=true`. |
| **MT-20** | **Texturas candidatas sem mapa de uso** (15 PNGs em `assets/textures/procedural/candidates/`, ex. `stone_dark_gold_A/B/C/D`). | novo: `assets/textures/procedural/TEXTURE_USAGE_MAP.json` | Mapear cada candidato → variante(s) que usa, status (candidate/approved/rejected), feedback Felipe. |
| **MT-21** | **Sem teste automatizado de tema/material** — `batch_theme_render.py` (com `C_stress_nero`) nunca testado em CI; mudar sintaxe de material não avisa. | novo: `tests/test_kitchen_batch_themes.py` | Fixture planta_74, `BATCH_RENDER=0`, validar p/ cada tema: PNG existe, render_bbox válido, gate_summary OK. |
| **MT-22** | **Veredito visual A/B/C não persistido** — specs descrevem variantes mas não há review side-by-side com anotações + checkboxes de gate. | novo: `artifacts/reference_lab/kitchen/KITCHEN_VARIANT_VISUAL_REVIEW.md` | Renders lado-a-lado + achados (B coluna escura, C dourado demais, A safe) + checkbox cave/fake_luxury/maintenance/continuity por variante + veredito. |

---

## 2. FASE GEOMETRIA — EXIGE liberar o GOLDEN_SAMPLE_004 (depende do Felipe)

Nada aqui se toca sem **OK explícito do Felipe** (KITCHEN_DECISIONS D8 é explícito: *"NÃO
alterar módulos sem validar circulação/scorecard"*). Bloqueadas também por **D1-D3** (cooktop
indução / airfryer / coifa = infra), que mudam dimensão de nicho e devem ser batidas antes.

> **Ordem interna:** primeiro o que o gate endurecido (MT-09) acusar (geladeira), depois os
> eletros embutidos (escopo grande), por último a marcenaria de assinatura.

| # | O quê | Onde | Conserto | Pré-req |
|---|---|---|---|---|
| **MT-23 `[GEO]`** | **Nicho da geladeira 70→75cm + respiro real.** `GEL_W=0.70`, `inset_side=0.014` (1.4cm/lado) — abaixo dos ≥3cm/lado críticos (fridge.md §5-6, §3). Porta não abre 90°, gaveta-freezer não sai. | `kitchen_layout.py:21,129` | `GEL_W 0.70→0.75`; `inset_side 0.014→0.06-0.07` (≥3cm/lado honesto). Re-validar circulação+scorecard (D8). | D8; MT-09 (gate que prova o gap) |
| **MT-24 `[GEO]`** | **TORRE QUENTE inexistente.** `TORRE_W/D/H` definidos (`:22`) mas **nunca construídos** em `build_boxes`. Forno (70-80L, nicho 60×60×56) + micro (trim kit, 60×38-40×40-45) = OBRIGATÓRIOS, ausentes. | `kitchen_layout.py:build_boxes` (após `:369`) | Construir torre na ponta OPOSTA à geladeira (calor longe do frio, §0.3): forno base 70-90cm + micro base 140-150cm, com respiro/tomada, kinds próprios (`kc_forno`/`kc_micro`). | D1 (220V) |
| **MT-25 `[GEO]`** | **LAVA-LOUÇAS ausente.** OBRIGATÓRIO (§6), 45cm slim ao LADO da cuba (mesmo ponto hidráulico oeste). Não modelada. | `kitchen_layout.py:build_boxes` | Módulo 45×82×55-57 ao lado de `sink_module`, frente integrável (`kc_lavalouca`). Comprime bancada / desloca cooktop. | D6 |
| **MT-26 `[GEO]`** | **AIRFRYER sem nicho.** Uso real (fritura diária), nicho ABERTO ventilado 45×50×45, respiro ≥5cm (§4). Ausente. | `kitchen_layout.py:build_boxes` | Nicho aberto na torre/coluna, base 90-110cm, respiro ≥5cm, tomada no fundo (`kc_airfryer`). | D2 |
| **MT-27 `[GEO]`** | **Cooktop = só vidro fino**, sem rasgo real no tampo nem respiro ≥2cm sob o vidro (§1). | `kitchen_layout.py:158-168` | Rasgo no tampo (~56×49 no módulo 60), 4 zonas visíveis, respiro 2cm embaixo. | D1 |
| **MT-28 `[GEO]`** | **Coifa não-validada vs cooktop** — clearance 45-65cm não é assert (hoje calha em 55cm por acaso). Modelar como depurador slim 60cm. | `kitchen_layout.py:194-200,347-351` | Assert clearance cooktop→coifa ∈ [45,65]; coifa 60cm depurador recirculação. | D3 |
| **MT-29 `[GEO]`** | **Cuba não-undermount.** Modelada como bojo visível por todos os lados; spec §7 = undermount (borda invisível, pedra contínua por cima). | `kitchen_layout.py:169-176` | Parametrizar `sink_type=undermount`; pedra passa contínua, junta só silicone embaixo. **Coluna da pia** (cuba+lava-louças+purificador disputam) precisa ser contada. | D5 |
| **MT-30 `[GEO]`** | **Purificador sob-pia ausente** (§9, obrigatório) + bica preta discreta. Disputa coluna com lava-louças. | `kitchen_layout.py:build_boxes` | Reservar espaço no gabinete da pia; biquinha preta no tampo. | D5/D6 (coluna) |
| **MT-31 `[GEO]`** | **Marcenaria sem perfil Gola real.** Puxador é BARRA (`:152,155`), spec §11 = Gola horizontal preto fosco (cava recuada ~1-2cm) em TODOS módulos. Geladeira tb (barra `:135-137` → pega embutida/cava, §3+§0.4). | `kitchen_layout.py:135-137,152,155` | Trocar barra por cava/Gola recuada (sombra ~0.01m, recuo ~0.02-0.03m). É a assinatura "caixa→planejado". | D4 (onde vai o bronze) |
| **MT-32 `[GEO]`** | **Piso CONTÍNUO cozinha+sala não modelado.** D9 = plano único, transição zero; render hoje é cozinha ISOLADA sem chão. (Textura do piso = MT-06 `[PELE]`; a MALHA contínua é `[GEO]`.) | SKP `planta_74_furnished` / `furnish_apartment` | Adicionar malha de piso contínua sala+cozinha; câmera que mostra a integração. | D9 |

> **Eletros como densificação `[PELE]`-friendly (nuance do pipeline audit):** o audit de
> pipeline nota que dá pra adicionar os eletros como *placeholder-boxes com kind próprio*
> (`kc_cooktop`/`kc_forno`/...) **sem alterar o LAYOUT** dos módulos congelados — só densificar.
> Se o Felipe topar essa leitura ("densificar ≠ reabrir layout"), MT-24/25/26/27 podem cair pra
> `[PELE]`. **Mas como ocupam espaço e podem deslocar cooktop/bancada, o default aqui é `[GEO]`
> + OK do Felipe.** Decisão a bater com ele.

---

## 3. Resumo por SEVERIDADE (visão de cima)

**ALTA (ataca já, lado PELE):** MT-01 (luz lado direito), MT-09 (gate vent_gap falso-PASS),
MT-10 (circulação falso-PASS), MT-15 (wire dos gates de cozinha).
**ALTA (depende do Felipe, lado GEO):** MT-23 (nicho geladeira), MT-24 (torre quente),
MT-25 (lava-louças). Estas três são *infra* — D1/D6/D8 antes.
**MÉDIA:** MT-02..MT-08 (pele/material), MT-11..MT-14 (medidores), MT-17..MT-22 (persistência),
MT-26..MT-31 (eletros/cuba/gola).
**BAIXA:** MT-16 (cor placeholder), MT-32 (piso contínuo é médio mas pós-decisão), decor
volumétrico (tábua/vaso vertex-modeling — upgrade pós-golden, não listado como MT própria).

---

## 4. Lições REUTILIZÁVEIS pros outros cômodos

- **L1 — RGB de geometria é placeholder; o tema V-Ray vence.** Auditar a cadeia
  geometria→`vray_export` tex_map→`tweak_vrscene` tema antes de chamar "cor errada" de bug
  visual. (Origem: §0 deste doc — 3 das 5 auditorias erraram a prioridade da geladeira.)
- **L2 — "material fora da lista do tema = bug recorrente."** O cream `ph_filler` genérico
  escapava da listagem `kc_*` e virava painel claro. Toda peça nova precisa de **kind
  prefixado e listado** no tema, senão herda cor de placeholder. Vale pra QUALQUER builder.
- **L3 — gate que passa não prova spec.** `fridge_vent_gap` e `circulation` reportavam PASS
  medindo a coisa ERRADA (o inset, o door-clearance). **Gate verde ≠ spec atendido** —
  conferir que a métrica do gate é a métrica do spec. (testing.md: cobertura de comportamento.)
- **L4 — separar PELE de GEOMETRIA no backlog desbloqueia trabalho.** ~22 de 32 tarefas
  fecham sem tocar o congelado. Sempre triar `[PELE]` vs `[GEO]` antes de pedir OK humano —
  ataca a pele em paralelo enquanto a decisão de geometria espera.
- **L5 — "densificar ≠ reabrir layout".** Adicionar peça com kind próprio sem mover módulo
  pode ser `[PELE]`; mas se a peça OCUPA espaço e desloca vizinho, é `[GEO]`. Default
  conservador: na dúvida, marca `[GEO]` e pergunta.
- **L6 — constante definida ≠ construída.** `TORRE_W/D/H` existiam há tempo mas o builder
  nunca instanciou a torre. Grep "está definido" não prova "está no .skp" — conferir o
  `build_boxes`/loop real. Vale auditar todo builder por constantes órfãs.
- **L7 — toda variante precisa de matriz canônica (env→verdict→status).** Render solto + env
  var hardcoded = zero rastreabilidade quando o humano revisita em 2 meses. (MT-17/22.)

---

## 5. Ordem de execução recomendada (a primeira primeiro)

1. **MT-18** (matar duplicata scratch — evita editar o arquivo errado nas próximas).
2. **MT-01** (luz lado direito) → re-render B → **gate GPT** (maior ganho visual, lado PELE).
3. **MT-09 + MT-10** (endurecer gates falso-PASS) → vira o sinal objetivo que justifica MT-23.
4. **MT-15** (wire gates de cozinha no pipeline) → daqui pra frente toda mudança dispara gate.
5. **MT-04 + MT-05 + MT-02 + MT-06** (pele: pedra controlada, hierarquia, paredes, piso) → re-render B → gate GPT.
6. **MT-17/19/20/21/22** (persistência — fecha rastreabilidade do método).
7. **MT-11..MT-14, MT-16** (medidores e higiene restantes).
8. **PARAR e levar ao Felipe:** D1-D9 + OK pra liberar geometria → então MT-23..MT-32.
