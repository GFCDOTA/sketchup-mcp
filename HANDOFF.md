# HANDOFF — Estúdio Banheiro (2026-08-09 — sessão de kickoff pra próxima)

> Substitui o HANDOFF de 2026-08-08 (p20/9.2). Esta sessão foi MUITO além
> daquele checkpoint — ler este documento inteiro antes de retomar.

- **Data / sessão:** 2026-08-09 · sessão longa (2026-08-08 → 09, perto do
  limite de tokens — por isso este handoff)
- **Repo / app:** `E:\Claude\worktrees\estudio-banheiro` (worktree de
  `apps/sketchup-mcp`, branch `feat/estudio-banheiro`)
- **Status geral:** 🟢 GREEN — tudo commitado, pushed, working tree limpa

## 1. Objetivo atual
Estúdio Banheiro: gerar render V-Ray fotorrealista do BANHO 01 (planta_74,
STONE_MONOLITH) num loop iterativo com juiz GPT, curadoria do Felipe em
produtos reais, e depois estender pros outros 2 cômodos molhados (BANHO 02,
LAVABO) com temas próprios. Critério de parada do Felipe: "faz sentido pra um
designer de interiores" (já batido — ver §4).

## 2. Branch atual
- **Branch:** `feat/estudio-banheiro` · **base:** `fix/planta74-furnished-fidelity`
  (⚠️ NÃO é `develop` — ver §6 pendência de repo)
- **Último commit:** `e7b5635` "feat(banhos): p28 GPTMATCH04 — highlight da
  parede esquerda controlado; espelho oficialmente deixou de ser reclamação"
- **Ahead/behind do remoto:** sincronizado (`origin/feat/estudio-banheiro`),
  nada pendente de push

## 3. Arquivos alterados (vs base, cumulativo da branch)
159 arquivos, +3723/-206. Os que mais importam pra quem retomar:
- `tools/bathroom_layout.py` (+843) — o BRAIN: geometria paramétrica de todas
  as peças do banheiro + sistema de TEMA POR CÔMODO (`THEMES` dict).
- `tools/tweak_vrscene.py` (+205) — materiais V-Ray por `mat_name`, temas
  `oak`/`nero`, beauty pass (pedra/vidro/espelho refinados).
- `tools/render_banho_auto.py` (NOVO, 132 linhas) — enquadra/ilumina QUALQUER
  banho automaticamente reusando a receita aprovada do BANHO 01.
- `tools/render_banho_vray.py` (+137) — CLI de render; ganhou `--noise`.
- `tests/test_bathrooms_style.py` — 28 travas (red→green a cada mudança de
  linguagem).
- `artifacts/estudio_banheiro/ITERATIONS.md` — placar COMPLETO de toda
  iteração (p01→p28), leia antes de mais nada.
- `artifacts/estudio_banheiro/ORCAMENTO_V0.md` — orçamento real com
  preço+link (GPT com browsing, 08/08/2026).
- `artifacts/estudio_banheiro/REFERENCE_KIT_PRODUTOS.md` — kit de produtos
  reais curado (Roca Gap, Deca Slim/Unic/Flex Max, Ideia Glass Nobre).

## 4. Decisões tomadas
- **Curadoria de produto real > estética procedural**: Felipe pediu pra
  ancorar louças/metais em produto real (não "esculpir de cabeça"). GPT deu
  kit inicial → Felipe curou num front local (:8788) → trocou torneira/
  gabinete/chuveiro → GPT deu substitutos com medidas → implementado. Nota
  subiu 9.2→9.4.
- **Vaso "mantido" ≠ geometria antiga**: Felipe pegou um vacilo meu — eu
  mantive a privada procedural antiga achando que "manter na curadoria" =
  "não mexer". Errado: "manter o Roca Gap" = modelar com a CARA do Gap.
  Refeito (rounded-rect, saia fechada). Nota 9.4→9.5.
- **Espelho preto morto (reclamação desde p14)**: diagnosticado por
  COMPARAÇÃO com imagem gerada pelo próprio GPT como referência. Causa
  física: o espelho reflete a parede escura do box, sem conteúdo algum.
  GPT deu 3 opções (light-slot / painel flutuante / yaw do espelho);
  implementada a Opção A (light-slot vertical rasante, kind `kb_slot_led`).
  Levou 2 tentativas — a primeira errou os EIXOS (fino devia ser em Y não em
  Z) e estourou o espelho pra branco morto. Corrigido. Depois, comparar com a
  MESMA imagem de referência e reabrir luz/exposição destravou de vez: juiz
  confirmou "espelho finalmente deixou de ser o maior problema" (8.9/10).
- **Tema por cômodo (não só o BANHO 01)**: Felipe pediu tema diferente pros
  outros 2 banhos. Implementado via sufixo de `mat_name` por sala
  (`THEMES` dict em `bathroom_layout.py`) — BANHO 01 fica CONGELADO
  (stone_monolith, sem sufixo), BANHO 02 = `oak_sereno`, LAVABO =
  `nero_ardosia`. `render_banho_auto.py` generaliza câmera/luz pra qualquer
  cômodo reusando a fórmula aprovada.
- **Orçamento é responsabilidade do GPT com browsing**, não invenção —
  pesquisou preço+link real pra cada item (V0 = catálogo puro, sem mão de
  obra/marcenaria sob medida).

## 5. Testes rodados + evidências
- **Suíte de estilo:** `pytest tests/test_bathrooms_style.py -q` → **28
  passed** (última rodada, sem falhas). Rodar de novo antes de qualquer
  render pra garantir que nada regrediu.
- **Gate determinístico:** N/A (não há gate visual automático nesse fluxo —
  é 100% veredito humano/GPT).
- **Evidência humana (renders promovidos):**
  `artifacts/estudio_banheiro/iterations/` tem TODO o histórico p01→p28 +
  `banho02_oak_p24/p25.png` + `lavabo_nero_p24/p25.png`.
  Hero final da sessão: `banho01_GPTMATCH04.png` (também espelhado em
  `ops/estudio-front/assets/banho01.png` pro painel local).
- **Veredito visual (GPT-via-Chrome, chat fixo "Estúdio Banheiro — Claude ⇄
  GPT"):** BANHO 01 = **APROVADO_DESIGN: SIM, 9.6/10** (era o gate de
  parada). Depois disso, polish contínuo sem re-perguntar aprovação: última
  nota validada = **8.9/10** no critério "chegou mais perto da referência" +
  espelho resolvido. BANHO 02 = 8.8 (AINDA_NÃO — não é o gate de parada
  desse cômodo, é só nota de polish). LAVABO = 8.6 (AINDA_NÃO).

## 6. Pendências
- **BANHO 02 e LAVABO não passaram pelo mesmo tratamento fino de luz/mood**
  que o BANHO 01 recebeu nesta sessão (fills quentes, box com profundidade,
  highlight controlado). É "falta fazer", não "esperando decisão".
- **V1 do orçamento** (pedra+porcelanato por m²+vidro+instalação+mão de
  obra) foi oferecida pelo GPT mas Felipe ainda não pediu — está
  "esperando decisão".
- **Feature nova: rotação de peça (yaw) no builder** — o juiz pediu yaw
  2° no espelho pra resolver de vez, mas o builder atual só desenha peças
  retas nos eixos. NÃO implementado (fora de escopo dessa sessão; contornado
  via luz/câmera em vez de geometria).
- **PR pra develop**: branch tem 20+ commits não-mergeados, é off
  `fix/planta74-furnished-fidelity` (não `develop` direto) — decisão de
  merge não foi tomada nesta sessão nem na anterior.

## 7. Riscos
- **Escala do brain**: `render_banho_auto.py` e qualquer script que chame
  `build_boxes` PRECISA de `os.environ.setdefault("PT_TO_M", "0.0259")`
  ANTES de importar `tools.bathroom_layout` — senão as peças saem 1.36×
  maiores e a câmera aponta pro vazio (render sai PRETO). Gotcha pago 2×
  nesta sessão.
- **Câmera <8in (≈20cm) de qualquer parede = render PRETO total** (a lente
  fica dentro da geometria). `render_banho_auto.py` já tem `WALL_PAD=8.0`
  de proteção — não reduzir esse valor sem entender por quê.
- **Fill light <18in de parede = disco escuro projetado** no reflexo/halo
  (a esfera de luz projeta a própria silhueta). `FILL_PAD=18.0` protege
  isso no auto-framer; em renders manuais, clampar manualmente.
- **Eixos de peça retangular**: pra parede `orient="v"` (normal em X), o
  eixo "ao longo da parede" é Y e a altura é Z — inverter isso faz um
  "rasgo fino" virar um painel gigante (já aconteceu 1×, ver §4).
- **Bridge GPT :8899 é INSTÁVEL** — ver §9 gotchas. Não é bug do código, é
  característica do bridge; sempre ter o fallback Chrome pronto.

## 8. Próximos 5 passos
1. Rodar `pytest tests/test_bathrooms_style.py -q` pra confirmar 28/28
   antes de qualquer mudança nova (baseline de segurança).
2. Se for continuar o polish: aplicar a MESMA receita de luz desta sessão
   (fills mais quentes, box −0.3EV, highlight controlado) no BANHO 02 e
   LAVABO — usar `render_banho_auto.py --room r006` / `r007` como ponto de
   partida, depois ajustar `--fill`/`--rect` manualmente como foi feito pro
   BANHO 01 (comandos exatos no ITERATIONS.md, seção "GPTMATCH").
3. Se Felipe pedir a V1 do orçamento: reabrir o chat fixo do GPT (via
   bridge ou Chrome) e pedir a cotação completa (pedra m², porcelanato m²,
   vidro+instalação, mão de obra) — ele já sabe o contexto.
4. **Enviar o .skp atualizado pro Felipe** (`SendUserFile`) se ele pedir
   "ver no SketchUp" — última promoção foi antes do tema-por-cômodo, pode
   estar desatualizado; rodar `python -m tools.furnish_apartment` primeiro.
5. Considerar a feature de rotação de peça (yaw) no builder SE o Felipe
   quiser fechar o espelho 100% (hoje está "resolvido" mas não "perfeito"
   segundo o juiz mais rigoroso).

## 9. Comandos úteis
```bash
# venv canônico (SEMPRE usar este, não o Python global)
VENV=/e/Claude/apps/sketchup-mcp/.venv/Scripts/python.exe

# travas de estilo (rodar sempre antes de commitar mudança no brain)
cd /e/Claude/worktrees/estudio-banheiro
$VENV -m pytest tests/test_bathrooms_style.py -q

# rebuild do .skp mobiliado (após qualquer mudança em bathroom_layout.py)
$VENV -m tools.furnish_apartment

# render automático de qualquer banho (câmera+luz derivadas da receita aprovada)
$VENV -m tools.render_banho_auto --room r005 --out artifacts/planta_74/furnished/kitchen_angles/x.png   # r005=BANHO01 r006=BANHO02 r007=LAVABO

# render manual fino (comando do hero final desta sessão, BANHO 01)
$VENV -m tools.render_banho_vray --eye "521,632,64" --target "540,569,45.5" \
  --fov 62 --iso 220 --shutter 65 --fnum 4.5 --sky 0.30 --sun 0.10 --burn 0.6 \
  --hide "porta,door" --width 1600 --height 2000 --noise 0.008 \
  --fill "534,585,50,32,10;525,546,44,38,8;528,588,72,20,10;520,610,66,14,10;523,584,50,34,9;523,596,64,34,9;545,600,50,30,12;548,585,42,26,10" \
  --rect "521,545,93,22,16,50,0,0,-1" \
  --out artifacts/planta_74/furnished/kitchen_angles/x.png

# painel local ao vivo (status + curadoria) — subir por sessão, SEM watchdog
cd /e/Claude/ops/estudio-front && $VENV server.py   # http://127.0.0.1:8788

# bridge GPT (juiz) — verificar antes de perguntar
curl -s -m 8 http://127.0.0.1:8899/health
# se offline: Docker Desktop precisa estar de pé (o container sobe junto)
```

## 10. O que NÃO fazer
- **Não mexer no BANHO 01 sem motivo** — está congelado no tema
  `stone_monolith` (sem sufixo de `mat_name`) e aprovado. Mudança nele
  exige re-passar pelo juiz.
- **Não esquecer `PT_TO_M=0.0259`** antes de importar `bathroom_layout`
  fora do `furnish_apartment.py` (que já seta isso) — ver §7.
- **Não confiar em resposta do bridge `/ask` que chega em <20s IDÊNTICA à
  anterior** — é STALE (cache), não resposta nova. Sempre conferir no
  Chrome (`get_page_text` ou `javascript_exec` no chat fixo) antes de agir.
- **Não tratar erro "Algo correu mal" do ChatGPT como ausência de
  resposta** — às vezes a resposta REAL aparece alguns segundos depois,
  mesmo com o banner de erro visível (aconteceu 2× nesta sessão). Reler a
  página antes de reenviar/retry.
- **Não reviver NOC/dashboard com daemon** — o painel `ops/estudio-front`
  é INTENCIONALMENTE descartável, sobe por sessão, sem watchdog/task
  agendada (lição do NOC removido 2026-07-24).
- **Não fazer merge pra `develop`** sem decisão explícita do Felipe — a
  branch é off `fix/planta74-furnished-fidelity`, não direto de `develop`.

## 11. Checkpoint p/ próxima sessão
Parei logo depois de fechar o BANHO 01 num estado bom (mood aproximado da
referência, espelho resolvido, nota 8.9 confirmada pelo juiz) — Felipe pediu
esse handoff porque a sessão está perto do limite de tokens. Primeiro
movimento ao retomar: ler `artifacts/estudio_banheiro/ITERATIONS.md`
(placar completo) e este HANDOFF.md, depois perguntar ao Felipe se quer
continuar pro BANHO 02/LAVABO ou fechar por aqui. Sinal de que está tudo de
pé: `pytest tests/test_bathrooms_style.py -q` → 28 passed; `git status`
limpo; painel `http://127.0.0.1:8788` mostra o último render se o server
ainda estiver rodando (senão, subir de novo — é local, não precisa do
Felipe fazer nada).
