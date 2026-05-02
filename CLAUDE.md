# CLAUDE.md — instruções pra agentes Claude no sketchup-mcp

**Propósito:** pacote de contexto pra Claude Code/API ao continuar trabalho neste projeto. Lido automaticamente em toda sessão.

---

## 0. Git Protocol (REGRA INVIOLÁVEL — antes de tudo)

**Toda sessão neste repo:**

1. **Início — antes de qualquer Read/Glob/Grep do código:**
   ```bash
   cd E:/Claude/sketchup-mcp
   git status -s
   git fetch --all
   git pull --ff-only
   ```
   Se working tree dirty: committar trabalho não-versionado em commits temáticos (`feat:`/`fix:`/`refactor:`/`docs:`/`chore:`/`test:`) ANTES de seguir.

2. **Fim — antes de fechar a resposta final:**
   - Commits do trabalho da sessão (um commit = uma ideia)
   - `git push` na branch corrente

**Não esquecer.** Pull desatualizado = merge conflicts ou trabalho duplicado. Push esquecido = trabalho perdido entre sessões. Reforçado pelo user em 2026-05-02.

Regras anti-acidente:
- NUNCA `git push --force` em main/master sem autorização explícita
- NUNCA `--no-verify`/`--no-gpg-sign` sem autorização — se hook falhar, fix root cause
- Branch + PR pra main; commits diretos só em feature branches

---

## 1. Missão do projeto (resumo)

PDF de planta arquitetônica → `observed_model.json` (Python) → `.skp` SketchUp (Ruby).

Etapa Python: `PDF → ingest → extract → classify → openings → topology → model → debug`.

**Este CLAUDE.md foca apenas na etapa Python.** Ruby/SketchUp tem outro escopo.

---

## 2. Invariantes INVIOLÁVEIS (AGENTS.md §2)

Claude NUNCA pode violar:

1. **Não inventar rooms / walls.** Se `polygonize` retorna `[]`, output é `rooms=[]`. Isso é observação válida.
2. **Não mascarar falhas.** `rooms=0` é informação. Não substituir por bbox.
3. **Não usar bounding box como substituto de room.**
4. **Não acoplar pipeline a PDF específico.** Nada hardcoded para `planta_74.pdf`, `proto_p10.pdf`, etc.
5. **Debug artifacts obrigatórios:** `debug_walls.svg`, `debug_junctions.svg`, `connectivity_report.json`. Sem eles o run é inválido.
6. **Ground truth NUNCA entra no output do extrator.** Scores são observacionais.

Se uma mudança "resolveria o caso" violando invariante, **PARE** e reporte o tradeoff.

---

## 3. Contexto do trabalho feito por Claude (sessão 2026-04-21)

### Auditoria completa em docs/
- `docs/ANALYSIS.md` — análise crítica do código (4 violações de invariantes)
- `docs/SOLUTION.md` — arquitetura Hybrid CV+DL em 10 stages
- `docs/SOLUTION-FINAL.md` — status real após code review com 3 agents
- `docs/CAUSA-RAIZ.md` — por que a planta despedaça
- `docs/ROADMAP.md` — 6 fases de execução, 3-4 semanas

### Patches propostos em patches/ (NÃO APLICADOS)
- 01-04: higiene (corrigem violações de invariantes sem mudar extração)
- 06: openings L3 (arc + hinge_side + swing_deg)
- 07 FIXED: LSD real + KDTree (OpenCV puro)
- 08 FIXED: CubiCasa5K DL (arch `hg_furukawa_original`)
- 09: AFPlan multi-scale + CCA (topologia força reconnect)

Patches foram revisados mas **não executados** (ambiente Python 3.12 não disponível). Valide antes de merge.

---

## 4. Causa raiz da planta despedaçada

Conhecida após leitura completa do código:

```
extract/service.py:43-50
  HoughLinesP(maxLineGap=40)  # fragmenta walls em 2-5 pedaços

topology/service.py:98
  snap_tolerance = 3 × thickness ≈ 24px  # não reconecta gaps 24-80px

Resultado: walls a 24-80px de distância = ilhas flutuantes permanentes
```

Ver `docs/CAUSA-RAIZ.md` para análise completa.

---

## 5. Ordem recomendada de ataque

Se vai aplicar patches, siga esta ordem (baixo → alto risco):

### Fase 1 — Higiene (1 dia, baixo risco)
- Aplicar 01-04 (corrige invariantes, não muda extração)
- Rodar `pytest`, confirmar baseline
- Commit por patch

### Fase 2 — Topologia (1 dia)
- Aplicar 09 (AFPlan multi-scale + CCA)
- Testar em `planta_74.pdf`
- Métricas: `orphan_components` deve cair, `perimeter_closure` deve subir

### Fase 3 — LSD (1 dia, se Fase 2 insuficiente)
- Aplicar 07 FIXED ensemble com 09
- Instalar `opencv-python>=4.5.4` + `scipy`

### Fase 4 — DL oracle (2-3 dias, solução definitiva)
- Setup CubiCasa5K (clone + weights Google Drive)
- Aplicar 08 FIXED
- DL primário, Hough fallback

### Fase 5 — Features
- Aplicar 06 (openings L3)

### Fase 6 — Ruby bridge
- TCP socket pattern (mhyrr/sketchup-mcp)
- NÃO reescrever em Python — manter contrato `observed_model.json` estável

---

## 6. Regras pra Claude ao trabalhar aqui

### Sempre
- **Antes de mudar código:** ler o arquivo inteiro, não apenas o trecho a editar
- **Antes de declarar "resolvido":** medir baseline antes/depois empiricamente (rodar em planta_74 + p12)
- **Ao adicionar filtro:** documentar reasoning no código (ver `classify/service.py` como exemplo)
- **Ao adicionar parâmetro:** default que preserva comportamento atual (backward compat)
- **Commits pequenos e semânticos** com prefixo (`feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`)
- **Um commit = uma ideia**

### Nunca
- **Hardcoded paths** (ex: `C:/Users/felip_local/Documents/paredes.png`)
- **Thresholds específicos por PDF** (viola invariante #4)
- **`strict=False` em load_state_dict** sem reportar explicitamente keys ignoradas
- **Scores que não refletem qualidade** (ver `_geometry_score` antigo como anti-exemplo)
- **Push direto em main** (sempre branch + PR)
- **`--no-verify`** em commits (hooks existem por motivo)

### Quando em dúvida
- Ler `AGENTS.md` §2 (invariantes) e §6 (proibido)
- Consultar 2ª LLM ou rodar teste mínimo
- Perguntar ao usuário se a decisão é irreversível (destrutiva)

---

## 7. Debug eficiente

### Comparar runs
```bash
python main.py extract planta_74.pdf --out runs/before
# aplicar patch
python main.py extract planta_74.pdf --out runs/after
diff <(jq '.scores, .metadata.connectivity' runs/before/observed_model.json) \
     <(jq '.scores, .metadata.connectivity' runs/after/observed_model.json)
```

### Visualização obrigatória
```bash
# Ver debug_walls.svg ANTES de confiar em métricas
# Métricas podem mentir (ex: retention score invertido) — imagens não
open runs/<name>/debug_walls.svg
open runs/<name>/debug_junctions.svg
```

### Quando patches de reconnect falharem
Comum em plantas com:
- Walls diagonais (LSD falha, AFPlan aceita)
- Hachura densa (text-baseline filter mata walls reais)
- Plantas pequenas <20 walls (snap over-aggressive sem floor)

Nesses casos, consultar `docs/SOLUTION-FINAL.md` seção "O que PODE precisar ajuste".

---

## 8. Estado das coisas (2026-04-21)

### Baseline conhecido em planta_74
```
walls: 94 (meta ≤ 150)
rooms: 14 (ideal 6-15)
junctions: 161 (split graph)
orphan_component_count: 7  ← alto, problema
orphan_node_count: 16
geometry_score: 0.156  ← É RETENÇÃO, não qualidade
topology_score: 0.275
room_score: 0.581
topology_quality: poor
warnings: [walls_disconnected, many_orphan_components]
```

### Meta pós-fixes
```
orphan_components: ≤ 2
perimeter_closure: ≥ 0.90  (novo score, ver patch 03)
quality_score: ≥ 0.75
warnings: [] (ou só notes, não blockers)
```

### Runs base conhecidos
- `runs/planta_74/` — PDF principal, 74m²
- `runs/proto/p10..p12_v1_run/` — **VIOLA INV #4** (usa PDFs pré-processados red-mask)

---

## 9. Ferramentas externas úteis

- `cv2.createLineSegmentDetector` — LSD real, OpenCV core 4.5.4+ (patent expirou)
- `cv2.ximgproc.createFastLineDetector` — alternativa em contrib
- `scipy.spatial.cKDTree` — nearest-neighbor queries O(n log n)
- `skimage.morphology.skeletonize(method='lee')` — robusto em walls espessas
- `networkx` — cycle detection, connectivity
- `shapely.polygonize` — detectar rooms fechados

### Para DL (se Fase 4 aplicada)
- `torch` + `torchvision`
- `segmentation-models-pytorch` — NÃO serve para CubiCasa5K (arch incompatível)
- `gdown` — download de Google Drive (weights CubiCasa5K)
- Clone `github.com/CubiCasa/CubiCasa5k` + `pip install -e .`

---

## 10. Como validar que "resolveu" a planta despedaçada

### Critérios (todos devem ser verdade)
```python
def plan_is_resolved(observed_model) -> bool:
    return all([
        observed_model['metadata']['connectivity']['largest_component_ratio'] >= 0.90,
        observed_model['metadata']['connectivity']['orphan_component_count'] <= 2,
        len(observed_model['rooms']) >= 1,  # pelo menos 1 room
        # visual inspection de debug_walls.svg
    ])
```

### Visual inspection manual (obrigatória)
Abrir `debug_walls.svg` e verificar:
- Perímetro da planta visivelmente **fechado**
- Nenhuma "ilha" solta longe do resto
- Walls alinhadas com o PDF original (não deslocadas)

### Regression tests
- Planta_74 deve continuar funcionando APÓS mudanças
- P12 deve funcionar SEM red-mask manual (invariante #4)
- Tests sintéticos (`tests/fixtures.py`) devem passar

---

## 11. Contatos relevantes

Se precisar escalar:
- Felipe (GFCDOTA, dono do repo): decisões arquiteturais
- Documentação: este CLAUDE.md + `docs/*.md` + `AGENTS.md`
- Testes: `pytest -v` + comparação empirica de runs

---

**Última atualização:** 2026-04-21
**Contexto anterior:** sessão Claude autônoma (worktree sleepy-tu-9247d5)
**Estado:** docs + patches propostos, não aplicados. Aguardando validação empírica e decisão de integração.
