# Reinício do servidor MCP `sketchup` (runtime_identity)

`su_status` → `runtime_identity` compara três coisas: o checkout em disco (`E:/Claude/apps/sketchup-mcp`), o commit que o **processo** do servidor carregou ao subir (`start_head`) e o hash dos arquivos Ruby da ponte. Qualquer divergência dá `BLOCKED` no perfil `INTELLIGENT_BUILD` e as ferramentas `su_*` recusam construir/mobiliar (a regra não é relaxada).

## Causas e correção
| Sintoma em `reasons` | Causa | Correção |
|---|---|---|
| `checkout <sha> != origin/develop <sha> (a frente 0, atras N)` | o checkout do MCP ficou para trás | `git -C E:/Claude/apps/sketchup-mcp fetch --prune` e, **se estiver limpo e só atrás**, `merge --ff-only origin/develop`. Nunca `reset --hard`; checkout sujo/à frente → parar e reconciliar |
| `processo carregou <a> mas o disco esta em <b>: reiniciar o servidor` | o processo Python do MCP é anterior ao `fast-forward` | reiniciar o servidor MCP: no app Claude, reconectar o servidor `sketchup` (ou reiniciar a sessão); depois `su_status` |
| hash de arquivo `.rb` da ponte diferente | ponte Ruby editada depois de o servidor subir | reiniciar o servidor e conferir de novo |

## Verificação
`su_status` deve devolver `runtime_identity.status == "OK"`, `process.stale == false`, `code.ahead == code.behind == 0`, `dirty == false`.

## Limites
Um agente não consegue reiniciar o próprio servidor MCP: a reconexão é do app/usuário. Sem o reinício, use os scripts do repo (ex.: `artifacts/review/fp056/p6/run_p6.py`), que não passam pelo MCP e registram commit, PIDs e versão no `summary.json`.
