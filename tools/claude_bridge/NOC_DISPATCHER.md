# NOC dispatcher — o NOC que AGE, não só vigia

O cockpit do NOC (`server.py` + `dashboard.html`) é um **vigia**: lê estado
(fleet local, fila de consults, inventário SKP) e mostra. O **dispatcher** é o
**atuador** — ele pega uma task da fila, abre um worktree isolado, roda um worker
autônomo dentro dele, **verifica deterministicamente** o resultado e só então
mantém o trabalho. É o braço que executa o que o NOC enxerga.

Por que existe: sem atuador, todo item de backlog precisa de um humano pra abrir
worktree, rodar o agente, conferir e landar. O dispatcher fecha esse loop pras
tasks **seguras e auto-verificáveis**, deixando o humano só onde ele é
insubstituível (o olho na aparência da planta).

> Honestidade: este doc descreve o **contrato** do dispatcher (fila, ledger,
> rails, flags). O atuador em si é operado pelo NOC; os workers nunca dão
> `commit`/`merge`/`push` — quem landa é o dispatcher, e só depois do verify.

## Rails de segurança (inegociáveis)

São os limites que tornam a autonomia aceitável. Quebrar qualquer um é RED.

- **Lock de 1-atuador com TTL.** Só um dispatcher atua por vez. O lock tem
  *time-to-live*: se o processo morrer sem soltar, o lock expira e outro
  dispatcher pode assumir — sem deadlock permanente, sem dois atuadores
  pisando no mesmo repo.
- **Worktree isolado, off `develop`.** Cada task roda num `git worktree` próprio,
  criado a partir de `origin/develop` (develop-first), **fora do glob
  `sketchup-mcp*`** — não toca o checkout principal nem outros worktrees do NOC.
- **NUNCA `main`, NUNCA auto-merge.** O dispatcher não escreve em `main` e não
  faz merge sozinho. No máximo prepara o trabalho num branch isolado; landar em
  `develop`/`main` segue o fluxo de PR humano-revisável (Hard Rule #4).
- **Verify determinístico antes de manter.** Nada é mantido por "parece bom".
  Cada task aponta um `verify` (comando determinístico) e/ou um `verify_file`
  (artefato esperado). Falhou → o trabalho é descartado/marcado, não landa.
- **Aparência de planta/`.skp` → não auto-aprova.** Se a task muda a APARÊNCIA
  de uma planta ou `.skp`, o dispatcher **não** julga fidelidade (veredito visual
  IMPROVED/SAME/WORSE é comprovadamente não-confiável em modo auto). Ele
  **enfileira um `VISUAL_REVIEW`** pro humano e registra `VISUAL_REVIEW_QUEUED`.
  O olho do Felipe vs o PDF é o único gate humano.

## Como rodar

```bash
# Processa a fila inteira (modo daemon/batch normal)
python tools/claude_bridge/noc_dispatcher.py

# Uma única task e para — bom pra inspecionar o ciclo
python tools/claude_bridge/noc_dispatcher.py --once

# Simula tudo (abre nada, landa nada) — só mostra o que faria
python tools/claude_bridge/noc_dispatcher.py --dry-run

# Roda só a task com este id (ignora o resto da fila)
python tools/claude_bridge/noc_dispatcher.py --task-id <id>
```

As flags compõem: `--once --dry-run`, `--task-id <id> --dry-run`, etc.
`--dry-run` sempre vence — nenhum efeito colateral é gravado.

## A fila — `.ai_bridge/noc/queue.jsonl`

Uma task por linha (JSONL). Campos:

| campo         | o que é                                                              |
|---------------|----------------------------------------------------------------------|
| `id`          | identificador único da task (casado com `--task-id` e com o ledger). |
| `title`       | descrição curta, legível.                                            |
| `safe`        | `true` = elegível pra atuação autônoma; `false` = só humano.         |
| `appearance`  | `true` = muda APARÊNCIA de planta/`.skp` → força rota `VISUAL_REVIEW`.|
| `verify_file` | caminho do artefato que o verify deve produzir/checar.               |
| `verify`      | comando determinístico de verificação (exit 0 = passou).             |
| `prompt`      | instrução passada ao worker dentro do worktree.                      |

A combinação `safe` + `appearance` decide a rota: `safe:false` nunca atua;
`appearance:true` nunca auto-aprova (vai pra VISUAL_REVIEW mesmo que o verify
determinístico passe).

## O ledger — `.ai_bridge/noc/actions.jsonl`

Append-only, uma ação por linha. Registra o que o dispatcher **fez** com cada
task (`id` casa com a fila). O campo `status` é um destes:

| status                  | significado                                                    |
|-------------------------|----------------------------------------------------------------|
| `DRY_RUN`               | rodou com `--dry-run`; descreveu o que faria, sem efeito.      |
| `NOOP`                  | nada a fazer (sem diff / task já resolvida / não elegível).    |
| `VERIFY_FAILED`         | o `verify` determinístico falhou; trabalho **não** mantido.    |
| `COMMITTED`             | verify passou e o trabalho foi mantido/landado pelo dispatcher.|
| `VISUAL_REVIEW_QUEUED`  | task de aparência; enfileirada pro humano, **não** auto-aprovada.|

O ledger é a fonte de verdade auditável: dá pra reconstruir tudo que o atuador
tocou, por que manteve ou descartou, e o que ficou pendente de olho humano.
