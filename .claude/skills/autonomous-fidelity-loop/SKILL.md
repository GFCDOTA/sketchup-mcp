---
name: autonomous-fidelity-loop
description: Use quando o Felipe quer a sessão trabalhando a fidelidade de uma planta (planta_74 etc.) de forma CONTÍNUA e autônoma, em ciclos auto-ritmados, imprimindo um LOG de status por ciclo (PROGREDINDO/PATINANDO/BLOCKED), auto-corrigindo o que os detectores DETERMINÍSTICOS pegam, registrando lições, e parando só em RED / patinagem / NEEDS-HUMAN / backlog esgotado. Dispara em "não pare", "loop contínuo", "fidelity loop", "deixa rodando sozinho", "trabalha sozinho na planta", ou pedido de feedback de progresso ao vivo. NÃO usar pra tarefa pontual nem doc/typo.
---

# Autonomous Fidelity Loop

Faz a sessão tocar a fidelidade da planta **sem parar à toa**, com **log por ciclo** e
**auto-correção do que é determinístico**. O motor é o `/loop` (self-paced) — esta skill
é o protocolo canônico que ele segue.

## Como entrar
Entre em `/loop` dinâmico (sem intervalo, self-paced) com o protocolo abaixo. Cada wakeup
do loop = um ciclo. Não pasteie prompt solto — invoque esta skill (ou diga "não pare").

## Log por ciclo (OBRIGATÓRIO — imprima 1 linha por ciclo)

```
[ciclo N | HH:MM] fiz: <slice> | gate(:8765): <GO/NO-GO/—> | dets: overlay_diff=<PASS/FAIL> opening_host=<x/12> | tests: <n✓> | ESTADO: PROGREDINDO | PATINANDO | BLOCKED | aprendi: <1 frase ou —>
```

## Regras do ciclo

1. **PERCEBER erro (determinístico):** rode `tools/overlay_diff` + `tools/opening_host_audit`
   + `pytest`. Conserte o que eles acusarem; **commit por slice**.
2. **NÃO autojulgar visual:** render / representação / fixture NÃO se autojulga — o oracle de
   visão dá falso PASS (ver `negative_dogfood`). Isso é **NEEDS-HUMAN** → flag pro Felipe e segue.
3. **APRENDER (memória escrita, não ML):** ao errar/descobrir, escreva 1 linha em
   `.claude/memory/lessons_learned.md` + HANDOFF e **releia antes de repetir**.
4. **Consultar o oracle:** decisões A/B/C reais → `gpt-auto-consult-gate` (POST `:8765`).
5. **Detectar PATINAGEM:** 2 ciclos sem progresso novo (mesmo FAIL / nada commitado /
   repetindo a mesma tentativa) → **PARE** e reporte `PATINANDO: <motivo>`. Não insista no escuro.
6. **PARAR (certo, não desperdício):** pare só em **RED real**, **PATINANDO**,
   **NEEDS-HUMAN bloqueante**, ou **backlog determinístico esgotado** (reporte
   "backlog limpo, parando — sem inventar ciclo"). Fora isso → próximo ciclo.

## Modo B — autonomia delegada (não furar)
- Fixture/consensus: regenerar/corrigir é **AUTÔNOMO** (decide e faz). Mas **PROMOVER pra
  canônica** dispara `VISUAL_REVIEW` (olho do Felipe vs PDF) antes de virar ground-truth.
- Veredito visual IMPROVED/SAME/WORSE: **nunca** auto (não-confiável) → `VISUAL_REVIEW`.
- Develop-first; commit por slice; `--mode headless` proibido em dev local.

## Limites honestos (dizer ao Felipe, não fingir)
- **"Aprender"** = acumular lição em arquivo + reler — **não** é rede neural aprendendo.
- **"Perceber a planta errada"** = só o que os detectores **determinísticos** medem; o
  julgamento **visual** sobe pro humano.
- **"Não parar"** = não parar **à toa**; quando o trabalho real acaba, **parar é o certo**
  (continuar sem ROI = patinar = tempo/dinheiro jogado fora).
