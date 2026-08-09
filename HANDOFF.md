# HANDOFF — fidelidade da planta_74 mobiliada (resposta ao 9× WORSE)

> Fio da meada entre sessões. Seção vazia = pergunta aberta pra próxima
> sessão, não "N/A" silencioso. Gerado pela skill `/handoff`.
> Substitui o snapshot de 2026-07-15 (histórico relevante preservado abaixo).

- **Data / sessão:** 2026-07-23 · sessão f663b0e5 (snapshot + handoff/kickoff; sem dev novo nesta sessão)
- **Repo / app:** `apps/sketchup-mcp`
- **Status geral:** YELLOW — dois trens prontos e NÃO landados:
  (a) 3 fixes de fidelidade do furnished **sem commit** em branch local sem remote;
  (b) `feat/fp035-retrieval-eval` **pushada com 2 commits e sem PR** (viola "nunca
  deixar branch órfã"). Campanha de baseline voltou **9× WORSE** sem comentário.

> **ADENDO 2 (2026-07-24) — NOC + DASHBOARDS REMOVIDOS a pedido do Felipe:**
> `:8765`/watchdogs/atuador/feeder/curation_review/studio_dashboard/vitrine/BFF
> apagados (develop `f31f071`, -16k linhas; suíte pós-remoção **1217/0/5**).
> Aprendizados consolidados em `E:\Claude\LESSONS-NOC.md`. Oráculo (decisão E
> visual) = GPT-Docker `:8899` (`ask_gpt_gate` re-apontado). RAG/write-back
> INTACTOS (embed segue default do gerador); consulta via CLI ou Qdrant `:6333`.
> Referências a `:8765`/card :8782 nos adendos ABAIXO estão superadas.

> **ADENDO 2026-07-23 (mesma sessão, mais tarde) — RAG LIGADO NO RECALL:**
> a pendência (b) foi RESOLVIDA e foi além: develop recebeu `4d4df7f` (fusão RRF
> + retrieval_eval; eval real: MRR 0.90→1.00, nDCG@6 0.808→0.839), `6317500`
> (fix: o filtro token da fusão escondia os verdicts do Felipe do recall —
> regressão pega pelo teste infra-gated, red→green no dia) e `58cf40f` (card
> **🧠 Memória vetorial** no :8782 — status do banco, busca semântica,
> comparador faceted×embed, alerta de verdict sem sinal). Tree principal já tem
> tudo via merge `dd9112e`; suíte AQUI: **1410 passed, 5 skipped** (infra viva);
> Qdrant reindexado `--rebuild` (corpus `006ff80f9a96`, 218 chunks). Falta SÓ o
> flip `RAG_BACKEND=embed` do gerador (visual-gated) — ver KICKOFF §6. Gotcha
> novo: reindex NUNCA de worktree (clobbera o Qdrant compartilhado). As seções
> abaixo (§2/§5/§6) descrevem o estado da MANHÃ; este adendo prevalece.

## 1. Objetivo atual
Subir a **nota visual da planta_74 mobiliada** (a nota do GPT/Felipe é o
termômetro do projeto). A campanha de baselines de 2026-07-12 voltou **9× WORSE**
(3 perfis × níveis de luz + 1 industrial, todos sem comentário). A linha atual
(`fix/planta74-furnished-fidelity`, criada 2026-07-15 22:29) responde com 3 fixes
de fidelidade/aparência no pipeline de furnish. ROI = veredito IMPROVED no
furnished real + 2 PRs landadas.

## 2. Branch atual
- **Branch:** `fix/planta74-furnished-fidelity` · **base:** `origin/develop`
- **Último commit:** `a35ece6` — `chore(evidence): publish planta_74__baseline__warm_compact__L0.png…` (== tip do develop; a branch ainda não tem commit próprio)
- **Ahead/behind:** 0/0 vs `origin/develop`. **Branch é local-only** (sem remote
  homônimo; upstream aponta pra `origin/develop`). Todo o trabalho está na working tree.
- **Segunda branch em voo:** `feat/fp035-retrieval-eval` @ `205c200` — 2 commits
  únicos (`4bb3d7f` golden-set + retrieval_eval harness recall@k/MRR/nDCG;
  `205c200` RRF "ligar o embed"), **pushada pro origin, sem PR aberta**.
- **Worktrees:** só o tree principal (1). Sem sessão paralela.
- Há ~9 branches locais `chore/noc-nf-*` (visdrain 07-07 e 07-12) — não deletar
  sem drenar o corpus único (memória).

## 3. Arquivos alterados (working tree, NÃO commitado)
Código (o miolo dos 3 fixes):
```
 M tools/bedroom_designer.py   # tapete SEMPRE clipado ao cell real (vazava p/ BANHO 02 via buffer)
 M tools/furnish_apartment.py  # GUARD wet-room: banheiro só aceita kinds de louça (WARN, não aborta)
 M tools/place_layout_skp.rb   # PISO NEUTRO no furnished (gate FURNISH_NEUTRAL_FLOOR, default ON)
```
Artefatos regerados 2026-07-15 23:01 (rodada de furnish com os fixes):
```
 M artifacts/planta_74/furnished/planta_74_furnished.skp        # ⚠️ 1.408.293 → 315.684 bytes
 M artifacts/planta_74/furnished/planta_74_furnished_after_{iso,top}.png
 M artifacts/planta_74/furnished/planta_74_furnished_before_top.png (sem mudança de conteúdo)
```
Saída do loop autônomo / campanha (aguardando triagem):
```
 M references/felipe/verdicts/planta_74__baseline__warm_compact__L0.json  (re-julgado: IMPROVED→WORSE, cycle hv_4d09cb565bef)
?? references/felipe/verdicts/planta_74__baseline__black_wood_gold__L{0,1,2}.json  (WORSE)
?? references/felipe/verdicts/planta_74__baseline__dark_walnut__L{0,1}.json        (WORSE)
?? references/felipe/verdicts/planta_74__baseline__warm_compact__L{1,2}.json       (WORSE)
?? references/felipe/verdicts/planta_74__industrial__warm_compact__L0.json         (WORSE)
?? .ai_bridge/proposals/rejected/gap_completude_r00{0,4,5}.json + gap_nomenclatura_r004.json
 M .ai_bridge/noc/queue.jsonl · M .claude/plans/active_work.md (snapshot)
```

## 4. Decisões tomadas
- **Nesta sessão (2026-07-23):** nenhuma de engenharia — snapshot + HANDOFF + KICKOFF.
- **Herdadas de 2026-07-15 (código na working tree, ainda sem veredito):**
  1. Tapete clipado **sempre ao cell real**, não ao buffer com folga — o canto do
     tapete da SUÍTE 02 vazava pro BANHO 02.
  2. Guard anti-regressão wet-room: móvel de quarto/sala num banheiro **loga WARN**
     (não aborta) — pega regressão futura de roteamento.
  3. Furnished ganha **piso neutro** (repinta faces dos `Floor_Group` com material
     único `furnished_floor` 214/208/198): o chão color-coded do shell (rosa da
     suíte etc.) é útil pra fidelidade mas feio no deliverable mobiliado — hipótese
     de causa-raiz do 9× WORSE. Só aparência do furnished; shell canônico intocado;
     `FURNISH_NEUTRAL_FLOOR=0` preserva o comportamento antigo.
- **Herdada de 2026-07-15 (FP-035):** golden-set/eval PRIMEIRO, depois ligar o
  embed via RRF — exatamente o roadmap da auditoria RAG; implementado e pushado
  em `feat/fp035-retrieval-eval`, falta landar.

## 5. Testes rodados + evidências
- **Suíte:** `.venv/Scripts/python.exe -m pytest tests/ -q` → **1381 passed,
  9 skipped em 94.9s** (rodada NESTA sessão, 2026-07-23, com os 3 fixes na
  working tree). Skips = fixtures quadrado/aperture não construídas (esperado).
- **Gate determinístico:** furnish log de 2026-07-15 23:01 → `placed 194/194
  placeholders`, `shell travado: 25 grupos`. Nenhum gate visual determinístico rodado.
- **Evidência humana:** `artifacts/planta_74/furnished/planta_74_furnished_after_{iso,top}.png`
  (23:01) — gerados, **ainda não julgados**.
- **Veredito visual:** **PENDENTE** pros 3 fixes — NÃO autojulgar. Verdicts
  gravados da campanha: **9× WORSE** (todos com `felipe_comment` vazio — não há
  crítica pra guiar; ver Próximos passos).

## 6. Pendências
- **Commitar + pushar os 3 fixes** em `fix/planta74-furnished-fidelity` (hoje o
  trabalho só existe na working tree desta máquina). (falta fazer)
- **Veredito visual do novo furnished** (GPT-Docker :8899 / raw.githubusercontent)
  antes de PR — mudança de APARÊNCIA exige evidência além do diff. (falta fazer)
- **Landar `feat/fp035-retrieval-eval`** — PR por URL de compare (PAT sem
  `Pull requests:write`). (falta fazer)
- **Crítica dos 9 WORSE:** todos sem comentário → pedir ao GPT crítica apontada
  (o que exatamente está ruim: piso? luz? móveis-caixa?) pra virar roadmap. (falta fazer)
- **Triagem dos verdicts/propostas untracked:** commitar ou deixar o loop
  consumir — está no limbo desde 07-12. (decisão desta ou da próxima sessão)
- Fila `next_actions.md` (review clínico 07-11): janelas com peitoril/verga
  medidos do PDF + eixo Z nos gates. (backlog)

## 7. Riscos
- **`planta_74_furnished.skp` encolheu 4.5×** (1.4MB → 315KB). O anterior
  provavelmente era o `with_sofa_premium` (1.4MB, preservado ao lado). O novo é
  furnish de placeholders — **conferir sofá-perfil vs sofá-caixa antes de
  promover/commitar** (memória: furnish desenha PERFIS, não caixa).
- **Loop autônomo escreve nos mesmos arquivos** — `:8765` está VIVO (oracle
  claude, server_sha12 c8f0164816f3). Checar a fila antes de mexer em
  `.ai_bridge/` pra não competir com o atuador.
- **Branch local sem remote** = um `rm -rf`/crash perde os 3 fixes. Commitar cedo.
- **`.rb` builder não verificável aqui** sem SketchUp não-headless — contrato
  texto + flag "confirma em build SU"; nunca autodeclarar geometria.
- Branches `chore/noc-nf-*` visdrain têm corpus único — não deletar sem drenar.

## 8. Próximos 5 passos
1. Confirmar suíte verde (se a linha em §5 ficou aberta, rodar `pytest tests/ -q`)
   e **commitar os 3 fixes** em commits separados por intenção
   (`fix(furnish): clipa tapete ao cell` · `fix(furnish): guard wet-room` ·
   `feat(furnish): piso neutro FURNISH_NEUTRAL_FLOOR`) + `git push -u origin
   fix/planta74-furnished-fidelity`.
2. Gerar evidência visual before/after do furnished e **rotear pro veredito**
   (push PNG → URL raw.githubusercontent → GPT-Docker :8899). IMPROVED = segue;
   SAME/WORSE = reverter/iterar (gate de regressão visual).
3. **PR `fix/planta74-furnished-fidelity` → develop** via URL de compare; landar.
4. **PR `feat/fp035-retrieval-eval` → develop** via URL de compare; landar
   (nunca deixar branch pushada órfã).
5. Colher do GPT a **crítica detalhada dos 9 WORSE** e converter em
   regras/gates/fila — o comentário vazio de hoje não guia nada.

## 9. Comandos úteis
```bash
cd E:/Claude/apps/sketchup-mcp
git status -sb && git worktree list && git log --oneline -8

# suíte + gates
.venv/Scripts/python.exe -m pytest tests/ -q          # ~1319 verde esperado
.venv/Scripts/python.exe -m tools.door_swing_audit    # PASS 7/7 esperado

# cockpit :8765 (VIVO em 2026-07-23; subir: Desktop SUBIR-NOC.cmd)
curl -s http://localhost:8765/health

# oráculo visual (GPT-Docker)
curl -s http://127.0.0.1:8899/health

# PRs por URL de compare (PAT sem Pull-requests:write)
# https://github.com/<owner>/sketchup-mcp/compare/develop...fix/planta74-furnished-fidelity
# https://github.com/<owner>/sketchup-mcp/compare/develop...feat/fp035-retrieval-eval

# verdicts da campanha (9× WORSE)
ls references/felipe/verdicts/planta_74__*json
```

## 10. O que NÃO fazer
- **NÃO autojulgar veredito visual** IMPROVED/SAME/WORSE — Felipe/GPT-via-Chrome
  ou GPT-Docker; autojulgamento é comprovadamente não-confiável.
- **NÃO commitar o `.skp` de 315KB por cima do baseline** sem antes comparar com
  `planta_74_furnished_with_sofa_premium.skp` (1.4MB, 07-11) — risco de enterrar
  o mobiliado bom.
- **NÃO rebuild** do shell — editar SKP in-place; nunca `entities.clear!`.
- **NÃO push direto em `main`** (Hard Rule #4); fixtures só com aprovação humana.
- **NÃO deletar** branches `chore/noc-nf-*` visdrain sem drenar; **não** rodar
  higiene sem trigger.
- **NÃO usar `--mode headless` em dev local** (só CI).

## 11. Checkpoint p/ próxima sessão
Parei com os **3 fixes de furnish prontos na working tree** (não commitados) da
branch local `fix/planta74-furnished-fidelity` @ `a35ece6` (== origin/develop), o
furnished regerado com eles (23:01 de 07-15, ainda sem veredito) e o FP-035
pushado sem PR. **Primeiro movimento:** `git status -sb` + `curl :8765/health`;
depois seguir o §8 na ordem (commit → veredito visual → 2 PRs). **Sinal de que
está tudo de pé:** working tree igual ao §3, `pytest -q` verde, `:8765` e `:8899`
respondendo. Kickoff pronto em `KICKOFF.md` (raiz do repo).

---

<details>
<summary>Histórico — snapshot 2026-07-15 (superado, contexto ainda válido)</summary>

- `develop` @ `a35ece6` == `origin/develop`; working tree suja só com saída do
  loop autônomo (verdicts + propostas + artefatos regerados de 07-12).
- Campanha de baseline 2026-07-12: 3 perfis (`warm_compact`, `dark_walnut`,
  `black_wood_gold`) × L0/L1/L2 publicados pro score; na época só
  `warm_compact__L0` tinha verdict. Hoje: todos os 9 = WORSE.
- vf_004 (2026-07-11): swing das 7 portas medido do arco do PDF, fixture emendada
  com provenance, painel votou IMPROVED.
- Pendências da época absorvidas nas seções acima (FP-035, room fidelity WARN,
  DIFF-001 DEFERRED M4).
</details>
