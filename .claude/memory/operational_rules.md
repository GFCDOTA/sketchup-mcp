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

**Natural slice complete IS a valid stop.** Concluir o escopo
declarado de uma branch / PR / ciclo é parada válida. Não criar
ciclo novo de governance / docs / refactor / hygiene só porque
não tem blocker RED.

**Continuar automaticamente** somente se houver próximo item de
ROI claro ligado a um destes:

1. **SKP fidelity** — gerar / refinar `.skp` em `artifacts/<plant>/`
2. **Artifact quality** — render side-by-side, report, sidecar
   inconsistente
3. **Failing gate** — teste vermelho, gate self-check FAIL,
   contract suite quebrada
4. **Active PR cleanup** — PR aberta esperando merge / review
   response / fix
5. **User-requested milestone** — item explícito do humano OU
   linha em `plans/next_actions.md`

Sem encaixe em 1–5 = parar e reportar. Não inventar próxima
auditoria, próxima doc, próxima limpeza.

**Verbal override (`NAO PARE` mode):** se o humano disser
explicitamente "continue / não pare / autônomo / nao pare", a
porta abre pra escolher próximo item mesmo se ele não encaixar
trivialmente em 1–5 — desde que ainda passe filtro de produto-ROI
(reduzir fila de PRs, fechar trabalho parado, etc. CONTA;
inventar governance doc não conta).

**Parar imediatamente** nos critérios RED da seção acima.

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
