# Operational rules — sketchup-mcp

Regras permanentes pra qualquer agente operando neste repo. Não
versionar mudança casual aqui — modificar só via PR explícita.

## Autonomia com limites (GREEN / YELLOW / RED)

**GREEN — executar direto, sem perguntar.** Mudança pequena,
reversível, testada localmente. Ex.: rename de variável local,
correção de typo, ajuste de teste verde, doc fix, criação de
fixture nova com `tests/test_*.py` cobrindo.

**YELLOW — executar mas registrar / pedir double-check assíncrono.**
Mudança que toca contrato, mas tem teste cobrindo. Ex.: nova
opening kind, ajuste em `kind_v5` routing, novo gate em
`geometry_report.json`. Commit + push, abrir PR, marcar pra
review humano antes de merge.

**RED — parar e perguntar.** Critérios reais de bloqueio:

1. **Credenciais expostas** ou risco de vazamento
2. **Ação destrutiva irreversível** (force push em branch
   compartilhada, drop de fixture canônica, delete de artifact
   versionado, reset --hard em commit não-local)
3. **Mudança de objetivo** declarada vs escopo da branch atual
4. **Conflito de merge não-resolvível** sem decisão de produto
5. **Merge vermelho** em check obrigatório (testes, gate)
6. **Falta de artefato obrigatório** que o spec exige (ex.: gerar
   `.skp` "ok" sem render + report)
7. **Limite operacional** (contexto esgotado, ferramentas indisponíveis)

## Continuar automaticamente vs parar

- **DONE IS NOT STOP**: escopo concluído não é fim de sessão.
  Registrar em `.ai_bridge/` (quando aplicável), atualizar
  `plans/next_actions.md`, escolher próximo item de ROI.
- **NAO PARE mode**: gatilho verbal do humano ("continue", "não
  pare", "autônomo") = aplicar DONE-IS-NOT-STOP imediatamente.
  Reduzir fila de PRs abertas conta como avanço; não tratar fila
  como bloqueador.
- **Parar** somente nos critérios RED acima.

## Consulta a LLM externo

Em bifurcação genuína (não trivialidade técnica resolvível por
leitura de código):

1. **Preferir LLM local** via Ollama (`deepseek-r1:14b` pra
   decisão, `qwen2.5-coder:14b` pra código). Setup em memory
   global: `reference_local_llm_setup.md`.
2. **Fallback ChatGPT bridge** em `localhost:8765` (`POST /ask`).
3. **Decidir + executar** se LLM local e Claude convergem. Só
   perguntar ao humano se for ambiguidade de escopo real.
4. Dar contexto estruturado: excerto dos arquivos + coords +
   decisão específica. LLM local não vê a sessão.

## Confirmação humana

- **Default** pra mudança pequena/reversível/testada: NÃO pedir.
- **Default** pra autonomia: total + carta branca + bypass (regra
  global do humano).
- Pedir somente nos critérios RED.

## Verbosidade da resposta

- Texto pro humano é update relevante, não narração interna.
- Final de turno: 1–2 frases. O que mudou + próximo passo.
- Em código: comentário só pra "porquê" não-óbvio. Nunca explicar
  o quê (o nome já explica).
