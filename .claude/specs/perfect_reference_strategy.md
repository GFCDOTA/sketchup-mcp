# Perfect reference strategy — sketchup-mcp

## Problema

Não existe ainda uma "planta perfeita de referência" automática.
O PDF é a fonte inicial — mas pode ser:

- Raster (sem geometria vetorial extraível)
- Mal escaneado (skew, noise)
- Incompleto (medidas omitidas, ambientes não-rotulados)
- Sem escala universal (depende do plotter de origem)

E mesmo um PDF vetorial bom não codifica todas as decisões
arquitetônicas óbvias pra um humano (que é parede estrutural vs
peitoril, onde a porta abre, qual o ambient name).

## Princípio raiz

**Não inventar paredes onde o PDF não mostra geometria.** (Hard
Rule #1.) Honestidade > completude.

## Tiers de verdade

| Tier | Origem | Confiança | Como usar |
|---|---|---|---|
| **A. PDF vetorial extraído** | filled paths do `pypdfium2` | Alta — geometria objetiva | Fonte primária de walls. Anchor de escala. |
| **B. Anotação humana** | overlay PNG / JSON anotado por humano | Alta — mas custo manual | Resolução de ambiguidade (semantic zones, kind_v5 routing) |
| **C. Inferência do agente** | heurística (junction extension, soft barriers) | Média — precisa ser auditada | Permitida se reversível e marcada em `geometry_origin` |
| **D. Hipótese experimental** | feature nova em micro-fixture | Baixa — não vai pra produção sem prova | Só em quadrado-style fixture, com teste cobrindo |

**Regra**: nunca usar tier D direto na planta real. Subir o tier
via prova (teste verde + side-by-side + review humano).

## "Truth card" por ambient / feature

Pra cada decisão não-trivial sobre o que o PDF mostra, criar
truth card sob `specs/truth_cards/<ambient_or_feature>.md`:

```
# Truth card — <ambient name>

## Evidência no PDF
- Page / region:
- Vetor presente?: yes / no
- Medidas legíveis?: yes / no

## Geometria esperada
- Walls esperadas (IDs ou bounds):
- Openings esperadas:
- Cell esperado?: yes / no

## Dúvidas / ambiguidade
-

## Status
draft / confirmed / superseded

## Artefatos relacionados
- consensus excerpt:
- truth_overlay.png:
- decisão final commitada em:
```

Truth cards são versionadas — quando a verdade muda, abrir nova
card e marcar antiga como `superseded`.

## Bootstrap incremental

Sequência sugerida pra cada planta nova:

1. **Extract**: rodar `build_vector_consensus.py` (ou equivalente
   atual) no PDF
2. **Audit**: revisar `observed_model.json` contra PDF — listar
   discrepâncias
3. **Annotate**: criar overlay PNG anotado se PDF for raster ou
   ambíguo
4. **Reconcile**: gerar consensus combinando A + B
5. **Prove**: gerar SKP, render side-by-side, abrir PR
6. **Promote**: artifact + provenance + truth cards relacionadas

## TODO — validar contra repo

- [ ] Confirmar quais ferramentas de extração existem hoje no
      repo (PR #184 podou bastante coisa)
- [ ] Criar pasta `specs/truth_cards/` se essa estrutura for
      adotada
- [ ] Cobrir caso peitoril/grade — qual tier (B humano ou C
      heurística) é o usado hoje
