# Stopped work — sketchup-mcp

PRs / branches pausadas ou encerradas, com motivo e condição de
retomada (se aplicável).

## Formato

```
## <branch-or-PR-ref>
Stopped: <YYYY-MM-DD>
Reason: ...
Retoma se: ... (ou "não retoma")
Artefatos relacionados: ...
```

---

## TODO — popular

Este arquivo nasceu vazio nesta reorganização. Próxima auditoria
de hygiene (ver `specs/repository_hygiene.md`) deve verificar:

- [ ] `git branch -a` → branches locais / remotas sem PR aberto
- [ ] `gh pr list --repo GFCDOTA/sketchup-mcp --state closed
      --search "is:closed -is:merged"` → PRs fechadas sem merge
- [ ] `.ai_bridge/HANDOFF.md` (se existir) → handoffs pendentes

Adicionar entry pra cada item que não retoma trivialmente.
