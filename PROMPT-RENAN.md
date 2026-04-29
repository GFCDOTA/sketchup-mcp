# PROMPT-RENAN.md — Cole isto em sessão Claude do Renan para continuar o PR #1

**Uso:** abra Claude Code no diretório do repo `sketchup-mcp` (ou aponte pro clone do Renan) e cole o prompt abaixo. Self-contained, sem precisar anexar CHAT_GPT.md nem `docs/`.

**Origem deste prompt:** Felipe (fmodesto30) rodou uma sessão paralela do Claude Opus 4.7 (1M ctx) que revisou o PR #1 a fundo, validou empiricamente as recomendações dos 9 patches em git worktrees isoladas, implementou o fix estrutural num branch novo, postou a review completa no PR, e fez push do fix pra `origin/fix/dedup-colinear-planta74`. Este arquivo registra o handoff pra sessão Renan continuar.

---

## PROMPT (colar inteiro)

```
Contexto: você é o Claude do Renan autorando o PR #1 (https://github.com/GFCDOTA/sketchup-mcp/pull/1). Felipe (outro humano, outro Claude) revisou o PR em paralelo e aplicou empiricamente parte das recomendações. Quero que você lide com o feedback e siga o trabalho.

**Status atual (2026-04-21)**

1. **Review técnica postada no PR**: https://github.com/GFCDOTA/sketchup-mcp/pull/1#issuecomment-4286508354
   Leia inteira. Tem TL;DR, baseline numérica, 3 sweeps paramétricos, per-patch verdict (9 patches), riscos de contrato, fix estrutural implementado com resultados, seção colapsável sobre um bridge GPT usado na review, e próximos passos.

2. **Branch nova no origin com fix aplicado + 3 waves de hardening**: `origin/fix/dedup-colinear-planta74`
   - Commit base: `a11724a` — fix original (dedup + re-extract adaptativo, 188 LOC)
   - Commit `524657c`, `dc03844` — PROMPT-RENAN.md (inicial + checklist GPT)
   - Commit `e0973ed` — **Frente 3**: DedupReport + audit log + 6 tests adversariais (+310 LOC)
   - Commit `53bc0f7` — **Frente 2**: RoomTopologyReport + snapshot hash + overlay_audited.png (+404 LOC)
   - Commit `2a268fe` — **Frente 1**: representative-anchored dedup + density gates (+227 LOC, refactor)
   - **Total do hardening**: +1130 LOC adicionais sobre o fix original
   - Diff cumulativo em `planta_74.pdf` pós-hardening:
     - walls 42 → 230 (o 42 era artificial por super-clusters, não representava geometria real)
     - rooms 16 → 48 (over-polygonization em bordas, follow-up topology-level)
     - components 3 → 1, largest_ratio 0.93 → 1.0, orphans 4 → 1 (melhor conectividade)
     - dedup max_perp_spread 151 → 19.2 (super-cluster pathology resolvida)
   - `p12_red.pdf` baseline intacto: walls=35, rooms=19, openings=6, topology_score=1.0, snapshot hash `918ad7d1...` estável
   - Testes: 63 pass / 15 pre-existing fail (zero nova regressão)

3. **Per-patch verdicts da review** (resumo):
   - 01 kmeans color: **REJEITAR** — duplica `preprocess/color_mask`
   - 02 density trigger: APROVAR c/ mudanças — threshold não calibrado
   - 03 quality score: APROVAR c/ correções críticas — `AttributeError` em runtime (`wall.p0/p1` não existe, tipo real é `start/end`; `max_component_size_within_page` não existe, real é `max_components_within_page`)
   - 04 ROI fallback: APROVAR c/ mudanças — renomear `fallback_reason` quebra schema 2.1.0 §4; keep canonical + add `fallback_used` aditivo
   - 06 arc detection: **REJEITAR** — `openings/service.py` já tem `_detect_arc_and_hinge`/`_arc_coverage`/`_assign_rooms`; 259 linhas de teste cobrem. Você não leu o file atual quando escreveu o patch (estava stale vs main uncommitted)
   - 07 LSD+morph: ADIAR — scipy ausente em requirements; morph close funde gaps de porta (confirmado empírico)
   - 08 CubiCasa DL: ADIAR — sem offline fallback; `strict=False` silencioso viola §6 do seu próprio CLAUDE.md
   - 09 AFPlan: APROVAR c/ gate — melhor dos 3 extractors mas só atrás de `SKM_EXTRACTOR=afplan`

**O que foi testado**

- Sweep snap tolerance (50/75/100) → rejeitado, mata rooms (16→3-4)
- Sweep hough_max_line_gap (60/80/120) → rejeitado, "fake perfect" com duplicatas sem dedup
- Sweep hough_threshold (6/8/10) → rejeitado isolado, downstream collapse
- Fix combinado → 4/5 targets em planta_74, zero regressão em p12_red
- 2 consultas GPT-4 via bridge local convergiram no approach estrutural

**O que NÃO foi testado**

- Protos `proto/p10_v1_run` e `proto/p11_v1_run` pós-fix (só p12 foi revalidado)
- Outras plantas reais além de planta_74 e p12_red (amostra=1 real)
- Export SKP via `skp_export/main.rb` consumindo `observed_model.json` pós-fix
- Integração `openings/` + `peitoris/` com os 42 walls novos
- Inspeção visual do `debug_walls.svg` pós-fix (os 42 walls fazem sentido semântico?)
- Identidade dos 4 órfãos residuais em `~[282,754]→[334,754]` e `~[357,420]→[401,420]` (inferência "mobiliário/legenda" não validada visualmente)
- Por que os 15 testes pré-existentes falham no `dcb9751`

**O que faça agora**

1. **Checkout e revise** o diff:
   ```
   git fetch origin fix/dedup-colinear-planta74
   git diff main..origin/fix/dedup-colinear-planta74
   ```
   Leia `classify/service.py` linhas ~54-100 (novo estágio gated) e ~163-280 (função `_dedupe_collinear_overlapping`). Leia `extract/service.py` linhas ~21-62 (re-extract adaptativo).

2. **Atualize patches 03 e 06 no próprio PR #1** com as correções indicadas:
   - 03: trocar `wall.p0`/`wall.p1` por `wall.start`/`wall.end`; trocar `max_component_size_within_page` por `max_components_within_page`. Remover qualquer F1-against-GT.
   - 06: fechar como duplicado. `openings/service.py` no main (commit `dcb9751` — branch da PR tá stale desse HEAD) já implementa.
   - Ou: feche 01 e 06 como "superseded by main" + suba versões corrigidas de 03 e 04.

3. **Cubra o fix com testes** antes de mergear (requisito mínimo pra aceitar o branch):
   - Unit test pro `_dedupe_collinear_overlapping`: cluster de 2, cluster de 3+, pares disjuntos (não merge), dupla alvenaria de 20+px (NÃO pode fundir)
   - Regression snapshot test: `planta_74.pdf` → walls=42, components=3, largest_ratio≥0.9, rooms=16
   - Validar protos p10/p11 também não regridem

4. **Investigue os 4 órfãos residuais** no `runs/v5_recheck/observed_model.json` do worktree que o Felipe deixou em `E:/Claude/sketchup-mcp-exp-dedup/`. Se forem mobiliário/legenda como inferido, proponha filtro semântico downstream (drop components ≤2 nós com bbox pequeno) em PR SEPARADA — não inclua nesta. A ideia do fix é só dedup + re-extract, mantém escopo enxuto.

5. **Atualize `docs/SOLUTION-FINAL.md`** e o TL;DR do PR pra refletir:
   - O approach ganhador foi o combo (2)+(4) do seu patches/README (dedup pós-Hough), não os patches 07/08/09.
   - Patch 09 AFPlan foi considerado inferior pelo GPT consultado — não troca classe de bug, introduz blobs.
   - Opening-aware topology vira Fase 2.

6. **ROADMAP**: revise estimativa pra 6-8 semanas em vez de 3-4. Fatos: arc detection L3 já existe no main (patch 06 era desnecessário); U-Net oracle (patch 08) precisa de setup CI de modelo + vendoring + pinned SHA de weight; o fix estrutural agora resolve 4/5 targets sem DL.

**Leia antes de retomar o trabalho** (artefatos novos que você precisa auditar)

Pra cada run que você fizer, 4 artefatos novos vão aparecer em `runs/<name>/`:
1. `dedup_report.json` — lista de clusters consolidados pelo dedup, com perp_spread_px e min_parallel_overlap_ratio por cluster. Audite clusters suspeitos (spread próximo de 20, overlap próximo de 0.35). Nenhum cluster deve ter perp_spread > 20 (bound garantido pelo novo algoritmo).
2. `room_topology_check.json` — Shapely is_valid + área threshold + nested_pairs por room. Todos devem estar "pass" em runs limpos.
3. `metadata.topology_snapshot_sha256` no `observed_model.json` — SHA256 canonical de (walls, junctions). Se você mudar algo no fluxo e o hash do p12 mudar, você regrediu o baseline.
4. `overlay_audited.png` — PNG PIL com walls em preto, órfãos em magenta, rooms coloridos. **Obrigatório abrir inline e inspecionar semanticamente** — GPT flagou explicitamente que validação só numérica é insuficiente.

Se for rodar o pipeline e achar que resolveu algo, PRIMEIRO abre o overlay_audited.png. Segundo: `grep max_spread dedup_report.json` e confira se está sob 20.

**Invariantes a respeitar** (seu próprio CLAUDE.md §6 lista elas; re-valide)

- Não usar `strict=False` em `load_state_dict` sem reportar keys ignoradas explicitamente.
- Nada de F1-against-GT no extrator (GT é contrato do consumer, não do pipeline).
- `RoiResult.fallback_reason` é campo estável v2.1.0 — não renomeie, adicione aditivos.
- `max_components_within_page` (plural, count) é o campo real no `ConnectivityReport`.

**Ambiente local do Felipe (só referência)**

- Repo: `E:/Claude/sketchup-mcp/` (main com uncommitted: `preprocess/`, `peitoris/`, `skp_export/` novos + modificações em `classify/`, `model/`, `openings/`)
- Worktree com fix: `E:/Claude/sketchup-mcp-exp-dedup/` (já branch local, pushed pra origin)
- Python: `E:/Python312/python.exe`
- Pipeline: `python main.py runs/<nome> -- planta_74.pdf`
- Baseline sanity: `python run_p12.py`
- Bridge GPT usado na review (ortogonal, não commitar): `E:/chatgpt-bridge/` (FastAPI localhost:8765, UIAutomation, sessão Plus)

**Não faça**

- Não committe patches 01 ou 06 (rejeitados definitivos).
- Não aplique patches 07/08 sem spike isolado.
- Não pushe force. Não faça rebase destrutivo do PR.
- Não mergeie o fix sem cobertura de teste.

**Entregável esperado desta sua próxima sessão**

- PR #1 atualizado com: patches 01 e 06 removidos/fechados, 03 e 04 corrigidos, TL;DR refletindo o fix real, ROADMAP realista.
- PR #2 novo (ou push forçado em `fix/dedup-colinear-planta74`): fix + testes unit + snapshot regression. Referência cruzada ao PR #1.
- Resposta consolidada no issue comment do Felipe explicando o que foi aceito vs contestado.

**Checklist obrigatório antes de fechar o entregável** (síntese de 2 consultas GPT-4 pedindo evidência, não interpretação — GPT flagou 3 furos no meu fix e 4 vieses que você pode ter):

1. **Prova visual antes/depois**: PNG/SVG anotado mostrando os 42 walls finais + os 4 órfãos destacados + overlay sobre o raster da planta_74. Sem imagem renderizada, o entregável é rejeitado — "parece mobiliário" não basta.
2. **Diff estrutural do grafo, não só métrica**: lista de wall IDs removidas pelo dedup, clusters formados (tamanho, IDs dos membros, razão de merge), 5-10 exemplos concretos no PR. Se você só mostrar "walls 104→42 ratio↑", é compressão de informação perigosa.
3. **Regressão semântica em rooms**: `rooms=16` numericamente certo pode ser semanticamente errado — dois cômodos fundidos em um ainda dá 16 se outro par ficou separado. Precisa validar que cada room no pós-fix corresponde a uma room real na planta.
4. **Auditoria do dedup**: mostre casos onde o dedup NÃO mergeou (por quê? perp > 10px? overlap < 35%?) E casos onde mergeou com justificativa geométrica. Evita overfit no planta_74.
5. **Run sem gate `>200`**: se o dedup só funcionar gated, o fix depende de heurística frágil. Rode o pipeline com gate removido e mostre se quebra p12 ou outros limpos — se quebrar, o gate é load-bearing e isso precisa ir na docstring.
6. **Não-regressão em openings**: dedup pode ter fechado porta silenciosamente. Compare `openings.json` antes/depois em planta_74 + p10/p11 — número de portas, posição, hinge_side. Se mudou, explique.
7. **p10_v1_run + p11_v1_run**: não rodei pós-fix. Você precisa rodar e mostrar a tabela de regressão (walls, rooms, openings, ratio) comparando com baselines deles em `runs/proto/p*`. Qualquer divergência é regressão a justificar.
8. **Não reverter o fix F1 pra voltar aos 42 walls sem evidência**: os 42 eram artificialmente baixos (super-clusters via transitividade). Se você quiser reduzir o wall count de 230 pra ~70-100 (mais realista), ataque DOWNSTREAM (topology short-polygon filter, melhor snap) em vez de voltar o union-find.

**Vieses tipados a evitar** (GPT antecipou):
- Não tentar salvar patches 07 (LSD+morph) ou 08 (CubiCasa DL). Eles foram ADIADOS, não aceitos — não reintroduza silenciosamente.
- Não assumir que os 4 órfãos são mobiliário. Procure ativamente contra-exemplo (E SE forem paredes reais perdidas?).
- Não otimizar métrica sobre geometria. Se melhorar ratio pra 0.95 fundindo 2 rooms legítimos, é regressão, não progresso.
- Não otimizar só planta_74. p10/p11 são gate.

Boa sessão.
```

---

## Metadata

- **Autor da sessão revisora:** Claude Opus 4.7 (1M ctx), autônomo, operado por Felipe (fmodesto30)
- **Data:** 2026-04-21
- **Review postada:** https://github.com/GFCDOTA/sketchup-mcp/pull/1#issuecomment-4286508354 (20.352 chars)
- **Commit do fix:** `a11724a` em `origin/fix/dedup-colinear-planta74`
- **Metodologia:** 6 Explore agents paralelos no codebase + 3 experimentos paramétricos em worktrees isoladas + 1 experimento estrutural + 2 rodadas de consulta GPT-4 via chatgpt-bridge local (UIAutomation, sessão Plus sem API key)
