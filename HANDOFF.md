# HANDOFF — MESA DE JANTAR = PASS (programa Arquiteto de Classe de móveis)

> Fio da meada entre sessões. Seção vazia = pergunta aberta, não "N/A" mudo.
> Gerado/atualizado pela skill `/handoff`. Snapshot LOCAL.

- **Data / sessão:** 2026-06-16 · handoff + 3 ciclos (002/003/004) WARN→PASS
- **Repo / app:** apps/sketchup-mcp · remote `GFCDOTA/sketchup-mcp`
- **Status geral:** GREEN — **classe MESA DE JANTAR = PASS, forma CONGELADA**
  (GPT "congelaria a forma"). Única ação aberta: **landar a PR** em develop
  (decisão do Felipe; gh sem escopo → URL de compare).

## 1. Objetivo atual
Programa **Arquiteto de Classe de móveis** (forma antes de detalhe, sem overfit,
melhoria sobe pro gate, prova por matriz + veredito visual GPT). **MESA DE
JANTAR concluída** como 6ª classe PASS. **Placar ×6:** SOFÁ(3c)·POLTRONA(2c)·
CAMA(2c)·MESA-CENTRO(2c)·RACK(2c)·**MESA-DE-JANTAR(4c)** — todas PASS.

## 2. Branch atual
- **Branch:** `feat/dining-table-cycle001` · **base:** `origin/develop`
- **Último commit:** `b698e5d` — *feat(dining-class): cycle004 — rect_family
  afina tampo+saia*. (f9ad2e9 c001 · 6b765b8 c002 · 6797043 c003 · b698e5d c004)
- **Ahead/behind:** **ahead 4 / behind 0** · **PUSHADA**. Tree limpa exceto
  `HANDOFF.md` (untracked, este doc) + `cell_*.png` (scratch, não commitar).

## 3. Arquivos alterados (`git diff --stat origin/develop..HEAD`)
```
tools/dining_table_class.py              # builder + gates da classe (4 ciclos)
tests/test_dining_table_class.py         # 28 testes (12 sabotagens)
artifacts/.../dining_table_class_matrix.png    # evidência visual (regenerada)
artifacts/.../dining_table_class/matrix_report.json   # gate determinístico
```
Builder Python-only / SU-free — verificado integralmente nesta máquina.

## 4. Decisões tomadas (loop FAIL/WARN → regra → gate → prova → veredito)
- **cycle001 (f9ad2e9):** teoria executável; derivada de LUGARES; 3 arquétipos;
  satélites (cadeira-proxy/envelope/anel) VISÍVEIS. → **GPT = WARN** (round fraco).
- **cycle002 (6b765b8):** `round_compact` vira **redonda real** — tampo+pedestal
  por **disco de bandas** (`_disc_bands`, verts8); coluna fina, prato menor/baixo.
  Gate: octógono(`corner_cut`)→`round_facets≥16`. → **GPT round = IMPROVED**.
- **cycle003 (6797043):** `oval_soft` vira **oval real** — pontas **semielipse**
  (`_oval_end_bands`); perna menos frágil. Gate: `tip_frac`→`oval_facets≥6`. →
  **GPT oval = IMPROVED**.
- **cycle004 (b698e5d):** `rect_family` afina **tampo+saia+reveal** (`apron_inset`)
  → lê tampo+pernas, não bloco. Gate: `apron_h≤0.09`. → **GPT rect = IMPROVED**.
- **Veredito FINAL GPT = PASS** ("congelaria a forma; 3 arquétipos leem como
  famílias distintas e funcionais"). **Não auto-julguei nenhum veredito.**
- **Técnica reusável nascida aqui:** curva/disco por BANDAS verts8 (round + oval)
  dentro da primitiva caixa do `render_parts_iso`.

## 5. Testes rodados + evidências (nesta sessão, HEAD b698e5d)
- **Suíte completa:** `pytest -q` → **750 passed, 5 skipped** (skips benignos).
- **Classe:** `pytest tests/test_dining_table_class.py -q` → **28 passed**.
- **Prova do módulo:** 9/9 derivados PASS · **12/12 sabotagens reprovam**.
- **Matriz canônica regenerada:** `artifacts/review/furniture/dining_table_class/
  dining_table_class_matrix.png` (round 7→38, oval 9→23 partes; 3 arquétipos PASS).
- **Veredito visual GPT-via-Chrome (real, ele confirmou abrir cada imagem):**
  c001 WARN → c002 round IMPROVED → c003 oval IMPROVED → c004 rect IMPROVED →
  **CLASSE = PASS / "congelaria a forma"**. Thread "Crítica de Mesa de Jantar".

## 6. Pendências
- **(landar — decisão do Felipe) PR `feat/dining-table-cycle001` → develop**
  (cobre cycle001–004, classe PASS): branch pushada, ready. `gh pr create` falha
  (token sem `Pull requests:write`) → abrir/mergear pela URL de compare. Decidir:
  merge agora (classe congelada) — recomendado.
- **(follow-up de escala)** re-validar móveis/V-Ray no `PT_TO_M=0.0259`.
- **(detalhe, outro estágio)** cadeiras/proxies — o juiz notou "limitações de
  detalhe nas cadeiras", mas a FORMA da classe está OK; detalhe é fase posterior.
- **(fila do programa)** próxima classe: **cadeira** → guarda-roupa (builder
  existe) → criado-mudo (régua da cama + nightstand_builder prontos).
- **(outras branches — não tocar):** scene-materials (pré-veredito), sofa-cushion-
  bevel, planta74-peitoril, sofa-skill, noc-t1/t2 (não-pushadas).

## 7. Riscos
- **`main` divergiu de `develop`:** `develop` 124 à frente de `main`; `main` tem
  6 commits que não estão em develop. Reconciliar/auditar ANTES do próximo merge
  develop→main. `develop` == `origin/develop` (limpo).
- **PR via `gh` FALHA** (token) → URL de compare.
- **raw.githubusercontent cacheia por ref** → veredito GPT sempre com URL fixada
  no SHA do commit (não no nome da branch).

## 8. Próximos 5 passos (menor risco primeiro)
1. **Landar a classe:** abrir/mergear a PR `feat/dining-table-cycle001` → develop
   pela URL de compare (classe PASS, congelada).
2. Atualizar o placar do programa (6 classes PASS) onde for visível ao Felipe.
3. **Iniciar a classe `cadeira`** (próxima da fila) — mesmo template:
   FASE 0 → spec/teoria → derive por arquétipo → matriz → veredito GPT.
4. (Quando abrir o estágio de detalhe) cadeiras-proxy de jantar viram cadeiras
   convincentes — é o que o juiz deixou explicitamente pra depois da forma.
5. Reconciliar `main`↔`develop` antes de qualquer promoção a `main`.

## 9. Comandos úteis (paths absolutos)
```powershell
E:\Claude\apps\sketchup-mcp\.venv\Scripts\python.exe -m pytest -q
E:\Claude\apps\sketchup-mcp\.venv\Scripts\python.exe -m pytest tests\test_dining_table_class.py -q
E:\Claude\apps\sketchup-mcp\.venv\Scripts\python.exe -m tools.dining_table_class   # prova + sabotagens
E:\Claude\apps\sketchup-mcp\.venv\Scripts\python.exe -c "from tools.dining_table_class import build_matrix; build_matrix('artifacts/review/furniture/dining_table_class')"
git -C E:\Claude\apps\sketchup-mcp log --oneline develop..feat/dining-table-cycle001
```
- **PR (URL de compare):**
  `https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feat/dining-table-cycle001`
- **Veredito GPT:** push + URL raw fixada no SHA → ChatGPT-web na extensão Chrome
  (NÃO auto-julgar; Chrome off → BLOCKED_VISUAL_REVIEW).

## 10. O que NÃO fazer
- **Não auto-julgar visual** (IMPROVED/SAME/WORSE/PASS) — é do GPT-via-Chrome.
- **Não mexer na FORMA da classe sem novo ciclo formal com juiz** (forma
  congelada; mudança casual de forma é proibida — padrão das outras 5 classes).
- **Não push em `main`** (e há divergência main↔develop a reconciliar — §7).
- **Não commitar** `cell_*.png` nem `HANDOFF.md` dentro da PR da feature.
- **Não tentar `gh pr create/merge`** (token) — URL.
- **Não overfitar:** fix de um arquétipo sobe pro gate + sabotagem + matriz.

## 11. Checkpoint p/ próxima sessão
Parei em `feat/dining-table-cycle001` @ `b698e5d` — **classe MESA DE JANTAR =
PASS, forma congelada** (4 ciclos, veredito GPT externo), tree limpa (fora
`HANDOFF.md`/`cell_*.png`), suíte **750 passed / 5 skipped**. **Primeiro
movimento ao retomar:** landar a PR `feat/dining-table-cycle001` → develop pela
URL de compare; depois iniciar a classe **cadeira**. **Sinal de que está tudo de
pé:** `git status` limpo, branch ahead 4, `pytest -q` 750✓, e a matriz canônica
mostra os 3 arquétipos lendo redondo/oval/retangular distintos.
