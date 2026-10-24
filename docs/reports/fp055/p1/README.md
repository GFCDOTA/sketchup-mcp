# FP-055 P1 — runtime único e identidade verificável (2026-10-23)

## Reconciliação feita (sem descartar nada)
| Item | Antes | Ação | Depois |
|---|---|---|---|
| Checkout do MCP `E:/Claude/apps/sketchup-mcp` (`develop`) | `90d4433`, 102 atrás, 0 à frente; só `?? worktrees/` | removido o worktree limpo que eu tinha criado por engano em `apps/sketchup-mcp/worktrees/w-audit` (0 entradas no status, nenhuma ref); `git merge --ff-only origin/develop` | `ab934fa` = `origin/develop`, limpo, 0/0 |
| venv canônico | desatualizado frente ao `uv.lock` | `uv sync --locked`; a 1ª tentativa falhou no meio porque o servidor MCP em execução trava `rpds…pyd` e deixou o `jsonschema` sem importar; o `.pyd` travado foi movido para o temp e o sync refeito | imports verificados (`rpds`, `jsonschema`, `mcp`, `shapely`, `pytest`) |
| Servidor MCP desta sessão | carregou `90d4433` na memória | **não reiniciado** (é o processo da sessão); o novo check o acusa | `BLOCKED: processo carregou 90d44338a6 mas o disco está em ab934fa639: reiniciar o servidor` |

## O que entrou
`tools/sketchup/runtime_identity.py`: três identidades comparadas.
- `code`: HEAD, branch, sujo, à frente/atrás de `origin/develop`.
- `process`: HEAD no disco quando o processo importou o módulo. Detecta servidor velho depois de um pull.
- `bridge`: SHA-256 dos `.rb` executados pelo SketchUp.

`check(profile)`:
- `LEGACY_DIAGNOSTIC` nunca bloqueia: `OK` ou `RECORDED`.
- Perfis inteligentes ficam `BLOCKED` com o motivo se o checkout estiver atrás ou divergente, se o commit esperado não bater, se o
  checkout estiver sujo, se o processo estiver velho, se faltar um Ruby ou se o git for desconhecido (fail closed).
- `allow_dev=True` vira `DEV_OVERRIDE`, explícito no resultado.

Ligado em: `su_status` (`runtime_identity` no perfil `INTELLIGENT_BUILD`) e `su_furnish` (resultado carimbado `profile:
LEGACY_DIAGNOSTIC` + identidade). Nenhum caminho de geração ficou bloqueado nesta fase: o perfil inteligente só nasce na P3.

## Correção do P0
O `su_furnish` (`tools/sketchup/jobs.py::furnish`) **roda** o pré-voo obrigatório `layout_preflight` (FP-054 F1-03: circulação e
sobreposição) antes do SketchUp. O P0 rastreou só o `collect_boxes` comum e não o registrou. O `furnish_apartment.main` **não**
tem esse pré-voo. O retrato do P0 fica como está (é datado); a correção está aqui.

## Versão do SketchUp
26.0.429, relatada pelos jobs Ruby no resultado (`sketchup_version`). O check não abre o SketchUp para descobri-la.

**Gate P1:** a identidade do runtime é verificável (`code`, `process`, `bridge`) e divergência bloqueia o perfil inteligente ou
fica explícita como `DEV_OVERRIDE`. Testes: `tests/test_fp055_p1_runtime_identity.py` (repositório git temporário: sincronizado,
atrás, sujo, processo velho, commit esperado, Ruby ausente, git desconhecido).
