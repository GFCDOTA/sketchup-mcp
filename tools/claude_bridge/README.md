# claude-bridge — Claude como oracle do GPT Auto-Consult Gate

Faz o `tools/ask_gpt_gate.py` consultar o **Claude** (em vez do ChatGPT) automaticamente,
nas decisões reais (os 9 triggers do gate), via HTTP no `:8765`. Motor: `claude -p`
headless na **assinatura** (sem API key).

## Como o gate usa isto
O gate já faz `GET :8765/health` + `POST :8765/ask {"prompt": ...}` e lê `{"response": ...}`.
Este server atende esse contrato e responde com `claude -p`. Suba na 8765 (parando o
bridge do ChatGPT, se estiver na mesma porta) e o gate fala com o Claude **sem mudar nada**.

> O gate consome a resposta pelo **HTTP**, não por arquivo. `.ai_bridge/responses/*.md`
> é só registro. Por isso o oracle é um *server*, não um vigia-arquivo.

## Setup (1x)
1. `claude setup-token` → gera um token OAuth de longa duração (requer assinatura Claude).
2. Cole o token em `tools/claude_bridge/.oauth_token` (gitignorado — **NUNCA** commitar).

## Rodar
```powershell
.\start.ps1 -SelfTest   # confirma a auth/chamada (espera 'PONG')
.\start.ps1             # sobe o oracle em :8765 — deixe a janela aberta
```
Janela aberta = oracle vivo. Fecha = desliga. Para auto-start no login, crie uma tarefa
no Agendador do Windows apontando para `start.ps1`.

## Limites (no system prompt do server)
- NUNCA aprova mutar fixture canônica (Hard Rule #3) → `Verdict: NEEDS-HUMAN`.
- NUNCA dá veredito visual IMPROVED/SAME/WORSE → `NEEDS-HUMAN`.

## Trocar o motor (futuro)
O ponto de troca é `ask_claude()` em `server.py`. Hoje = `claude -p` (assinatura, sem key).
Se um dia precisar de mais performance/escala, dá pra trocar por Anthropic SDK + prompt
caching ali, mantendo o mesmo contrato HTTP.

## Arquivos
- `server.py` — HTTP server self-contained; `claude -p` por request; guarda "not logged in".
- `start.ps1` — carrega o token e sobe o server.
- `.oauth_token` — local, **gitignorado**, seu token (não compartilhe/commite).
