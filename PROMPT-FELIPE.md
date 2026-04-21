# PROMPT-FELIPE.md — Cole isto em sessão Claude nova para continuar

**Uso:** abra Claude Code no diretório do repo `sketchup-mcp` e cole o prompt abaixo.

---

## PROMPT (colar inteiro)

```
Você está continuando um trabalho iniciado por Claude em sessão autônoma (commit 570f934 na branch claude/fix-planta-despedacada). O repositório é sketchup-mcp e o problema central é "planta arquitetônica saindo despedaçada" ao extrair de PDF.

CONTEXTO CRÍTICO — leia nesta ordem antes de qualquer ação:

1. AGENTS.md (§2 invariantes invioláveis — nunca violar)
2. CLAUDE.md (raiz do repo — instruções específicas pra Claude)
3. docs/CAUSA-RAIZ.md (por que a planta despedaça, com arquivo:linha)
4. docs/SOLUTION-FINAL.md (status real após code review com 3 agents)
5. docs/ROADMAP.md (6 fases de execução)
6. patches/README.md (ordem de aplicação)

Depois de ler, siga este protocolo:

FASE 0 — BASELINE (30 min)
- Garantir Python 3.10+ instalado (NÃO 3.12, que não funciona na máquina do Renan)
- Criar venv e instalar requirements.txt
- Rodar: python main.py extract planta_74.pdf --out runs/baseline_before
- Capturar métricas: walls, rooms, orphan_component_count, geometry_score, topology_score, warnings
- Abrir runs/baseline_before/debug_walls.svg e fazer screenshot (referência visual)
- Reportar baseline em 1 tabela antes de tocar em qualquer código

FASE 1 — HIGIENE (aplicar patches 01-04, ~4h)
Estes patches corrigem 4 violações de invariantes SEM mudar extração.
Risco: baixo. Backward compat preservada via alias `geometry_score`.

Aplicar na ordem:
- patches/04-roi-fallback-explicit.py → roi/service.py (adiciona fallback_used + reason)
- patches/03-quality-score.py → model/pipeline.py (renomeia _geometry_score, adiciona _quality_score real)
- patches/02-density-trigger.py → classify/service.py (remove len>200 hardcoded)
- patches/01-kmeans-color-aware.py → criar preprocess/color_aware.py (NÃO integrar ainda, só criar módulo)

Após cada patch:
- pytest -v (deve passar 100%)
- git commit com prefixo fix: ou feat: conforme patch
- Re-rodar planta_74 e confirmar que nenhuma métrica piorou drasticamente

FASE 2 — AFPLAN TOPOLOGIA (patch 09, ~1 dia)
- Copiar patches/09-afplan-convex-hull.py → extract/afplan.py
- Em model/pipeline.py, adicionar flag de feature (env var USE_AFPLAN=1)
- Quando USE_AFPLAN=1: usar extract_from_raster_afplan em vez de extract_from_raster
- Rodar: USE_AFPLAN=1 python main.py extract planta_74.pdf --out runs/afplan
- Comparar com baseline. Se orphan_component_count caiu de 7 para ≤3 E perimeter_closure subiu para ≥0.88, parar aqui e commitar. Se não, seguir Fase 3.

FASE 3 — LSD REAL (patch 07 FIXED, ~1 dia, se necessário)
- Verificar: python -c "import cv2; print(cv2.createLineSegmentDetector)" deve funcionar em opencv-python≥4.5.4
- Instalar scipy se faltar
- Copiar patches/07-reconnect-fragments-FIXED.py → extract/reconnect.py
- Em model/pipeline.py, adicionar flag USE_LSD=1 que usa extract_from_raster_v2
- Idealmente: ensemble AFPlan + LSD (concatenar candidates, merge por overlap espacial)

FASE 4 — CUBICASA5K DL ORACLE (patch 08 FIXED, ~2-3 dias, solução definitiva)
Apenas se Fases 2 e 3 insuficientes.

Setup (único):
- cd .. && git clone https://github.com/CubiCasa/CubiCasa5k
- cd CubiCasa5k && pip install -e .
- cd ../sketchup-mcp
- pip install torch torchvision gdown scikit-image
- Copiar patches/08-unet-oracle-FIXED.py → preprocess/cubicasa_oracle.py
- python -c "from preprocess.cubicasa_oracle import download_cubicasa_weights; download_cubicasa_weights()"
  (Baixa ~100MB do Google Drive ID 1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK via gdown)
- Em model/pipeline.py, adicionar flag USE_DL=1 que chama extract_from_raster_dl

Validar:
- USE_DL=1 python main.py extract planta_74.pdf --out runs/dl
- Inspecionar debug_walls.svg: walls agora seguem contornos reais da planta, sem ilhas
- Comparar tempo inferência: esperado ~5-15s CPU por página

CRITÉRIO DE SUCESSO
Planta resolvida quando TODOS verdadeiros:
- perimeter_closure ≥ 0.90
- orphan_components ≤ 2
- len(rooms) = número de salas visíveis no PDF (validação humana)
- quality_score ≥ 0.75 (novo score do patch 03)
- debug_walls.svg visualmente: perímetro fechado, sem ilhas soltas

Se não atingir, NÃO fingir que atingiu. Reportar qual métrica falhou e por quê.

INVARIANTES INVIOLÁVEIS (de AGENTS.md §2) — JAMAIS violar:
1. Não inventar rooms/walls
2. Não mascarar falhas (rooms=0 é informação)
3. Não usar bounding box como sala
4. Não acoplar pipeline a PDF específico (nada hardcoded planta_74)
5. Sempre emitir debug_walls.svg, debug_junctions.svg, connectivity_report.json
6. Ground truth nunca entra no output do extrator

Se uma mudança "resolveria o caso" violando invariante, PARE e reporte o tradeoff ao Felipe antes de commitar.

WORKFLOW DE COMMITS
- Branch: claude/fix-planta-despedacada (já existe) ou nova branch
- Um commit = uma ideia (fix: X, feat: Y)
- Sempre pytest antes de commit
- Sempre comparar baseline antes/depois em planta_74
- NUNCA push --force em main
- NUNCA --no-verify em hooks

REPORTAR AO FELIPE
Após cada fase, gerar relatório em markdown com:
- Métricas antes/depois (tabela)
- Screenshot de debug_walls.svg antes/depois
- Decisões tomadas com justificativa
- Próximo passo recomendado

O objetivo final é: Felipe roda `python main.py extract <qualquer-planta.pdf>` e recebe observed_model.json honesto que o downstream Ruby/SketchUp consome pra gerar .skp fiel ao PDF.

Comece lendo AGENTS.md e CLAUDE.md agora.
```

---

## Notas pro Felipe

**O que o Claude anterior entregou:**
- 6 docs técnicos em `docs/`
- 9 patches prontos em `patches/` (NÃO aplicados — você escolhe quando/como)
- CLAUDE.md na raiz com guidelines persistentes

**O que você precisa fazer:**
1. Rodar baseline em `planta_74.pdf` (capturar métricas atuais)
2. Colar o prompt acima numa sessão Claude Code
3. Seguir o protocolo

**Ambiente:**
- Python 3.10+ (não 3.12 — conhecido que não funciona na máquina do Renan)
- OpenCV 4.5.4+ se for usar LSD real (patch 07)
- Torch + CubiCasa5K se for usar DL oracle (patch 08)

**Dúvidas sobre decisões arquiteturais:**
- Consulte `docs/SOLUTION-FINAL.md` seção "O que PODE precisar ajuste"
- Consulte `docs/CAUSA-RAIZ.md` pra entender por que o bug existe

**Se o Claude que você usar violar invariante:**
Pare a sessão. Leia `AGENTS.md §2`. Seja explícito no próximo prompt.
