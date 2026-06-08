# Plano Cérebro / Músculo — sketchup-mcp

> Síntese (2026-06-08) do inventário NOC dispatcher + RTK + LLM local + gate/tier + cockpit.
> Objetivo: tirar o trabalho GROSSO da sessão Claude (que custa token) e jogar na máquina local.

## Princípio

- **Claude (sessão) = CÉREBRO**: decide, sintetiza, orquestra, produz design intent, julga via gate. Caro em token.
- **Máquina local = MÚSCULO**: executa o trabalho GROSSO (build `.skp`, render V-Ray, pytest, scans, git) e devolve
  só o **resultado compacto**. O cérebro **nunca lê log cru**.

## Sintoma (por que importa)

Cada build/render/pytest despeja centenas de linhas no contexto do cérebro. Ex.: um render V-Ray ≈ 500 linhas de log
que o cérebro não precisa — ele só quer `{status, png, base_intact}`. Isso queima token e polui o contexto. O músculo
absorve o verboso; o cérebro lê o veredito. (Evidência viva: a sessão V-Ray colou logs gigantes de render no contexto.)

## Componentes existentes (mapeados a papéis)

| Componente | Papel no split |
|---|---|
| **NOC dispatcher** (`tools/claude_bridge/noc_dispatcher.py`) | Músculo **ASSÍNCRONO**: fila → worktree isolado off develop → worker → verify determinístico → ledger. Pra tasks enfileiradas, `safe`, auto-verificáveis. Rails: 1-lock TTL, nunca main/auto-merge, aparência→VISUAL_REVIEW. |
| **RTK** (Rust Token Killer) | Mata token nos ops **INLINE** (git/scan/status) — já transparente via hook (60-90%). |
| **LLM local** (Ollama) | Compute **grátis** pra decisões baratas/repetitivas (o "fast" abaixo do Sonnet). |
| **gate/tier** (`tools/consult_tier.py`) | Roteia a DECISÃO: fast (Sonnet/low) p/ rotina, deep (Opus/xhigh) p/ o juízo. |
| **cockpit** `:8765` | Observabilidade + o único gate humano (VISUAL_REVIEW). |

## A lacuna

Falta o **músculo INLINE síncrono**: um comando único que o cérebro chama no meio do raciocínio, roda o pesado local, e
devolve **um JSON compacto** (sem log cru). Hoje o cérebro ainda spawna SU/V-Ray/pytest e lê o log inteiro. O NOC
dispatcher resolve o ASSÍNCRONO (fila), não o inline.

## Contrato — `tools/muscle.py`

`python tools/muscle.py <verb> <args> [--json]` →
- roda o trabalho pesado LOCAL;
- redireciona TODO o verboso p/ um **log file** (`runs/muscle/<verb>_<ts>.log`), nunca p/ stdout;
- imprime no stdout **só** um JSON compacto; exit-code = status.

```json
{"verb":"gates","target":"planta_74","status":"pass",
 "metrics":{"...":"..."},"artifacts":["..."],"log_path":"runs/muscle/gates_...log",
 "elapsed_s":3.2,"base_intact":true}
```

Verbos (crescem por slice): `gates <plant>` · `build <plant>` · `render <...>` · `test [pattern]` · `git <op>`.
Determinístico, idempotente, exit-code = status. Base `.skp`/fixtures: hash conferido (nunca muta — Hard Rule #3).

## Como compõe (não duplica)

- NOC dispatcher chama `muscle.py` por baixo (mesma engine de verify) p/ as tasks da fila.
- RTK envelopa os `git`/`scan` DENTRO do muscle (token-kill em cascata).
- gate/tier decide QUANDO vale Opus vs Sonnet vs LLM-local p/ cada decisão do cérebro.
- cockpit lê `runs/muscle/` + ledger p/ mostrar o que o músculo fez.

## Primeiro slice mínimo e verificável

**`tools/muscle.py gates <plant>`** — envelopa `tools/run_deterministic_gates.py` (determinístico, sem SU/rede, segundos):
- captura o verboso num log file;
- devolve JSON compacto `{plant, gates:{<gate>:pass|fail,...}, verdict, log_path}`;
- exit 0 = todos PASS, 1 = algum FAIL.

**Por que este 1º:** é o que o cérebro mais consulta no ciclo de fidelidade; é determinístico (verificável na hora);
não depende de SU/AV; prova o contrato barato. Depois estende p/ `build`/`render` (o maior token-saver, mas envolve
SU/V-Ray/AV — risco a isolar).

**Verificação do slice (aceitação):**
1. `python tools/muscle.py gates planta_74` → JSON ≤ ~10 linhas + exit casa com o gate determinístico.
2. `python tools/muscle.py gates quadrado` → idem (quadrado PASS).
3. `tests/test_muscle.py` pina o SHAPE do JSON (verb/status/log_path/exit-code) — hermético.
4. O log verboso vai p/ `runs/muscle/` (gitignored), NÃO p/ o stdout/contexto.

Resultado: o cérebro passa a ler ~8 linhas no lugar do log inteiro de gates. É a base do contrato p/ depois absorver
build/render (onde o ganho de token é maior).
