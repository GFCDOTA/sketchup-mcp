# FP-043 — Decisões em aberto

Pendências que **não se resolvem pelas fontes** e por isso estão registradas em vez de decididas por mim. Cada uma diz o
que está provado, o que cada opção muda, a recomendação e o que continua andando enquanto isso. Quando o Felipe decide, a
linha vira uma nota de decisão com data e o item sai daqui.

| ID | Assunto | Decide | Bloqueia |
|---|---|---|---|
| D-001 | Referência canônica do `quadrado` × builder aprovado em 2026-06-04 | Felipe | só a re-baseline da referência; nenhum fluxo |
| D-002 | `tools/Dockerfile.dashboard` + `docker-compose.yml` do dashboard morto — **RESOLVIDA** (2026-10-22: arquivados em `docs/archive/2026-10-22/root/`, autorização do Felipe) | Felipe | nada |
| D-003 | `tools/furnish_plan.py` / `.rb` (3D Warehouse): vigente ou histórico | Felipe | só o destino desses 2 arquivos em P4 |
| D-004 | Dono da CLI `tools/trace_view.py` | Felipe | só o destino dele em P4 |
| D-005 | `scripts/set_clipboard_image.ps1` ainda útil — **RESOLVIDA** (2026-10-22: movido para `tools/oracle/`, junto do fluxo legado de revisão GPT; `scripts/` saiu da raiz) | Felipe | nada |
| D-011 | 4 fachadas de `tools/` lidas pelo Inspector do harness (fora das 8 públicas) — **RESOLVIDA** (harness-app#17 + FP-045/F2, 2026-10-21) | técnica | nada |
| D-012 | `tools/sofa_class_matrix.py` escondia uma dependência quarto → living — **RESOLVIDA** (`_grid_sheet` → `tools/rooms/shared/contact_sheet.py`, 2026-10-20) | técnica | nada |

**Linha final (P8, 2026-10-19):** D-001 a D-005 = BLOCKED_DECISION (Felipe; material da D-001 em `artifacts/review/fp043/p3a04_quadrado_d001/`); D-006 = RESOLVED; D-007 = OPEN_TECNICA (planta_74 já respeita o contrato por cômodo; sintéticas seguem `xfail(strict)`).

**Linha final (FP-044/F7, 2026-10-20):** D-008 (`.impeccable/`) e D-009 (`ops/estudio-front/`) = BLOCKED_DECISION (Felipe; spec FP-044 §10); D-010 = manter as 8 públicas agora; D-011 = OPEN_TECNICA; D-012 = RESOLVIDA em 2026-10-20 (seções abaixo). Relatório: [FP-044_final_validation](../reports/FP-044_final_validation.md).

**Decisão técnica já resolvida:** D-006 — o `repo_health_gate` foi corrigido e incluído no CI; evidências e contraprovas na seção histórica abaixo.

## D-001 — Peitoril (e mais) do `quadrado`: referência de 2026-05-24 × builder aprovado em 2026-06-04

**O que está provado (L2, SketchUp 26.0.429, `artifacts/review/l2_fp042_20261019/`)**
O shell do `quadrado` gerado hoje preserva massa de parede abaixo e acima da janela (raios: sólido em z = 0,5 / 1,2 m e em
2,4 / 2,65 m; vão aberto em 1,8 m), sem faces degeneradas. O contrato **semântico** (ADR-007 / LL-016: janela é abertura 3D
que preserva peitoril e verga, nunca carve em altura cheia) **vale**. O que diverge são **números** da referência:

| | Referência `docs/specs/_assets/quadrado_canonical_geometry_report.json` (2026-05-24) | Build atual (medido) |
|---|---|---|
| Janela (peitoril → verga) | 0,90 → 2,10 m, um painel de vidro (1 face) | 1,50 → 2,10 m, esquadria basculante (vidro com 4 sub-grupos) + grupo `WindowSash` |
| Grupos de nível raiz | 3 | 4 |
| Piso do cômodo | 14,516 m² (3,6135 → 7,4235 m) | 15,697 m² (3,5375 → 7,4995 m): o piso passa por baixo da parede |
| `PlanShell_Group` | idêntico | idêntico |

**De onde veio a divergência (fontes)**
- `b45712a` (2026-06-04): "janelas viram esquadria" — Felipe aprovou `VISUAL_REVIEW=IMPROVED` **sobre a planta_74**; janelas
  horizontais ≤ 1,20 m viram basculante (peitoril 1,50 m), as de quarto ganham 1,10 m. O comentário do builder diz que a
  regra é para "as pequenas de banheiro/serviço".
- O piso "tucado" sob a parede é de 2026-06-04 também (comentário em `build_floor`, "Felipe 2026-06-04").
- A janela do `quadrado` tem 30 pt ≈ 1,06 m: **cai na regra do basculante por efeito colateral**, não por decisão sobre o
  `quadrado`. Não existe registro de aprovação humana para o `quadrado` depois disso, e a referência nunca foi re-baselinada.

**Por que não mexi no esperado:** a referência é protegida (`docs/specs/_assets/`), o teste que a pina é canônico, e a
fonte não diz se o `quadrado` deve seguir a regra nova. Mudar o esperado para o teste passar é o que a FP-043 §8 proíbe.

**Invisível hoje:** `tests/test_window_aperture_geometry.py` só roda esses checks quando existe `runs/quadrado_v3_aperture/`
(cinco testes **pulam** no CI); com o build real presente, `test_quadrado_window_glass_group_exists` falha
("altura 0,600 m; esperado 1,200 m"). A divergência só aparece rodando no SketchUp.

**Opções**
- **A (recomendada):** re-baselinar a referência (relatório de geometria + constantes do teste) a partir de um build real,
  declarando que o `quadrado` exercita a regra de janela estreita aprovada; exige o seu OK por ser referência protegida, e
  um `VISUAL_REVIEW` do render novo.
- **B:** alargar a janela do `quadrado` (≥ 1,25 m) para que volte ao painel simples. Muda `fixtures/quadrado/` (protegida)
  e perde a cobertura de janela estreita.
- **C:** o builder não aplicar a regra do basculante em micro-fixtures. Cria caso especial sem fonte; não recomendado.

**Continua andando:** shells da `planta_74`, validação por cômodo e todo o resto (a `planta_74` reconstruída é idêntica ao
canônico aprovado; só a referência do `quadrado` está defasada).

## D-002 a D-005 — vindas do mapa P0

Ver [mapa P0](FP-043_P0_map.md), seção "Perguntas abertas". Resumo: o dashboard do estúdio foi removido em 2026-07-24 e
`docker-compose.yml` ainda o sobe (`tools/studio_dashboard.py` não existe); `furnish_plan` insere componentes do 3D
Warehouse sem consumidor; `trace_view` lê traces do AI Pipeline Inspector e não tem dono óbvio; `set_clipboard_image.ps1`
colava imagem no ChatGPT, e a memória do projeto registra que Ctrl+V/upload não funcionam (o GPT vê via URL raw).

## D-006 — `repo_health_gate` não rodava no CI e falhava — **RESOLVIDA (P3a-05)**

As 4 ocorrências eram defeitos de autoridade estabelecida, corrigidos sem mexer em evidência: (1) as 3 pastas de imagens
de revisão sem report (`artifacts/review/furniture/kitchen`, `.../planta_74/curation`, `.../planta_74/shell_proof`)
ganharam um `README.md` só de proveniência (primeiro commit, arquivos; sem veredito visual; PNGs intactos, READMEs
registrados em `fp042_references.v1.json`); (2) `SCALE_DEF_FORA_DO_CORE` em `tools/interior_studio/architect_program.py`
agora lê `PLANT_PT_TO_M["planta_74"]` de `core.scale` (mesmo valor, 0,0259, fonte única). O gate passou a ser coletado
pelo pytest/CI via `tests/test_repo_health_gate.py`, com contraprovas (escala fora do core e artefato sem report
reprovam). Nenhuma regra foi afrouxada.

## D-007 — vão de mobiliar = laje (entra sob a parede) — causa do guarda-roupa "4,5 cm na parede" (P3a-02)

**Achado.** Na fixture sintética `bedroom_medium_14m2` o guarda-roupa fica ~4,5 cm dentro da parede oeste. A hipótese
inicial (polígono do cômodo no eixo da parede em vez da face interna) foi **refutada**: o planner nem lê o polígono —
`tools/spatial_model.build_spatial_model` usa `compute_room_floors`, que devolve a **laje**, a qual entra
`FLOOR_UNDER_FRAC = 0,4 × espessura` sob a parede (esconde a junta). Eixo × face interna dá layout idêntico
(`tests/test_synthetic_polygon_convention.py`). A fixture `*_inner_face` foi criada e documenta a convenção real da
`planta_74` (vértices a meia espessura do eixo), mas **não** resolve o achado.

**Tentativa e porque foi revertida.** Planejar no vão livre (laje − massa das paredes) para todos os cômodos reprova a
`SUITE 02` (`NO_VALID_LAYOUT`), tira 15 peças da `SUITE 01` e quebra o anchor da pia da cozinha (`require_kitchen_anchor`).
Mudança global não é segura.

**Direção técnica (P3a-03, sem decisão do Felipe):** adotar o vão livre por ambiente (`free_cell`), ambiente a ambiente,
com regressão por cômodo, mantendo cozinha/SUITE 02/SERVICE como controles. Qualquer mudança de aparência vira
`VISUAL_REVIEW`. Até lá o contrato "nenhum móvel dentro da parede" fica como `xfail(strict)` — vira falha ruidosa quando
for corrigido.

**Atualização de diagnóstico (FP-044, 2026-10-20) — o mecanismo real é outro e a correção muda um cômodo de controle.**
Na sintética `bedroom_medium_14m2_inner_face` o guarda-roupa entra ~4,5 cm na parede **esquerda** (perpendicular à parede onde
ele está encostado): o item do planner começa em x = 1,42 pt, dentro da massa da parede (face interna em 2,70 pt). Duas coisas somam:
(1) o intervalo ao longo da parede (`_place_against`, `designer.py`) parte do **eixo** da parede perpendicular + 0,05 m, ignorando a
meia espessura; (2) o filtro contra a massa das paredes (`b.intersection(wfoot).area > 0.06 m²`) tolera ~600 cm² de sobreposição, o que
mascara o canto. Medido: reduzir a tolerância para 0,002 m² elimina o achado na sintética, **mas altera as caixas da SUITE 02**
(`fp044_baseline compare` → `CAIXAS_MUDARAM: SUITE 02`), porque o guarda-roupa dela também usa essa folga no canto. Mudar a SUITE 02 é
mudança de aparência de cômodo de controle → `VISUAL_REVIEW` do Felipe; por isso **não** foi aplicado e o `xfail(strict)` continua.
Hipótese descartada: o piso de 0,45 m de profundidade do adaptador (`furnishing.py`) não é a causa (a profundidade já é ≥ 0,45 m).
Proposta quando o Felipe aprovar: apertar a tolerância **e** partir o intervalo da face interna da parede perpendicular, com a
SUITE 02 revista lado a lado antes/depois.

## D-011 — Inspector do harness lê 4 fachadas de `tools/` por caminho (FP-044/F6) — **RESOLVIDA (FP-045/F2, 2026-10-21)**

**Resolução:** `GFCDOTA/harness-app#17` repontou o catálogo Java para os donos (e `correction_loop` para `tools/orchestration/correction/`, cuja fachada não define `run_loop`); as 4 fachadas foram removidas (`tools/*.py`: 14 → 10). O texto abaixo é o registro histórico.

**Achado (varredura da Hard Rule #1 antes do 1º lote da F6).** O `fp044_tools_facades.v1.json` só contava imports
Python; o `apps/harness-app` (outro repositório) também tem um catálogo Java (`ImplementationCatalog`/`ComponentCatalog`)
cujo `SourceVerifier` lê, em tempo de execução, `../sketchup-mcp/tools/reference_db.py`, `tools/rag_embed_backend.py`,
`tools/ollama_bridge.py` e `tools/run_deterministic_gates.py` e procura `def <símbolo>` no texto. Desde o P4 esses
arquivos são fachadas (o símbolo mora no dono), então o Inspector **já** marca esses símbolos como não encontrados;
remover as fachadas mudaria o sintoma para "arquivo ausente".

**Decisão técnica tomada na F6:** as 4 ficam (`BLOCKED_EXTERNAL_CONSUMER` no JSON de fachadas, registradas em
`tools/PUBLIC_API.md`); nenhuma outra fachada é afetada. **Próximo passo (fora deste repositório):** PR no harness
repontando o catálogo para os donos (`tools/knowledge/reference_db.py`, `tools/knowledge/rag_embed_backend.py`,
`tools/oracle/ollama_bridge.py`, `tools/validation/run_deterministic_gates.py`); depois disso uma fatia futura remove
as 4. Até lá, o critério §11 da FP-044 ("`tools/*.py` = 8 públicas + 2 bloqueadas") não fecha: estado `PARTIAL`
(consumidor externo).

## D-012 — fachada `tools/sofa_class_matrix.py` escondia uma dependência quarto → living (FP-044/F6) — **RESOLVIDA**

**Achado (lote `rooms/living`).** `tools/rooms/bedroom/bed_class.py::build_matrix` importa `_grid_sheet` (helper puro de
folha-contato em PIL) de `tools.rooms.living.capabilities.sofa_class_matrix`, **pela fachada** `tools.sofa_class_matrix`.
O gate de fronteira (`tools.rooms.ownership_audit`) só resolve as fachadas listadas em `LEGACY_ROOM_MODULES`; esta não
está lá, então a dependência quarto → living ficava invisível. Reescrever o import para o dono faz o gate reprovar
(`CROSS_ROOM_DEPENDENCY`) — o que é correto.

**Decisão técnica tomada na F6:** a fachada fica (`BLOCKED_HIDDEN_CROSS_ROOM_DEPENDENCY` no JSON de fachadas; o
`bed_class` continua importando por ela, exatamente como antes). Mover `_grid_sheet` para um lugar compartilhado
(`tools/rooms/shared/` ou `tools/rendering/`) é uma alteração de estrutura que não foi pedida — fica como proposta para
uma fatia própria; depois disso a fachada sai e o gate passa sem exceção.

**Resolução (2026-10-20).** `_grid_sheet` (helper puro de folha-contato em PIL) foi para `tools/rooms/shared/contact_sheet.py` como `grid_sheet`; `bed_class` importa de `shared` (sem dependência quarto → sala) e o módulo do sofá reexporta o nome antigo para os consumidores do living. A fachada `tools/sofa_class_matrix.py` foi removida; o gate de fronteira passa sem exceção.
