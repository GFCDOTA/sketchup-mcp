# Prompt para GPT — Generalization Failure Analysis

**Para você, GPT**: você está sendo consultado como segunda opinião técnica. Resposta curta NÃO é objetivo — quero crítica direta, apontamento de erros que eu (Claude) possa ter cometido na análise, e priorização lúcida do próximo passo. **Não aceito "parece ok" / "boa análise" / "continue assim"**. Aponte furos. Compare com referências de literatura (Hough + Shapely + CubiCasa5K) quando relevante.

---

## 1. Contexto do projeto

Pipeline Python que extrai geometria de plantas baixas arquitetônicas em PDF → walls, rooms, openings (portas/janelas), peitoris → JSON `consensus_model.json` (schema 1.0.0) → consumer Ruby (`consume_consensus.rb`) gera `.skp` SketchUp 3D.

Repos:
- **Produtor**: https://github.com/GFCDOTA/sketchup-mcp/tree/fix/dedup-colinear-planta74 (branch ativa)
- **Consumer SKP**: https://github.com/GFCDOTA/sketchup-mcp/tree/feat/v6-2-substitute-door

Pipeline tem 13 fases de hardening (F1–F13) já mergeadas, CI verde com 193 pass / 15 pre-existing fail / 9 skip, multiplant validation 2/2 fixtures (`p12_red` + `planta_74`).

## 2. Evidência: validação em 5 plantas externas (2026-04-27, hoje)

Baixadas 5 PDFs reais de sites gov/edu brasileiros (sem auth, todos free): especificação Caixa Minha Casa Minha Vida, projetos FUNASA/AGEHAB/CODHAB/Prefeitura Natal. Rodadas via `run_external_plant.py` (commit `6c6f20f`).

Resultado completo em [EXTERNAL_VALIDATION_REPORT.md](https://github.com/GFCDOTA/sketchup-mcp/blob/fix/dedup-colinear-planta74/EXTERNAL_VALIDATION_REPORT.md).

**Resumo:**

| Plant | walls | rooms | orph | ratio | quality | status |
|---|---:|---:|---:|---:|---|---|
| `p12_red` (GOLDEN sintética) | 33 | 18 | 0 | 1.0 | good | OK |
| `planta_74` (real, F13 baseline) | 133 | 15 | 0 | 1.0 | good | OK |
| `p4_roi` (planta_74 + ROI crop preproc) | 40 | 9 | 2 | 0.96 | fair | OK-ish |
| **funasa_3quartos** | 373 | 155 | 80 | 0.19 | poor | **FAIL** |
| **caixa_especificacoes_min** (é tabela, não planta) | 93 | 58 | 33 | 0.33 | poor | **FAIL** |
| **agehab_projetos** | 460 | 213 | 60 | 0.30 | poor | **FAIL** |
| **codhab_planta_baixa** (23pg A0) | **7093** | **3875** | 496 | 0.20 | poor | **FAIL** |
| **natal_planta_baixa** (7pg A0 UERN) | 3248 | 1063 | 337 | 0.46 | poor | **FAIL** |

5/5 externas FAIL com mesma assinatura: `walls_disconnected` + `many_orphan_components` + `room_count_deviation`.

Visualmente (overlay_audited.png): pipeline lê cotas, eixos de grid, blocos de texto, hachura, mobiliário, **legendas e tabelas** como walls. Output é uma "manta" de rooms sobrepostos sem relação com planta real.

## 3. Hipótese de causa raiz (minha interpretação — desafie)

Pipeline `planta_74` + variantes `p10/p11/p12_red` foram tunadas com:
- **Color preset `red`** ativo (planta_74 e variantes desenham walls em vermelho saturado)
- **A4 single-page**
- Gates `text_baseline_filter` e `pair_merge` calibrados pra esse caso (gate `len(strokes)>200` desativa filtros em planta limpa)

PDFs externos brasileiros desenham walls em **preto fino sobre branco** com cota e texto denso. Pipeline default (sem preprocess) trata cada linha como wall candidate.

**Evidência positiva** (`p4_roi`): mesma `planta_74` + ROI crop preprocess → ratio=0.96, quality=fair, 9 rooms. Generalização é possível **se o preprocess certo for ativado**. Pipeline tem flag `color_mask color: auto` que NÃO está disparando nessas externas.

## 4. Propostas V6.3 que estou considerando (priorize)

1. **Auto-detect color preset** via K-means em fingerprint cromático (não threshold fixo de saturação)
2. **Single-page selector** heurístico (página com mais structure geometry, não a primeira) — codhab tem capa/índice que explode antes da planta real
3. **Cap + retry**: rejeitar runs com walls>500 OR rooms>50, re-tentar com preset diferente automaticamente
4. **Regression gates negativas**: adicionar essas 5 externas como `expected_quality: poor` — teste falha se acidentalmente passarem
5. **Outra coisa que você sugerir** (preferia essa)

## 5. Perguntas pra você, GPT

1. **A trajetória "extract-com-thresholds-fixos → multiplant test reveals over-fit" é típica?** Quais sinais eu deveria ter pego antes do F13 fechar com "tudo verde"? Onde eu fui ingênuo?

2. **Auto-detect color preset via K-means** é a abordagem certa pra paleta arbitrária OU isso é bandage e eu deveria atacar a raiz (descartar color_mask e usar Hough robusto + line detector multi-scale tipo LSD)?

3. **CubiCasa5K** treinou floor plan parser em 5K plantas reais (deep learning). É realista construir uma versão clássica (Hough + Shapely) que generalize OU eu deveria assumir que esse caminho é fundamentalmente limitado e migrar pra modelo treinado (YOLO + post-process geometric)?

4. Olhando os 5 PDFs externos via overlays (você não tem acesso — descreva como você abriria essa investigação), qual o **menor unit test que eu poderia escrever pra capturar o regress** sem custo de full-pipeline run? Sniff por `walls>5*expected` ou similar?

5. **Multi-page A0**: codhab tem 23 páginas, natal tem 7. Pipeline default processa apenas a primeira. Há técnica conhecida pra "page selector" sem rodar o full pipeline em cada página? Histograma de cor + áreas com hachura densa?

6. Os **15 pre-existing fails do pytest** (test_orientation_balance, test_pair_merge, test_pipeline, test_text_filter) — você acha plausível que **alguns deles SEJAM exatamente o sinal que eu precisava** pra prevenir a falha de generalização? Vale revisitar antes de V6.3?

7. **Pivot ou continua**: olhando a evidência, você recomendaria continuar com o pipeline clássico (Hough/Shapely) ou pivotar pra modelo neural (CubiCasa5K-style YOLO+graph) agora? Justifique pelo trade-off custo/qualidade.

## 6. Output esperado

Resposta direta, técnica, ~600–800 palavras. Estruturada por pergunta. Não cite "ótima análise" / "depende do contexto". Aponte erros concretos no meu raciocínio se houver. Cite paper/lib específico se for o caso (LSD, EDLines, CubiCasa5K, scikit-image, OpenCV `LineSegmentDetector`).

## 7. Referências (pra você puxar se quiser)

- Branch produtor: https://github.com/GFCDOTA/sketchup-mcp/tree/fix/dedup-colinear-planta74
- Relatório interno: https://github.com/GFCDOTA/sketchup-mcp/blob/fix/dedup-colinear-planta74/EXTERNAL_VALIDATION_REPORT.md
- Runner genérico: https://github.com/GFCDOTA/sketchup-mcp/blob/fix/dedup-colinear-planta74/run_external_plant.py
- AGENTS.md (regras de engenharia do projeto): https://github.com/GFCDOTA/sketchup-mcp/blob/fix/dedup-colinear-planta74/AGENTS.md
- Pipeline V6.2 (consumer SKP, branch separada): https://github.com/GFCDOTA/sketchup-mcp/tree/feat/v6-2-substitute-door
- Schema consensus_model.json: https://github.com/GFCDOTA/sketchup-mcp/blob/feat/v6-2-substitute-door/skp_export/SKETCHUP_GENERATOR_GUIDE.md

---

_Branch atual: `fix/dedup-colinear-planta74` HEAD `6c6f20f`. Data: 2026-04-27._
