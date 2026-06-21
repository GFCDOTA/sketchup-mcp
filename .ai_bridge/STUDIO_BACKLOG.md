# STUDIO BACKLOG — trabalho autônomo (2026-06-21)

> Backlog REAL (sem enchimento) do INTERIOR STUDIO + cozinha planta_74. O Claude ataca as **[A]**
> sozinho e commita; **[V]** = precisa veredito visual do Felipe/GPT; **[D]** = precisa decisão do Felipe.
> Status: ✅ feito · ▶ em andamento · ⬜ a fazer. Atacando de cima pra baixo por prioridade.
>
> **Feito 2026-06-21 (autônomo, carta branca):** P0-1,2,3,4,7 · P1-8,12 · P2-19,20,21 · P3-23,24,26 · P5-15 —
> commits `e4bc8ec`·`df60787`·`6a17d4d`·`4ea7aaf`·`d4da4fd`. O **ciclo alimenta o Arquiteto** sozinho (P0-7);
> em **dúvida de design, consulto os locais** (Arquiteto/consenso) no lugar do Felipe e alimento o resultado
> tagueado `[REC LOCAL · validar]`. ⚠️ Achado: o DeepSeek local pode **contradizer** o aprendizado do Consult
> GPT em decisão crítica (recomendou coifa "escondida" vs o anti-pattern `black_blob_appliance`) → decisão
> crítica/visual continua sendo GPT+Felipe; local serve pra soft/rascunho.

## P0 — Inteligência dos agentes (o que tava "burro"/alucinando)
1. ✅ [A] Endurecer o prompt do ciclo (PT, SÓ cozinha, sem inventar solda/código/emergência)
2. ✅ [A] Arquiteto do ciclo usa `_architect_priming()` (DNA + anti-patterns), não só architect.md
3. ✅ [A] Subir o cap de resposta do `_ask` 600 → 1500 chars (parava de cortar)
4. ⬜ [A] Roteamento: pergunta de design no chat do PM → nudge "isso é pro Arquiteto →"
5. ⬜ [A] Regra de consenso p/ decisão visual crítica (≥2 modelos OU justificativa) — MT-UI-005
6. ⬜ [A] `model_usage` por AGENTE (hoje é só o total) + warning de concentração
7. ⬜ [A] Ciclo: ao terminar, oferecer "→ validar no Consult GPT" automático (1 clique)

## P1 — Dashboard: clareza / despoluir
8. ✅ [A] Cards recolhíveis + 1 botão "✓ aprender" unificado
9. ⬜ [D] Apagar de vez o card "Alimentar o Arquiteto" (redundante com "✓ aprender")
10. ⬜ [A] Form "gerar pergunta" do Consult vira sub-bloco colapsável "▸ precisa perguntar?"
11. ⬜ [A] Painel "Ciclo atual": os 3 passos (PM→Lead→Arq) numa timeline só (MT-UI-002)
12. ⬜ [A] "Ciclos recentes": cortar a diretriz + expandir on click (menos parede de texto)
13. ⬜ [A] Nav do header refletir os cards reais (+ Ciclo, + Consult, − Curadoria se colapsado)
14. ⬜ [A] Legenda de 1 linha em cada card (pra que serve)
15. ⬜ [A] Remover JS morto (`consultSaveAns`/`consultIngest` agora sem uso)
16. ⬜ [A] Padronizar headers/labels/status pills (largura fixa, grid) — MT-UI-006

## P2 — Performance (página travando/piscando)
17. ⬜ [A] Não reconstruir o `#root` inteiro a cada poll — diff/atualizar só o card que mudou
18. ⬜ [A] Não montar o BODY de cards colapsados (economiza render de galeria/imagens)
19. ⬜ [A] `loading=lazy` nas imagens (galeria/curadoria/inbox)
20. ⬜ [A] Pausar/afrouxar o poll quando a aba está em background (visibilitychange)
21. ⬜ [A] Cache curto do `reference_db` no `_state` (não reabrir SQLite a cada 10s)
22. ⬜ [A] `studio_log.tail` ler só o fim do arquivo (não o arquivo todo) quando crescer

## P3 — Consult bridge: robustez
23. ⬜ [A] Testes unit do pacote `consult_gpt_bridge` (contracts/store/parser/ingest) commitados
24. ⬜ [A] Parser: limpar backtick solto no `what` dos anti_patterns (`black_blob_appliance\`:`)
25. ⬜ [A] Parser: cobrir mais variações de header do GPT (sem "##", com emoji, etc.)
26. ⬜ [A] `.gitignore` p/ runtime data (inbox/outbox/answered/ingested/failed/logs/cycles.jsonl)
27. ⬜ [A] Dedup de anti_patterns por `id` também (não só por `what`)
28. ⬜ [A] `/api/consult/learn`: mostrar no UI o resumo do que aprendeu (regras/anti/MT)

## P4 — Cozinha planta_74 (o objetivo real — prep [A], render [V])
29. ⬜ [A] Criar `interior/materials/kc_inox_dark.json` (do answer MT-09: diffuse/reflect faixa segura)
30. ⬜ [A] Criar o style pack `black_wood_gold_industrial_boutique.json` (scene_composer / SALA)
31. ⬜ [A] Gate determinístico "preto-sobre-preto" (a nova regra do DNA: separação por luz/sombra/borda)
32. ⬜ [A] Token `dark_stainless_appliance` já cobre coifa? senão refinar com o aprendizado MT-09
33. ⬜ [V] MT-09: render da coifa em 3 variações (A_dark_hidden / B_dark_readable / C_graphite_edge)
34. ⬜ [V] Render hero baseline do GOLDEN_SAMPLE_004 atual (pra comparar)
35. ⬜ [D] Revisar/refazer o `KITCHEN_TO_100` com o Felipe (priorizar o que importa de verdade)
36. ⬜ [A] Gate "daylight_reflection" no eletro escuro (não virar buraco morto)

## P5 — Limpeza / docs / histórico
37. ⬜ [A] Atualizar `STUDIO_HANDOFF.md` com o estado novo (modo limpo, learn unificado)
38. ⬜ [A] README do consult bridge: marcar MVP fechado + o fluxo do "✓ aprender"
39. ⬜ [A] Atualizar a memória `project_interior_studio` com o estado atual
40. ⬜ [A] Remover constantes/CSS órfãos acumulados no studio_dashboard.py

> A partir daqui (P6+) entram as microtarefas mais granulares de UI/perf/cozinha conforme eu for
> abrindo cada uma — este arquivo é vivo (cada item vira ✅ com o commit ao lado). O objetivo não é
> "100 por 100", é **avançar de verdade** sem te perguntar a cada passo.
