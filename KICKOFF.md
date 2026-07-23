# KICKOFF — próxima sessão sketchup-mcp

> Gerado 2026-07-23 junto com o `HANDOFF.md` (leia-o primeiro; este arquivo é o
> plano de ataque, aquele é o estado). Apagar/atualizar quando a missão landar.

## Contexto em 5 linhas
1. A campanha de baselines da planta_74 mobiliada voltou **9× WORSE** (sem comentário).
2. A resposta está PRONTA mas **não commitada**: 3 fixes na working tree da branch
   local `fix/planta74-furnished-fidelity` (tapete clipado ao cell · guard wet-room
   · piso neutro `FURNISH_NEUTRAL_FLOOR`).
3. Suíte verde COM os fixes: **1381 passed, 9 skipped** (2026-07-23).
4. `feat/fp035-retrieval-eval` (golden-set + RRF) está **pushada sem PR** — órfã.
5. Furnished regerado (07-15 23:01) **sem veredito visual**; `.skp` encolheu
   1.4MB→315KB (⚠️ conferir sofá-perfil antes de promover).

## Missão da sessão (nesta ordem)
1. **Commit + push** dos 3 fixes (3 commits, uma intenção cada):
   ```bash
   cd E:/Claude/apps/sketchup-mcp
   git status -sb   # conferir que a working tree == HANDOFF §3
   git add tools/bedroom_designer.py   && git commit -m "fix(furnish): clipa tapete ao cell real (vazava p/ comodo vizinho)"
   git add tools/furnish_apartment.py  && git commit -m "fix(furnish): guard wet-room loga movel fora da louca em banheiro"
   git add tools/place_layout_skp.rb   && git commit -m "feat(furnish): piso neutro no mobiliado (gate FURNISH_NEUTRAL_FLOOR)"
   git push -u origin fix/planta74-furnished-fidelity
   ```
2. **Veredito visual** do furnished novo (mudou APARÊNCIA → evidência além do diff):
   push dos PNGs after → URL raw.githubusercontent → GPT-Docker `:8899` (frase
   "se não abrir escreva IMAGE_NOT_VIEWED"). IMPROVED = segue; SAME/WORSE =
   iterar/reverter. **Não autojulgar.**
3. **PR → develop** (URL de compare; PAT sem `Pull requests:write`):
   `.../compare/develop...fix/planta74-furnished-fidelity` — landar, não deixar aberta.
4. **Landar `feat/fp035-retrieval-eval`** do mesmo jeito:
   `.../compare/develop...feat/fp035-retrieval-eval`.
5. Com folga: pedir ao GPT a **crítica apontada dos 9 WORSE** (piso? luz?
   móveis-caixa?) e converter em itens da fila `next_actions.md`.

## Definition of done
- [ ] 2 PRs mergeadas em `develop`; zero branch órfã pushada.
- [ ] Veredito visual gravado (verdict json) pro furnished pós-fix.
- [ ] `develop` == `origin/develop`, suíte verde, working tree limpa (ou só
      saída nova do loop autônomo, triada conscientemente).

## Guard-rails (resumo do HANDOFF §10)
- Veredito visual é do Felipe/GPT — nunca auto.
- Não enterrar `planta_74_furnished_with_sofa_premium.skp` (1.4MB) — é a
  referência de sofá-perfil.
- Não rebuild do shell; não push em `main`; fixtures intocáveis; sem headless
  em dev local; não deletar branches visdrain.
- `:8765` vivo = loop autônomo pode escrever em `.ai_bridge/` — checar antes de triar.

## Gate de entrada — re-rodar, não confiar no histórico
Evidência do handoff é de 2026-07-23; re-verifique ANTES do passo 1 da missão.
**Não prossiga sem tudo verde:**
```bash
cd E:/Claude/apps/sketchup-mcp && git status -sb && curl -s http://localhost:8765/health | head -c 200
.venv/Scripts/python.exe -m pytest tests/ -q            # esperado: 1381 passed, 9 skipped (exit 0)
.venv/Scripts/python.exe -m tools.door_swing_audit      # esperado: PASS 7/7 (exit 0)
```
Se a working tree divergir do `HANDOFF.md` §3 (loop autônomo escreve em
`.ai_bridge/`), reconciliar primeiro; se a suíte quebrar, consertar antes de
commitar qualquer fix.
