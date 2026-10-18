# GPT CHANGE GATE — Protocolo obrigatório por alteração

## Regra absoluta

Toda alteração que mude a imagem precisa de duas consultas ao GPT:

1. aprovação antes da execução;
2. julgamento depois da execução.

Sem as duas respostas registradas, a alteração é inválida e não pode entrar no baseline nem no commit final.

## Estado do ciclo

```text
PROPOSED
  -> waiting_gpt_answer
  -> APPROVE_CHANGE | REVISE_CHANGE | REJECT_CHANGE
  -> IMPLEMENTING (somente se APPROVE_CHANGE)
  -> waiting_gpt_result
  -> IMPROVED | SAME | WORSE
  -> KEPT (somente IMPROVED) | REVERTED (SAME/WORSE)
  -> CLOSED
```

O próximo ciclo só pode começar quando o anterior estiver `CLOSED`.

## Antes da mudança

Criar `change_request.json` com:

- `alteration_id`;
- versão atual;
- defeito dominante;
- exatamente uma mudança proposta;
- valores antes/depois pretendidos;
- elementos congelados;
- câmeras de validação;
- evidências atuais.

Enviar ao GPT:

> Estou prestes a executar UMA alteração. A hipótese é: `<mudança única>`. Ela ataca o defeito dominante ou estou mexendo no lugar errado? Responda pelo contrato. Não aprove lote de mudanças.

Apenas `APPROVE_CHANGE` libera edição.

## Depois da mudança

Renderizar com câmera, crop, luz e material idênticos ao before. Criar `before_after.png` e enviar:

> Julgue somente esta alteração. O resultado ficou claramente menos Minecraft e mais premium? Responda `IMPROVED`, `SAME` ou `WORSE`. Não avalie mudanças que não foram feitas.

- `IMPROVED`: manter e fechar ciclo;
- `SAME`: reverter;
- `WORSE`: reverter imediatamente.

## Proibições

- não agrupar mudanças;
- não alterar a câmera para favorecer o after;
- não trocar iluminação/material durante uma alteração geométrica;
- não esconder defeito com enquadramento;
- não editar enquanto `waiting_gpt_answer`;
- não iniciar novo ciclo antes de fechar o anterior;
- não autoatribuir `IMPROVED`.

## Auditoria final

O relatório final deve conter uma tabela com:

```text
alteration_id | hipótese | pre_verdict | post_verdict | kept/reverted | evidências
```

Qualquer linha sem `pre_verdict` e `post_verdict` torna o Definition of Done falso.
