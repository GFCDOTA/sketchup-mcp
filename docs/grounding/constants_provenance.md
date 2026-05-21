# Constants provenance — plan_shell exporter + invariant tests

**Status:** audit document (2026-05-20). **NOT a production gate.**
Records where every numeric constant in the plan_shell pipeline
comes from. Most are unsourced today; the table is the starting
point for grounding work (PDF cota extraction, NBR consultation,
measured corpus).

**Why this file exists:** the 2026-05-20 visual-bug post-mortem
exposed that we have magic numbers nobody can defend with an
external reference. The user response was: *"esses testes têm
princípio de onde? qual a fonte da verdade deles? e de tudo que
estamos construindo?"* This file does not answer the question — it
audits how badly we cannot answer it today.

## Classification taxonomy

| Tag | Meaning |
|---|---|
| `physical_constant` | Verdade matemática ou física universal (1 m = 39.37 in). Não muda. |
| `extracted_from_pdf` | Vem de cota textual ou geometria explícita do PDF da planta. Verificável re-extraindo o PDF. |
| `inherited_from_consume_consensus` | Copiado/portado do exporter de produção. Sua própria fonte é magic_unsourced — o débito é transitivo. |
| `heuristic_relative_to_consensus` | Calculado a partir de dados do próprio consensus (e.g., "30% do menor cômodo"). Escala com o input em vez de impor número fixo. |
| `aesthetic` | Pura escolha visual (RGB de palette). Não há "errado", só "feio". |
| `magic_unsourced` | Escolhido por intuição. Precisa de grounding. |

## Audit — `tools/build_plan_shell_skp.rb`

| Constante | Valor | Classificação | Fonte real | Ação pendente |
|---|---|---|---|---|
| `M_TO_IN` | `39.3700787402` | `physical_constant` | 1 m ≡ 39.3700787402 in exatamente (SI definition) | nenhuma |
| `PT_TO_M` | `0.19 / 5.4` | `extracted_from_pdf` (parcial) + `inherited_from_consume_consensus` | "wall_thickness = 5.4 pt ≡ 0.19 m" foi observado/calibrado no PDF da planta_74. O 0.19 m é convenção brasileira informal (paredes residenciais de 1 tijolo + reboco ≈ 19 cm). O 5.4 pt é cota geométrica do PDF | confirmar 0.19 m com cota textual do PDF ou trena |
| `PT_TO_IN` | `PT_TO_M * M_TO_IN` | (derivado) | composição das duas anteriores | herda débito |
| `WALL_HEIGHT_M` | `2.70` | `inherited_from_consume_consensus` | Convenção informal "pé direito padrão residencial". NBR 15575-1:2013 §11.7 estabelece pé-direito mínimo de 2.50 m; 2.70 é convencional acima do mínimo. Não está citado no código | citar NBR 15575-1 §11.7 + nota sobre por que 2.70 (acima do mínimo) |
| `PARAPET_HEIGHT_M` | `1.10` | `inherited_from_consume_consensus` (suspeita de NBR 9050 ou NBR 14718) | NBR 9050:2020 §6.9.5 exige guarda-corpo a partir de 1.10 m em áreas comuns. NBR 14718 (vidros em janelas) também usa 1.10 m como peitoril padrão. Mas nada disso está documentado no código | confirmar qual NBR aplica + citar |
| `WALL_RGB` | `[78, 78, 78]` | `aesthetic` + `inherited_from_consume_consensus` | Cinza-escuro arbitrário pra contrastar visualmente | nenhuma (é estético) |
| `PARAPET_RGB` | `[130, 135, 140]` | `aesthetic` + `inherited_from_consume_consensus` | Cinza-concreto. Comment no consume_consensus.rb cita "antes era [200,220,230] (papel-de-parede)" — ou seja, foi mudado depois pra distinguir. Sem fonte arquitetônica | nenhuma (é estético) |
| `ROOM_PALETTE` | 11 RGB triples | `aesthetic` | Pastéis aleatórios escolhidos pra distinguir 11 cômodos. Sem fonte | nenhuma (é estético) |
| `SOFT_BARRIER_THICKNESS_IN` | `1.5` | `inherited_from_consume_consensus` | consume_consensus.rb usa 1.5 in (≈ 3.8 cm) como espessura de slab pra peitoril/esquadria. **Sem fonte arquitetônica conhecida.** Real espessura de peitoril em construção: 2-15 cm dependendo material (alvenaria 9-15 cm, vidro com perfil 2-5 cm). 3.8 cm é razoável pra perfil de esquadria de alumínio, irreal pra peitoril de alvenaria | medir peitorils reais OU citar referência de construção residencial |

### Phase 2 visual parity constants (added 2026-05-20)

| Constante | Valor | Classificação | Fonte real | Ação pendente |
|---|---|---|---|---|
| `DOOR_HEIGHT_M` | `2.10` | `inherited_from_consume_consensus` | Convenção pé-direito de porta residencial. NBR 15575-1 não especifica; senso comum / catálogo de marcenaria padrão 2.10 m | citar referência (catálogo Pormade / Lafer / qualquer fabricante residencial) |
| `DOOR_THICK_M` | `0.04` | `inherited_from_consume_consensus` | 4 cm é folha de porta MDF interna típica (3.5-4.5 cm). Sem citação | citar catálogo |
| `DOOR_RGB` | `[140, 95, 55]` | `aesthetic` + `inherited_from_consume_consensus` | Madeira escura, escolha visual | nenhuma |
| `DOOR_SWING_DEG` | `30.0` | `inherited_from_consume_consensus` | "Visual swing angle pra renderização" — não tem base arquitetônica, é só pra reviewer ver que a porta abre. Convenção em planta baixa BR é 90° aberta (símbolo arco completo); 30° foi escolha de quem desenhou o exporter | poderia ser parametrizado por opening (ABNT NBR 6492 §6.1 desenho arquitetônico). Mas pra Phase 1, 30° é OK |
| `WINDOW_SILL_M` | `0.90` | `inherited_from_consume_consensus` (suspeita NBR 14718) | NBR 14718:2014 (vidros pra esquadrias) usa 0.90 m como peitoril padrão pra janela residencial. NBR 9050 também | citar NBR 14718 §X |
| `WINDOW_HEAD_M` | `2.10` | `inherited_from_consume_consensus` | Convenção: verga de janela alinhada com porta. NBR 15575 não impõe valor | mesma fonte que DOOR_HEIGHT_M |
| `GLASS_RGB` | `[180, 220, 240]` | `aesthetic` | Azul-vidro com tinta clara | nenhuma |
| `GLASS_ALPHA` | `0.45` | `aesthetic` | Opacidade 45% pra ler como vidro | nenhuma |
| `LINTEL_RGB` | `[110, 115, 120]` | `aesthetic` | Cinza-concreto pra verga | nenhuma |
| `PASSAGE_RGB` | `[102, 187, 230]` | `aesthetic` | Azul claro pra destacar marker em axon | nenhuma |
| `PASSAGE_MARKER_HEIGHT_IN` | `1.0` | `inherited_from_consume_consensus` | 1 in ≈ 2.5 cm. Marker visual, não estrutural. Sem fonte arquitetônica | nenhuma (é marcador, não geometria real) |
| `CARVING_ORIGINS` | `{svg_arc, svg_segments, human_annotation}` | `inherited_from_consume_consensus` | Set de geometry_origin values que disparam carving 2D. wall_gap é excluído porque a geometria já está nas walls do consensus. Conhecido no docstring do consume_consensus.rb | nenhuma — é convenção interna do pipeline |

## Audit — `tools/build_plan_shell_skp.py`

| Constante | Valor | Classificação | Fonte real | Ação pendente |
|---|---|---|---|---|
| `SNAP_EPS_PTS` | `0.1` | `magic_unsourced` | Escolhi por experimentação — "small enough not to fuse distinct walls, large enough to bridge mismatch". Sem benchmark em multiple plantas | rodar em corpus de >1 planta, ajustar empiricamente, OR derivar de wall_thickness_pts (ex: `wall_thickness_pts * 0.02`) |
| `MIN_SLIVER_AREA_PTS2` | `0.5` | `magic_unsourced` | Escolhi por intuição — "menor que 1 pt² é numerical noise da boolean op" | derivar de wall_thickness² (ex: `wall_thickness_pts ** 2 * 0.02`) ou medir empirically |

## Audit — `tools/build_geometry_invariants_report.py`

| Constante | Valor | Classificação | Fonte real | Ação pendente |
|---|---|---|---|---|
| `WALL_HEIGHT_M` | `2.70` | (espelho da Ruby) | mesmo débito que `tools/build_plan_shell_skp.rb` | mover pra arquivo único de constantes compartilhadas |
| `PARAPET_HEIGHT_M` | `1.10` | (espelho da Ruby) | idem | idem |
| `HEIGHT_TOL_M` | `0.01` | `heuristic_relative_to_consensus` (degenerada) | 1 cm é "maior que erro de ponto flutuante na conversão pt→m, menor que precisão útil pra arquitetura" | nenhuma — é tolerância numérica defensível |
| `FLOOR_HEIGHT_EPS_M` | `0.001` | `physical_constant`-ish | 1 mm é abaixo de qualquer precisão arquitetônica útil; é tolerância numérica pura | nenhuma |
| `SOFT_BARRIER_FOOTPRINT_FRACTION_WARN` | `0.30` | `heuristic_relative_to_consensus` | "soft barrier ocupando > 30% do menor cômodo é provavelmente a bbox-as-slab voltando". Substitui o magic absoluto 1.0 m² da versão anterior | WARN-only até corpus de >1 planta. Promover a FAIL se ficar estável |

## Audit — `tests/test_plan_shell_invariants.py`

| Constante | Valor | Classificação | Fonte | Ação |
|---|---|---|---|---|
| `WALL_HEIGHT_M`, `PARAPET_HEIGHT_M`, `HEIGHT_TOL_M`, `FLOOR_HEIGHT_EPS` | (espelhos) | herdam | mesmas | consolidar |
| `MAX_SOFT_BARRIER_FOOTPRINT_FRACTION` | `0.30` | `heuristic_relative_to_consensus` | mesma do report (consistentes intencionalmente) | manter alinhado com o report |

**Removido nesta iteração:** `MAX_SOFT_BARRIER_FOOTPRINT_M2 = 1.0` (era `magic_unsourced`). Substituído pela fração relativa ao menor cômodo.

## O que isso resolve hoje

- Cataloga honestamente cada número que afeta saída visual.
- Diferencia "verdade matemática" de "convenção" de "magic".
- Aponta as ações pendentes específicas por linha (NBR a citar, PDF a cotar, medição a fazer).
- NÃO bloqueia produção. NÃO impõe NBR como gate.

## O que isso NÃO resolve

- Não substitui consulta real às NBRs.
- Não extrai cotas textuais do PDF (próxima fase, separado).
- Não tem corpus medido em múltiplas plantas.
- Não estabelece a "verdade última". Documenta o débito.

## Política derivada (em vigor)

1. **Nenhum magic number novo sem entrada nesta tabela.** PRs que introduzem constante numérica em código de exporter devem adicionar uma linha aqui ou referenciar uma existente.
2. **Magic absolutos viram heurísticas relativas quando possível.** `MAX_SOFT_BARRIER_FOOTPRINT_M2 = 1.0` virou `* 0.30` do menor cômodo. O patamar absoluto não tinha fonte; o relativo escala com a planta.
3. **Heurísticas começam como WARN.** Promovem a FAIL só após estabilizar em corpus de >1 planta.
4. **`physical_constant` e `aesthetic` são whitelisted.** Não exigem citação externa.
5. **`inherited_from_consume_consensus` carrega o débito.** Quando uma constante for movida do produção pra fundamento real (NBR / medição), atualizar ambos os arquivos juntos.

## Próximas fases (fora deste audit)

- **Fase grounding-1 — PDF cota extraction.** Estender o V7 extractor pra ler strings de cotas do PDF (`"4.20 m"`, `"2.70 PD"`, etc.). Comparar com geometria inferida. Discrepância > X% → fail.
- **Fase grounding-2 — NBR citations.** Pra cada constante candidata, achar NBR + parágrafo. Adicionar comment no código + nesta tabela.
- **Fase grounding-3 — corpus empírico.** Quando >1 planta real estiver disponível, medir distribuição empírica de `wall_thickness`, `parapet_height`, etc. Substituir magic relativo por estimadores estatísticos.

Cada fase é seu próprio PR. Esta tabela é o índice.
