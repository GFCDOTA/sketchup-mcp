# HANDOFF — Estagiários do Arquiteto + Declutter do studio_dashboard

> Fio da meada entre sessões. Seção vazia = pergunta aberta, não "N/A".

- **Data / sessão:** 2026-06-23 · INTERIOR STUDIO (planta_74)
- **Repo / app:** apps/sketchup-mcp
- **Status geral:** GREEN — duas linhas commitadas, pushadas e verificadas. A
  2ª (declutter) está no 1º passe; fusões/remoções extras **aguardam aval do
  Felipe** (ele dispensou a pergunta de validação → retomar pedindo a decisão).

## 1. Objetivo atual
Duas entregas no app vivo do INTERIOR STUDIO (dashboard :8782 + workers locais):
1. **Estagiários do Arquiteto** — decompor o auditor monolítico em 6 validadores
   TEMÁTICOS do `furniture_program` (proposta de mobília do Arquiteto/LLM local),
   pra ficar legível QUAL regra cada proposta quebra. ROI: qualidade do programa
   antes de virar inventário/geometria.
2. **Declutter do dashboard** — Felipe: "muitos painéis, junta os de mesmo
   assunto, tira os sem utilidade". ROI: usabilidade do cockpit (base p/ app de
   celular — ver memória `feedback_unified_single_app_direction`).

## 2. Branch atual
- **Base:** `develop` (local @ `70e1726`).
- **Branch 1:** `feat/architect-interns` @ `872db43` — pushado (upstream
  `origin/feat/architect-interns`). Os 6 estagiários.
- **Branch 2 (HEAD):** `chore/studio-dashboard-declutter` @ `3ab4736` — pushado
  (upstream `origin/chore/studio-dashboard-declutter`). **Stacked SOBRE a branch
  1** (contém o commit dos estagiários como ancestral).
- Working tree: limpo p/ os arquivos desta sessão. Há untracked de OUTRA linha
  (vitrine/kgraph: `tools/*.html`, `grafo_server.py`, `build_kgraph.py`, etc.) —
  **NÃO commitar, não é desta sessão.**

## 3. Arquivos alterados (develop..HEAD)
```
tools/interior_studio/interns.py | 341 ++++  (NOVO — os 6 estagiários)
tools/interior_studio/auditor.py |  48 +-   (C4/C5 → interns.gaps_for_program; C1/C2/C3 mantidos)
tools/studio_dashboard.py        |  53 +-   (seção Estagiários + declutter de layout)
```
Sensível: `studio_dashboard.py` é o app vivo (:8782). Nenhuma fixture/builder/
constitution tocada. Nenhum `.skp`/render gerado.

## 4. Decisões tomadas
- **6 estagiários, 5 determinísticos + 1 LLM.** Pertencimento/Completude/
  Nomenclatura/Capacidade/Redundância = determinísticos (gate = verdade,
  idempotente, reusa `CORE_BY_ROOM`/`ROOM_EXCLUSIVE`/`normalize_program` do
  Arquiteto). Estilo = LLM-leve (qwen2.5-coder via Ollama) — único subjetivo;
  **degrada p/ no-op** se o Ollama (:11434) estiver fora (`_ollama_up()`).
- **Estagiário PROPÕE, nunca muta** — mesma filosofia do auditor antigo. Felipe
  ficou sem preferência sobre "auto-bloqueio" → mantido o padrão "propõe gap,
  você decide" (auto-bloqueio = flag futura).
- **Separação limpa Nomenclatura × Pertencimento:** Nomenclatura pega o prefixo
  literal de outro cômodo (`banheiro_*` na cozinha); Pertencimento pega o token
  semântico (cama na sala). Sem dupla-contagem.
- **Capacidade conservadora** (FILL_WARN 0.55 / FILL_FAIL 0.72) pra NÃO acusar
  banheiro mínimo legítimo (BANHO 52% não dispara; COZINHA 96% dispara).
- **Declutter passe 1 = baixo risco/reversível**, não fusão arriscada de
  template literals. Removi só 2 painéis read-only sem ação (Gráficos, Banco de
  referências). Agrupei o resto por assunto + recolhi via `DEFAULT_ORDER`/
  `DEFAULT_OPEN`. **`LAYOUT_VER` reseta o localStorage 1×** (senão o layout
  salvo no navegador do Felipe esconderia o novo default).
- **NÃO removi "Rascunho de diretriz"** (tem botão `Rodar ciclo` = função real)
  — só agrupei/recolhi.

## 5. Testes rodados + evidências
- **Estagiários (dados REAIS, 4 propostas pendentes da planta_74):**
  `./.venv/Scripts/python.exe -m tools.interior_studio.interns`
  → SUÍTE: falta `cama` · COZINHA: falta `bancada/cooktop/geladeira` + 4
  `banheiro_*` (nomenclatura) + 96% piso (capacidade) + 3 storages (redundância)
  · BANHO: falta `vaso` · SALA: PASS (zero falso-positivo). Bate com o gate
  antigo (mesmos removeria/injetaria), agora por tema.
- **Estilo (LLM):** COZINHA real → PASS; teste "sofa_rosa_pelucia/poltrona
  dourada barroca" → FAIL. Funciona e degrada offline.
- **Auditor wired:** `python -m tools.interior_studio.auditor --save`
  → `{found:6, saved:6, stale_removed:3}` (limpou os `gap_buggy_pending_*`
  antigos). **Idempotente** (2ª rodada igual).
- **ruff:** `python -m ruff check tools/interior_studio/{interns,auditor}.py`
  → All checks passed.
- **Dashboard (instância descartável :8783, DOM):** 20→18 cards na ordem
  agrupada, 9 abertos / 9 recolhidos, `sec-graf`/`sec-refs` ausentes,
  `studio_layout_ver` aplicado. Screenshot da seção Estagiários renderizando
  (subseções douradas + cards aceitar/ignorar). `import tools.studio_dashboard`
  OK.
- **Evidência humana / veredito visual:** N/A — não houve mudança de aparência
  de .skp/render; só UI de cockpit.

## 6. Pendências
- **[Espera decisão Felipe]** Confirmar/reverter as 2 remoções (Gráficos, Banco
  de referências). Ele dispensou a pergunta → repropor curto ao retomar.
- **[Espera decisão Felipe]** Fundir DE VERDADE algum cluster em card único
  (opções: Time local · GPT&Aprendizado · Referências) ou deixar só agrupado.
- **[Falta fazer]** Reiniciar o `studio_dashboard.py` da :8782 pra Felipe ver na
  tela dele (a instância viva carregou código antigo).
- **[Falta fazer]** Landar as 2 PRs (URLs no §9) — `gh pr` falha por escopo do
  PAT (só Contents:write), então PR por URL de compare.
- **[Opcional]** 7º estagiário (ergonomia/hidráulica/orçamento) = 1 função em
  `interns.py` + 1 linha no `ROSTER`.

## 7. Riscos
- **Declutter só aparece na tela do Felipe após reiniciar a :8782** + o
  `LAYOUT_VER` reset (que apaga ordem/colapso/tamanho manuais salvos 1×). É
  intencional, mas avisa.
- **Branches stacked:** a `chore/...-declutter` contém o commit dos estagiários.
  Se a PR dos estagiários mergear primeiro, a do declutter rebasa limpo em
  develop. Se for landar só o declutter, cuidado com a base.
- **Outra sessão no mesmo working tree:** há untracked vitrine/kgraph; worktrees
  `sofa-skill` e `wt-architect-rag` existem. Conferidas limpas p/
  `studio_dashboard.py`/`interior_studio/` nesta sessão, mas re-checar antes de
  editar (Hard Rule: grep refs / status antes).
- **Estilo depende do Ollama :11434** — se cair, o estagiário some (no-op), não
  quebra; só não opina.

## 8. Próximos 5 passos
1. Reiniciar a :8782 (`studio_dashboard.py --port 8782`) e abrir no Chrome pra
   Felipe ver o dashboard enxuto (menor risco, dá feedback imediato).
2. Pegar a decisão do Felipe sobre as 2 remoções + quais clusters fundir.
3. Se aprovado, fazer o passe 2 (fusão de card único do(s) cluster(s) escolhido(s))
   — verificar no :8783 (DOM) a cada fusão antes de commitar.
4. Landar `feat/architect-interns` → develop (URL §9), depois rebasar/landar o
   declutter.
5. (Se Felipe quiser) wire dos estagiários no fluxo de aprovação do Programa
   (auto-rodar a auditoria ao propor) e/ou 7º estagiário.

## 9. Comandos úteis
```
# venv canônico
E:\Claude\apps\sketchup-mcp\.venv\Scripts\python.exe

# rodar os estagiários nas propostas reais (sem estilo = rápido; --style = + LLM)
cd /e/Claude/apps/sketchup-mcp
./.venv/Scripts/python.exe -m tools.interior_studio.interns
./.venv/Scripts/python.exe -m tools.interior_studio.auditor --save     # salva gaps pending

# subir o dashboard (viva = 8782; descartável p/ teste = 8783)
./.venv/Scripts/python.exe tools/studio_dashboard.py --port 8782

# PRs (gh sem escopo → URL de compare)
# estagiários: https://github.com/GFCDOTA/sketchup-mcp/compare/develop...feat/architect-interns?expand=1
# declutter:   https://github.com/GFCDOTA/sketchup-mcp/compare/feat/architect-interns...chore/studio-dashboard-declutter?expand=1
```

## 10. O que NÃO fazer
- **Não commitar** os untracked vitrine/kgraph (`tools/*.html`, `grafo_server.py`,
  `build_kgraph.py`, `kgraph.json`, `*.cmd`) — é de outra linha.
- **Não fundir os 20 cards de uma vez às cegas** — há variáveis JS compartilhadas
  entre cards (ex.: `sec-err` usa `ebars`/`flagopts` calculados no bloco
  `sec-agents`; TDZ de `const`). Fundir = mover o `appendChild` p/ DEPOIS das
  dependências; verificar render a cada passo.
- **Não tocar a :8765** (cockpit/oráculo, frágil/off-limits) — isto é :8782.
- **Não push em main.** PR por URL (PAT só Contents:write).
- **Não autojulgar veredito visual** de render/SKP (é do Felipe/GPT-via-Chrome).

## 11. Checkpoint p/ próxima sessão
Parei logo após Felipe DISPENSAR a pergunta de validação do declutter (sem
decidir remoções/fusões). Ambas as linhas estão commitadas+pushadas; HEAD =
`chore/studio-dashboard-declutter` @ `3ab4736`. **Primeiro movimento ao
retomar:** confirmar com Felipe (a) manter/reverter Gráficos+Banco-de-refs,
(b) fundir qual cluster — e oferecer reiniciar a :8782. **Sinal de que está de
pé:** `git -C apps/sketchup-mcp status` limpo p/ os 3 arquivos; `python -m
tools.interior_studio.auditor` devolve 6 gaps temáticos.

---

## Prompt de continuação (cola numa sessão nova)
```
Contexto: workspace E:\Claude, app apps/sketchup-mcp, INTERIOR STUDIO (dashboard
:8782 + workers LLM locais). Leia o HANDOFF.md do repo primeiro.

Estado: duas branches pushadas, ambas off develop.
- feat/architect-interns @872db43 — adicionei 6 "Estagiários do Arquiteto"
  (tools/interior_studio/interns.py): validadores temáticos do furniture_program
  (pertencimento, completude, nomenclatura, capacidade, redundância + estilo via
  LLM-leve qwen). Wired no auditor.py (substituem C4/C5) e no studio_dashboard.py
  (seção "🎓 Estagiários do Arquiteto" agrupada por estagiário). 6 gaps temáticos
  nas 4 propostas reais; ruff limpo; idempotente.
- chore/studio-dashboard-declutter @3ab4736 (stacked sobre a de cima) — 1º passe
  do declutter do dashboard: 20→18 painéis, removi Gráficos e Banco-de-referências,
  agrupei por assunto (DEFAULT_ORDER) + recolhi não-líderes (DEFAULT_OPEN) +
  LAYOUT_VER reseta o localStorage 1×.

Tarefa: retomar o declutter. (1) Pergunte ao Felipe, curto, se mantém/reverte as
2 remoções e quais clusters fundir em card único (Time local / GPT&Aprendizado /
Referências). (2) Faça o passe 2 conforme a resposta, verificando no DOM de uma
instância descartável (porta 8783) a CADA fusão (cuidado com TDZ de const entre
cards — mover appendChild p/ depois das dependências). (3) Ofereça reiniciar a
:8782. (4) Não comite os untracked vitrine/kgraph. (5) Landa as PRs por URL de
compare (gh sem escopo de PR).

Regras: estagiário/auditor PROPÕE nunca muta; venv em .venv\Scripts\python.exe;
não toca :8765; não push em main; veredito visual é do Felipe/GPT.
```
