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
| `kind`        | `claude` (default), `local_llm`, `tool`, `correction_cycle`.         |
| `appearance`  | `true` = muda APARÊNCIA de planta/`.skp` → força rota `VISUAL_REVIEW`.|
| `verify_file` | caminho do artefato que o verify deve produzir/checar.               |
| `verify`      | comando determinístico de verificação (exit 0 = passou).             |
| `prompt`      | instrução passada ao worker dentro do worktree.                      |

A combinação `safe` + `appearance` decide a rota: `safe:false` nunca atua;
`appearance:true` nunca auto-aprova (vai pra VISUAL_REVIEW mesmo que o verify
determinístico passe).

> ⚠️ Drift doc/código honesto: hoje `appearance` é consumido só pelo dashboard
> (`server.py`) — o `dispatch()` decide a rota de aparência pela heurística de
> arquivo tocado `_appearance_changed` (`.skp`/`.png`/`consensus`/`renderer`/…),
> não pelo campo. Não prometa que `appearance:true` sozinho força o review.
> ⚠️ `kind` desconhecido (typo) cai no caminho `claude` caro (fallthrough sem
> validação) — conferir o kind antes de enfileirar.

## kind: `correction_cycle` (FP-033 slice 3)

Roda **UM ciclo** do `tools/correction_loop.py` (detect→classify→fix→re-check)
escopado num worktree isolado, reusando `dispatch()` inteiro via o seam
`run_worker` (guardas, verify, commit/push de branch, ledger — nada duplicado).

Campos da task: `id`, `title`, `safe`, `kind:"correction_cycle"`, `fixture`
(default `planta_74`), `out?` (default `E:/Claude/data/runs/noc_correction/
<fixture>` — **fora do worktree**, que é efêmero; a fila de visão
`vision_requests.jsonl` precisa sobreviver entre tasks; `data/runs` é scratch
com TTL), `render?` (path(s) de render do estado ATUAL do modelo, repassados
como `--render` pro consumer — **sem render explícito o drain bloqueia
`BLOCKED_NEEDS_RENDER`**: não existe fallback de "PNG mais novo do repo",
que num worktree fresco é arbitrário e pode entregar dogfood corrompido
commitado ao olho), `max_cycles?` (default 1), `verify_file` (default
injetado: `artifacts/correction_loop/<fixture>/loop_result.json`).

O worker: (1) se há fila de visão pendente, drena via
`tools/vision_queue_consumer` (POST `/ask-vision` no `:8765`; exit 3 =
`BLOCKED_NEEDS_FP032`/`BLOCKED_NEEDS_RENDER` honesto, o pedido FICA na fila —
tolerado); (2) roda o loop com `--max-cycles` (o `run_loop` **purga no início**
os outputs de runs anteriores no out persistente — `cycle_*/`,
`consensus_candidate.json`, `loop_result.json` — então a evidência copiada é
sempre DESTE run; as filas `*.jsonl` sobrevivem); (3) copia a evidência
(`loop_result.json`, `consensus_candidate.json`, `findings.json`) pro worktree.
Timeout/erro de subprocess vira `rc=1` no ledger (nunca exceção — senão a task
ficaria sem status terminal e re-dispararia pra sempre).

Ciclo de vida da fila de visão (anti-ping-pong): o consumer grava
`vision_consumed.jsonl` **antes** de `vision_confirmed.jsonl` (crash entre os
dois não re-drena nem duplica); cada confirmação alimenta **um** run do loop e
é ackada em `vision_confirmed_consumed.jsonl`; finding já confirmado pelo olho
(`source_check: visual_oracle`) nunca re-roteia `NEEDS_VISION` — o resíduo
qualitativo sobe pro Felipe. Defeito que persiste re-entra por pedido NOVO do
detector, não pela confirmação velha.

Mapa de resultado:

| saída do loop | status no ledger |
|---|---|
| `consensus_candidate.json` presente (fix mudou consensus) | `VISUAL_REVIEW_QUEUED` — o filename casa com a heurística `_appearance_changed`; commit `wip` + push, nunca auto-aprova |
| só `loop_result.json`/`findings.json` (evidência) | `COMMITTED` (determinístico) |
| loop `PENDING_VISION`/`NEEDS_FELIPE` (exit 3) | **sucesso enfileirado**, não falha — worker rc 0 |
| loop `STALL`/`RED` (exit 1) | worker rc 1 no ledger (investigar, não re-tentar em loop) |

Semântica: **1 task = 1 ciclo**. Os statuses terminais existentes
(`COMMITTED`/`VISUAL_REVIEW_QUEUED`/`NOOP`/`VERIFY_FAILED`) impedem re-run do
mesmo `id` — ciclo seguinte = task nova na fila.

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

## Apêndice: night_feeder — quem enche a fila quando o gate dorme

`tools/night_feeder.py` é o **alimentador**: um job read-only-exceto-a-fila que
detecta ociosidade do gate (idade do último registro de
`.ai_bridge/audit/audit.jsonl`) e faz **append** de trabalho seguro e capado em
`queue.jsonl` — quem age continua sendo o dispatcher; o veredito visual continua
sendo do Felipe.

**Caps default (por dia, ids `NF-<YYYYMMDD>-<slug>` = idempotência):**

- 1 `correction_cycle` por planta (default `planta_74`, `max_cycles: 1`);
- 1 `variant-sweep` (real SU-free, `n: 8` — o dispatcher passa `--dry-run` pro
  `tools.variant_sweep`, que nesse modo gera registros REAIS com
  `PENDING_VISION` honesto, sem visão e sem SketchUp);
- dedup duro: nunca enfileira kind+fixture que já está **pendente** na fila
  (pendente = sem status terminal no ledger, mesma régua do `pick_task`).

**Sinais reportados mas SEM ação automática (limitações honestas):**

- variante `PENDING_VISION` no corpus não tem caminho de drain via fila —
  `dispatch_variant_sweep` não expõe `--ask-vision`; upgrade manual:
  `python -m tools.variant_sweep --ask-vision --only <variant_id> --out <run>`;
- o drain de `vision_requests.jsonl` via fila (kind `correction_cycle`) exige
  `render` explícito na task; o feeder **não fabrica render** (sem ele o
  consumer bloqueia `BLOCKED_NEEDS_RENDER` e o pedido permanece).

**Como rodar / desligar:** `--dry-run` imprime o plano (default sem flags);
`--once` aplica; `--today`/`--now` injetam o clock (teste); `--no-sweep` /
`--no-correction` desligam cada perna; desligar de vez = simplesmente não
agendar o feeder (ele não tem daemon próprio — cada execução é one-shot,
exit 0 sempre).
