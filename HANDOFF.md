# HANDOFF — Estúdio Banheiro + merge pra develop (2026-08-09, fim de sessão)

> **Atualização final (mesma sessão, commit `100b3be`):** depois do merge
> (§abaixo), o Felipe pediu redesign do painel `ops/estudio-front` (tirar
> "Etapas do Pedido", consertar "Placar do Loop", render em destaque) + um
> **chat com memória vetorial**: `ops/estudio-front/rag_chat.py` (novo) fala
> com Ollama (`llama3.1:8b` — o modelo `interior-designer` local é fixado pra
> JSON de layout, não serve pra bate-papo) e salva preferências explícitas
> (botão "salvar na memória") numa coleção Qdrant própria
> (`felipe_preferences`, separada do `rag_chunks` do RAG de fidelidade — não
> mexe naquele corpus). Testado ponta a ponta: salvou "Felipe odeia piso
> branco" e uma pergunta nova recuperou e usou esse contexto. Commitado e
> pushado DIRETO em `develop` (já estava nela, sem branch nova). Máquina foi
> desligada logo em seguida a pedido do Felipe — se esta sessão reabrir e o
> painel não responder, é só isso: `cd ops/estudio-front &&
> ../../.venv/Scripts/python.exe server.py` sobe de novo.

> Substitui o HANDOFF de 2026-08-09 anterior (o que dizia "branch NÃO é
> develop" — isso mudou: **já está em develop, pushado**). Sessão terminando
> aqui porque o Felipe vai logar de outro computador. Ler inteiro antes de
> retomar — não é continuação do BANHO 01 sozinho, teve merge grande no fim.

- **Data / sessão:** 2026-08-09, fim de sessão (troca de computador)
- **Repo / app:** `apps/sketchup-mcp` (branch **`develop`**, pós-merge — não é
  mais `feat/estudio-banheiro`)
- **Status geral:** 🟢 GREEN — merge limpo, pushado, suite verde (mesmas
  falhas pré-existentes de sempre), painel funcionando

## 1. Objetivo atual

Duas linhas de trabalho convergiram nesta sessão:
1. **Estúdio Banheiro** (BANHO 01 planta_74, STONE_MONOLITH) — indo além do
   veredito visual (hero aprovado 9.2-9.6) pra uma **auditoria de
   buildability**: descobrir e corrigir bugs REAIS de geometria/pipeline que
   o veredito visual não pegava.
2. **Consolidação de repo** — a pedido do Felipe, mergeado TUDO que tinha
   trabalho maduro nesta máquina pra `develop`, deixando de fora o que tem
   problema conhecido ou é lixo de sistema morto.

## 2. Branch atual

- **Branch:** `develop` · upstream `origin/develop`, sincronizado
- **Último commit:** `4a70232` = merge de `feat/estudio-banheiro` (101
  commits) sobre `9b5f0cf`, que por sua vez veio depois do merge de
  `fix/planta74-furnished-fidelity` (32 commits)
- **Ahead/behind do remoto:** 0/0 — **já pushado** (`git push origin develop`
  rodou com sucesso nesta sessão)
- As branches `feat/estudio-banheiro` e `fix/planta74-furnished-fidelity`
  continuam existindo (local + remoto) — **não foram deletadas** pós-merge
  (decisão: não apagar sem pedido explícito). Podem ser limpas quando quiser.

## 3. Arquivos alterados (resumo do que entrou em develop)

**Via `fix/planta74-furnished-fidelity` (32 commits):** `tools/bathroom_layout.py`,
`tools/bedroom_designer.py`, `tools/circulation_gate.py` (novo),
`tools/furnish_apartment.py`, `tools/kitchen_layout.py`,
`tools/place_layout_skp.rb`, testes novos (`test_circulation_gate.py`,
`test_kitchen_layout_style.py`, `test_living_room_style.py`,
`test_suites_style.py`), `references/felipe/VERDICT_APE_V1_2026_08_03.md`.

**Via `feat/estudio-banheiro` (101 commits, todo o trabalho desta sessão):**
- `core/scale.py` — **guard fail-fast** `assert_pt_to_m_for_source()` contra
  o bug histórico de escala 1.36x (silencioso antes, agora `RuntimeError`).
- `tools/spatial_model.py` — chama o guard acima (ponto único usado por
  bathroom/bedroom/kitchen/layout brains).
- `tools/bathroom_layout.py` — fix do teto (`join_style=2` mitre, resolve
  `add_face`=nil silencioso do Ruby), fix do gap parede↔teto
  (`WALL_TOP_M`), schema `PRODUCT_BY_KIND` (BOM real: Roca The Gap, Deca
  Slim/Unic/Flex Max, com `verification_status`).
- `tests/conftest.py` (novo) — fixa `PT_TO_M=0.0259` antes de qualquer
  coleta pytest (elimina dependência de ordem de import entre arquivos).
- `tests/test_bathrooms_style.py` — 6 testes novos: `GEOMETRY_INTEGRITY_GATE`
  (`test_ceiling_polygon_is_valid_simple`, `test_wall_panels_reach_ceiling_no_gap`)
  travam os 2 bugs reais achados/corrigidos, sem precisar renderizar.
- `.claude/skills/interior-project-audit/SKILL.md` (novo) — skill de 12
  gates de buildability (não estética), desenhada em consulta ao GPT-Docker.
- `.claude/agents/interior-project-auditor.md` (novo) — agent read-only que
  roda esses gates, postura "olhos de águia" + sugestão tipo loja de
  mobiliados. **⚠️ Ainda não aparece no `Agent` tool desta sessão** — agents
  novos só carregam em sessão nova do harness.
- `ops/estudio-front/` (novo dentro do repo — migrado de `E:\Claude\ops\`,
  que era scratch fora de qualquer git) — painel local `:8788`,
  **`index.html` reescrito 100% em React** (CDN + Babel standalone, sem
  build/npm; `server.py` continua stdlib puro). Widget de "engrenagem"
  (canto flutuante) mostra atividade ao vivo do `interior-designer`.
- Vários renders de auditoria em `artifacts/estudio_banheiro/corner_audit/`.

## 4. Decisões tomadas

- **Skill `interior-project-audit` nasceu de consulta ao GPT-Docker
  (:8899)** pedindo pra ele vestir papel de arquiteto real + pesquisar
  referência construída (browsing) antes de opinar — não foi invenção
  minha, é baseada na resposta dele. Regra-raiz: *"render bonito nunca pode
  transformar projeto tecnicamente incompleto em aprovado."*
- **GPT reordenou minha priorização** (eu ia primeiro no teto, ele disse
  escala primeiro — "pode invalidar silenciosamente tudo") — segui a ordem
  dele: UNITS → CEILING → GEOMETRY GATE → (parei antes do LIGHT SLOT).
- **Light slot vertical NÃO foi mexido** — decisão consciente (minha +
  validada pelo GPT) de não arriscar refactor 3D numa feature cuja própria
  permanência no projeto não está decidida. GPT sugeriu marcar
  `execution_geometry: FAKE_SURFACE` + `design_status: REVIEW` — **não
  implementado ainda**, é sugestão pendente.
- **Merge pra develop:** Felipe pediu "push e merge de tudo que existe
  nessa máquina a respeito do sketchup". Levantei o cenário (worktrees,
  branches, stashes) e voltei com escopo reduzido, confirmado por ele via
  pergunta direta:
  - ✅ `feat/estudio-banheiro` + `fix/planta74-furnished-fidelity` → merge
    limpo em `develop`, pushado.
  - ❌ `feat/mobiliar-bedroom-layout` (57 commits, só no GitHub) — **NÃO
    mergeado**: o próprio MANIFEST dela avisa scale-leak/WARN conhecido,
    pendente de decisão de produto. Deixada de fora por pedido do Felipe.
  - ❌ 6 branches `chore/noc-nf-*` — sobras do sistema NOC que o Felipe
    mandou remover em 2026-07-24. Não ressuscitar. Deixadas de fora.
  - Mecanismo: merge local + `git push origin develop` direto (sem PR —
    `gh` não tem permissão de criar/mergear PR nesta máquina, só push;
    `develop` não tem a trava de "nunca push direto" que `main` tem).

## 5. Testes rodados + evidências

- **Suíte completa pós-merge:** `pytest tests/ -q` → **1262 passed, 19
  failed, 6 skipped**. As 19 falhas são **as mesmas de sempre**
  (`test_bed_placement_gate`, `test_bedroom_layout` sintético,
  `test_circulation_gate`, `test_material_de_verdade`, `test_room_modes`,
  `test_variant_sweep`) — confirmadas pré-existentes via `git stash` +
  comparação de baseline **antes** de qualquer mudança minha, nesta mesma
  sessão. **Zero regressão introduzida pelo merge ou pelos fixes.**
- **`tests/test_bathrooms_style.py` isolado:** 34/34 verde (28 antigos + 6
  novos do `GEOMETRY_INTEGRITY_GATE`).
- **Evidência humana (render):** canto NO do BANHO 01 foi de vão preto TOTAL
  (bug do teto) → frestinha residual pequena (após os 2 fixes de geometria).
  Ver `artifacts/estudio_banheiro/corner_audit/banho01_c1_NO_walltop_fix.png`.
- **Veredito visual:** não houve novo veredito formal do Felipe/GPT sobre os
  fixes de geometria em si (são fixes de *buildability*, não de estética —
  o hero já estava aprovado 9.2-9.6 antes). A auditoria de código (agent
  `interior-project-auditor` via `general-purpose`, já que o agent nomeado
  não carrega nesta sessão) e a consulta ao GPT-Docker confirmaram os
  achados, mas isso não substitui o gate visual humano de verdade.

## 6. Pendências

**Falta fazer (determinístico, não precisa de decisão humana):**
- Bug real no **LAVABO**: `tools/bathroom_layout.py:568`
  (`stone = kind in ("box", "ducha")`) nunca ativa a textura de ardósia
  veinada na parede da bancada porque o lavabo não tem `box`/`ducha` — o
  tema NERO_ARDÓSIA promete monólito de pedra e não entrega. Achado pelo
  `interior-designer` (agent), ainda não corrigido.
- Fila P1 do GPT (ordem que ele recomendou, não atacada ainda):
  `LIGHTING SCHEMA` (separar `project_lights` de `render_only_fill` —
  ele quis isso *antes* de decidir o light slot) → `MEP SCHEMA` scaffolding
  (campos + `UNVERIFIED/CONFLICT`, sem inventar hidráulica real) →
  `WET-ZONE gate` da janela do box → `RULE PROVENANCE` dos clearances → só
  então decidir o LIGHT SLOT (`REMOVE`/`KEEP_AS_CONCEPT`/`EXECUTABLE`).
- Sugestão do GPT ainda não implementada: proibir `rescue StandardError`
  engolindo falha de geometria obrigatória no `.rb` — deveria estourar
  `REQUIRED_GEOMETRY_CREATION_FAILED` em vez de a peça sumir em silêncio
  (isso teria pego o bug do teto na 1ª iteração, não 20 depois).
- Sliver residual pequena no canto NO (não mais estrutural) — suspeita:
  peça `kb_trilho` do box (z 2.44-2.462) não fecha perfeitamente contra o
  teto/vidro naquele ângulo específico. Não investigado a fundo (parei por
  custo/benefício).

**Esperando decisão humana (Felipe):**
- `feat/mobiliar-bedroom-layout` — mergear ou não? Tem scale-leak/WARN
  conhecido documentado em `.ai_bridge/HANDOFF.md` da própria branch +
  `E:\Claude\archive\pending-merge\mobiliar\MANIFEST.md`. Ninguém decidiu
  ainda se vale a pena resolver o WARN e trazer, ou descartar.
- As 6 `chore/noc-nf-*` — deletar (local+remoto) ou deixar existir sem
  mergear? Não apaguei porque não foi pedido explicitamente, só "deixar de
  fora do merge".
- Diretrizes dos 8 cômodos do `interior-designer` (SUITE 01, SALA, SUITE 02,
  COZINHA, BANHO 02, LAVABO, A.S./Terraços) — são propostas de
  primeiro/segundo passe, nenhuma foi implementada em render ainda (exceto
  BANHO 01, que já estava pronto). Precisa priorizar qual entra em produção.
- 4 stashes de **outras sessões** (`stash@{1}` a `stash@{4}` em
  `apps/sketchup-mcp`, marcados "não-meu" nos próprios nomes) — não mexi,
  não sei o conteúdo/intenção. Alguém (Felipe ou a sessão dona) precisa
  decidir se ainda valem.

## 7. Riscos

- **`Agent` tool desta sessão não carrega `interior-project-auditor`** (nem
  outros agents criados no meio da sessão) — precisa reiniciar/nova sessão
  do harness pra ele aparecer na lista. Se tentar chamar e não aparecer,
  não é bug — é esperado.
- **65 arquivos untracked ainda no working tree** de `apps/sketchup-mcp`
  (branch `develop`), em `artifacts/planta_74/furnished/kitchen_angles/` —
  são renders de iteração antigos (scratch regenerável), decisão explícita
  do Felipe de deixar de fora do commit. Se rodar `git status` e estranhar,
  é isso — não é coisa nova quebrada.
- **`git stash@{0}`** (meu, desta sessão) tem 2 arquivos tracked modificados
  (`planta_74_furnished_before_top.png` + `verdicts/...warm_compact__L0.json`)
  que bloqueavam o checkout pro merge — dei stash em vez de descartar.
  `git stash pop` recupera se algum dia precisar; não sei se é trabalho
  ativo de outra sessão ou lixo — não investiguei o conteúdo/origem.
- **Painel `:8788` não fica no ar sozinho** — precisa subir por sessão
  (`python server.py`), sem watchdog por design (lição do NOC). Se a próxima
  sessão abrir o painel e não responder, é só isso — sobe de novo.
- Testes do `.rb` (Ruby/SketchUp) não são verificáveis nesta máquina sem SU
  rodando — os fixes de geometria foram validados por: (1) teste
  determinístico Python (`Polygon.is_valid`, cobertura, z-gap), (2) render
  V-Ray real confirmando visualmente. Não há teste automatizado do
  `place_layout_skp.rb` em si.

## 8. Próximos 5 passos

1. **Corrigir o bug do LAVABO** (`tools/bathroom_layout.py:568`) — é o mais
   barato e concreto: mudar a condição de `stone=True` pra incluir a parede
   que hospeda o gabinete/espelho no lavabo, não só `box`/`ducha`. Depois
   re-renderizar e comparar.
2. **Lighting schema** (P1 do GPT): separar no schema de peças
   `general | task | accent` de `render_only_fill` — ele quer isso resolvido
   antes de decidir o destino do light slot.
3. **Decidir com o Felipe**: mergear `feat/mobiliar-bedroom-layout` (resolver
   o WARN primeiro?) e o que fazer com as `chore/noc-nf-*` (deletar?).
4. **MEP scaffolding** — campos `VERIFIED/UNVERIFIED/CONFLICT` no schema,
   sem inventar hidráulica real; BANHO 01 continua propositalmente
   `execution_status: FAIL` até isso existir.
5. **Escolher 1 dos 7 cômodos** (fora BANHO 01) pra levar a diretriz do
   `interior-designer` até o primeiro render de produção — sugestão: SUITE
   01 ou COZINHA (já tem geometria congelada e diretriz completa).

## 9. Comandos úteis

```bash
# confirmar estado do repo
cd /e/Claude/apps/sketchup-mcp && git status --short && git log --oneline -5

# rodar a suite completa
"/e/Claude/apps/sketchup-mcp/.venv/Scripts/python.exe" -m pytest tests/ -q

# só os testes do banho (28+6 = 34)
"/e/Claude/apps/sketchup-mcp/.venv/Scripts/python.exe" -m pytest tests/test_bathrooms_style.py -q

# subir o painel local
cd /e/Claude/apps/sketchup-mcp/ops/estudio-front && \
  "/e/Claude/apps/sketchup-mcp/.venv/Scripts/python.exe" server.py
# depois abrir http://127.0.0.1:8788

# oráculo GPT-Docker (verificar antes de perguntar)
curl -s -m 8 http://127.0.0.1:8899/health

# recuperar meu stash de hoje se precisar (2 arquivos, ver §7)
git -C /e/Claude/apps/sketchup-mcp stash show -p stash@{0}
```

## 10. O que NÃO fazer

- **Não mergear `feat/mobiliar-bedroom-layout` sem resolver o scale-leak/WARN
  primeiro** — é decisão de produto pendente, não hygiene.
- **Não ressuscitar as `chore/noc-nf-*`** — sistema removido a pedido
  explícito do Felipe (2026-07-24). Ver `LESSONS-NOC.md`.
- **Não mexer nos stashes `stash@{1}` a `stash@{4}`** de `apps/sketchup-mcp`
  sem confirmar de quem são — nomes dizem "não-meu"/"WIP" de outras sessões.
- **Não commitar os 65 PNGs untracked** de `kitchen_angles/` sem necessidade
  — é scratch regenerável, decisão já tomada de deixar fora.
- **Não autojulgar veredito visual** dos próximos renders — isso é do
  Felipe/GPT via Chrome, nunca auto-declarado.
- **Não editar geometria do light slot** sem primeiro resolver
  lighting/MEP/wet-zone — é a ordem que o próprio GPT recomendou.
- **Não commitar o `.rb` sem rodar a suite Python primeiro** — é o único
  jeito de pegar regressão nesta máquina (sem SketchUp headless disponível
  pra CI local).

## 11. Checkpoint p/ próxima sessão

Parei logo depois de `git push origin develop` (confirmado com sucesso) +
rodar a suite completa (1262/19/6, igual ao baseline). O painel `:8788`
ainda pode estar de pé nesta máquina (subiu via processo solto, não
sobrevive a reboot). Primeiro movimento ao retomar: `git -C
apps/sketchup-mcp status --short` pra confirmar que a working tree ainda
está do jeito descrito em §6/§7 (nada novo quebrado), e decidir entre os
Próximos 5 Passos (§8) — o mais barato é o #1 (bug do LAVABO). Sinal de que
está tudo de pé: `git log --oneline -1` mostra `4a70232` ou mais recente na
`develop`, e `origin/develop` bate com o local.
