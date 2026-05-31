# Spec — Gate Framework + Audit Core (+ worker headless)

> Status: **PROPOSED** (design). Implementação delegada ao loop autônomo (modo B),
> validada pelo audit-core + testes. Design: peer-Claude, a pedido do Felipe (2026-05-31).

## Motivação

Em **modo B** (autonomia delegada — o oracle decide tudo menos o olho na planta), a
autonomia só é confiável se cada decisão for **observável e auditável na origem**. Hoje
a decisão passa por `tools/ask_gpt_gate.py` (gate monolítico) e o registro é solto
(`.ai_bridge/questions|responses/*.md`). Este spec formaliza:

1. **Gates modulares** — um módulo fino por tipo de decisão, plugável.
2. **Audit core** — log append-only, estruturado, consultável e *replayável* de TODA decisão.
3. **Worker headless** — opcional; roda ciclos sozinho sem sessão interativa (o "never kick").

Princípio anti-over-engineering: **1 core de audit + N módulos finos**. NUNCA uma lib por
micro-decisão (boilerplate). O ouro é o audit-core; os módulos são só organização.

## 1. Gate (interface)

Cada gate é um módulo registrado (`tools/gates/<id>.py`):

```python
class Gate(Protocol):
    id: str                                  # "consult", "fixture_regen", "visual", "merge"...
    def applies(self, ctx: dict) -> bool: ...       # esse gate é o dono dessa decisão?
    def build_prompt(self, ctx: dict) -> str: ...   # prompt determinístico a partir do ctx
    def parse(self, raw: str) -> Verdict: ...        # extrai o verdict da resposta do oracle
```

`Verdict = GO | NO_GO | VISUAL_REVIEW | MORE_INFO` (+ reasoning, risks, next_action).

Um **registry** resolve qual gate `applies(ctx)` e roteia. `ask_gpt_gate.py` vira um
*thin runner* sobre o registry (compat: os 9 triggers atuais mapeiam pra gates).

## 2. Audit core (o coração)

Toda chamada de gate — qualquer gate — grava **append-only** um registro em
`.ai_bridge/audit/audit.jsonl` (imutável; nunca reescrever linha):

```json
{
  "ts": "2026-05-31T...Z",
  "gate_id": "fixture_regen",
  "trigger": "a_b_c_decision_with_tradeoff",
  "context_digest": "sha256:...",      // hash do ctx (dedupe/replay)
  "prompt": "...",                       // exato, o que foi enviado
  "response_raw": "...",                 // exato, o que voltou
  "verdict": "GO",
  "action_taken": "regenerou consensus em runs/...",  // preenchido pela sessão DEPOIS
  "model": "claude (oauth)",
  "latency_ms": 2140
}
```

Regras: **append-only**; `prompt`+`response_raw` **exatos** (é o que viabiliza replay);
`action_taken` fecha o elo decisão→ação; **segredos nunca entram** (token fica no env).

## 3. Ferramentas

- `tools/audit_query.py` — filtra por gate / verdict / data / trigger
  ("o que o oracle decidiu sozinho, verdict=GO, em fixture nas últimas 24h?").
- `tools/audit_replay.py <ts|digest>` — re-envia o `prompt` salvo ao oracle ATUAL e
  **dá diff** na resposta. Pega **drift de julgamento** (o oracle regrediu? mudou de ideia?).
  É teste de regressão do próprio oracle.

## 4. Worker headless (opcional — o "never kick again")

A sessão interativa **para** e precisa de um turno humano pra retomar. O worker remove isso:
processo que roda ciclos do `autonomous-fidelity-loop` **sem sessão interativa**.

- `tools/fidelity_worker.py`: a cada N min (ou on-demand) invoca `claude -p` com o protocolo
  da skill no cwd do repo; faz **UMA fatia**, commita, registra no audit, dorme. Pára em
  RED / patinagem / VISUAL_REVIEW.
- Disparo: Agendador do Windows (logon) ou manual. Cada ciclo é uma chamada headless
  **isolada** → auditável + sem estado preso a janela.
- **Segurança = o carve-out do modo B**: o worker NUNCA promove fixture a canônica nem
  julga visual sozinho — emite `VISUAL_REVIEW` (pinga o Felipe). Tudo no audit log.

> O worker mata o "toda hora preciso pedir". O audit-core é o que o torna seguro:
> você não está no loop, mas **vê e reproduz cada decisão**.

## 5. Implementação (delegada ao loop — fatias, cada uma = commit + teste)

1. `audit_core` (write/read `audit.jsonl`) + teste.
2. `Gate`/registry + migrar 1 gate real (o `ask_gpt_gate` atual vira gate `consult`).
3. `audit_query` + `audit_replay` + testes.
4. Migrar os demais gates (fixture_regen, visual, merge...).
5. **(sob OK do Felipe)** `fidelity_worker`.

Cada fatia respeita Hard Rules + modo B. Specs irmãos: `fidelity_gate.md`,
`sdd_and_harness_engineering.md`.
