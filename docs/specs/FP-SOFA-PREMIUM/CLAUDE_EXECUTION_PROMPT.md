# Prompt mestre para o agente implementar o sofá premium

Você vai implementar a spec `FP-SOFA-PREMIUM` no repositório do projeto.

## Objetivo

Substituir o sofá atual, que parece Minecraft/caixas empilhadas, por um arquétipo procedural premium, verificável e reutilizável.

## Regras duras

1. Não altere paredes, portas, janelas ou geometria arquitetônica.
2. Não mexa no layout da sala antes de aprovar o sofá isolado.
3. Não use “mais caixas” como solução de detalhe.
4. Faça microteste canônico em cena vazia primeiro.
5. Sem `.skp`, não há progresso.
6. Commitar o `.skp` do harness e o `.skp` da planta atualizada.
7. Toda iteração precisa de `run_id`, métricas, renders e verdict.
8. Faça uma hipótese de melhoria por iteração.
9. Consulte o GPT **antes e depois de cada alteração**, mesmo quando não houver dúvida.
10. Não execute mudança visual sem `APPROVE_CHANGE`.
11. Não mantenha mudança sem verdict posterior `IMPROVED`.
12. Não faça batch de alterações; uma hipótese por ciclo.
13. Não declare PASS apenas porque os testes geométricos passaram.

## Sequência de trabalho

1. Leia a spec completa.
2. Localize o gerador atual do sofá e documente por que ele produz blockiness.
3. Crie o arquétipo `PREMIUM_LOW_PROFILE_LOUNGE`.
4. Crie o harness `sofa_premium_harness`.
5. Adicione gates G1–G10.
6. Gere a primeira versão em clay.
7. Gere contact sheet com 6 câmeras.
8. Avalie com o contrato `VISUAL_REVIEW_CONTRACT.json`.
9. Escolha apenas a mudança de maior impacto.
10. Antes de editar, crie `change_request.json` e consulte o GPT com `ALTERATION_REVIEW_CONTRACT.json`.
11. Só execute quando receber `APPROVE_CHANGE`.
12. Faça exatamente UMA alteração.
13. Gere as mesmas vistas antes/depois e consulte novamente o GPT.
14. Só mantenha a mudança se receber `IMPROVED`; reverta `SAME` ou `WORSE`.
15. Feche e registre o ciclo antes de propor a próxima alteração.
16. Repita até `blockiness_score <= 1` e demais scores >= 4.
17. Insira o sofá aprovado na sala sem mudar a arquitetura.
18. Cada ajuste de posição, material ou iluminação da integração também precisa do ciclo GPT antes/depois.
19. Revalide circulação, mesa, tapete e poltrona.
20. Gere before/after.
21. Salve os `.skp`.
22. Commitar código + artefatos + relatório final.

## Entregáveis obrigatórios

- código do novo arquétipo;
- harness executável;
- métricas JSON;
- gates JSON;
- contact sheet isolada;
- render do sofá na sala;
- comparação antes/depois;
- review_request.json;
- review_response.json;
- uma pasta `changes/<alteration_id>/` para cada alteração;
- `change_request.json` e `change_pre_response.json` de cada alteração;
- `change_result_request.json` e `change_post_response.json` de cada alteração;
- comparação visual antes/depois usando câmera idêntica;
- log provando que nenhuma alteração ficou sem revisão;
- `sofa_premium_harness.skp`;
- `planta_74_furnished_with_sofa_premium.skp`;
- relatório final com PASS/WARN/FAIL por gate.

## Pergunta obrigatória ao GPT

Anexe a contact sheet e pergunte:

> Você é um crítico exigente de mobiliário premium e modelagem procedural. Avalie este sofá sem aliviar. Ele ainda parece Minecraft, caixas empilhadas ou placeholder de SketchUp? Identifique o principal defeito de silhueta, o principal defeito de estofamento e a única mudança geométrica de maior impacto. Responda estritamente no JSON do contrato.


## Consulta obrigatória antes de CADA alteração

Antes de tocar na geometria, material, câmera, luz ou posição, envie a evidência atual e pergunte:

> Estou prestes a executar UMA alteração no sofá. A hipótese é: `<descrever uma única mudança>`. Avalie se ela ataca o defeito dominante. Responda `APPROVE_CHANGE`, `REVISE_CHANGE` ou `REJECT_CHANGE`, informe o que deve permanecer congelado e dê uma única instrução executável. Use `ALTERATION_REVIEW_CONTRACT.json`.

Sem `APPROVE_CHANGE`, marque o ciclo como `waiting_gpt_answer` e não altere nada.

## Consulta obrigatória depois de CADA alteração

Depois da mudança, envie before/after com a mesma câmera e pergunte:

> Julgue somente o efeito desta alteração. O resultado ficou claramente menos Minecraft e mais premium? Responda `IMPROVED`, `SAME` ou `WORSE`, cite a evidência visual e dê apenas uma próxima instrução.

Mantenha apenas `IMPROVED`. Reverta `SAME` e `WORSE` antes de continuar.

## Critério de parada

Pare somente quando:

- os gates determinísticos passarem;
- `blockiness_score <= 1`;
- o GPT não apontar blockiness como defeito dominante;
- todas as alterações tiverem resposta prévia e posterior registrada;
- nenhuma alteração sem `APPROVE_CHANGE` tiver sido executada;
- nenhuma alteração `SAME` ou `WORSE` tiver sido mantida;
- a nova versão for claramente `IMPROVED`;
- o sofá estiver integrado à sala sem quebrar circulação;
- os dois `.skp` estiverem salvos e commitados.
