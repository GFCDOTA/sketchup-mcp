# SPEC-C — Endurecer o Arquiteto: CORE obrigatório + 0 cross-cômodo

- **Sessão:** 2026-06-22 · linha STUDIO · branch `feat/sofa-class-from-reference`
- **Status:** ✅ FECHADO

## Problema
Re-rodando o Arquiteto (deepseek-r1:14b), a **suíte esquecia a cama** e a **cozinha saía
bugada** (itens prefixados `banheiro_`). Prompt solto + LLM local não confiável.

## Goal
Re-rodar os 4 cômodos → **0 itens cross-cômodo** e **quarto com cama**.

## Abordagem (LLM propõe, GATE garante — filosofia do projeto)
Duas camadas em `tools/interior_studio/architect_program.py`:
1. **Prompt endurecido**: lista os ITENS CORE OBRIGATÓRIOS do cômodo + proíbe móvel de
   outro cômodo + exige nome do próprio cômodo (sem prefixo).
2. **`normalize_program(items, room_key)` determinístico** (a garantia, não o prompt):
   - `CORE_BY_ROOM` — injeta CORE faltante (suíte→cama; cozinha→bancada/cooktop/geladeira;
     sala→sofá; banheiro→vaso/cuba).
   - `ROOM_EXCLUSIVE` — remove item exclusivo de outro cômodo (cama na cozinha, etc.).
   - `_strip_room_prefix` — salva o asset bom tirando prefixo errado (`banheiro_cooktop`→`cooktop`).
   - idempotente. Report `{removed, injected}` vai no proposal (transparência; humano ainda aprova).

## Prova
- **Unit (determinístico, sem LLM):** 4 testes novos em `tests/test_architect_program.py`
  (injeta cama na suíte · remove cross-cômodo · salva prefixo errado · idempotência). **9/9 verdes.**
- **Live (4 cômodos reais, deepseek):** suíte=`bed`✓ · cozinha=`bancada/cooktop/geladeira`✓ (sem
  `banheiro_`) · sala=`sofa`✓ · banho=`vaso/cuba`✓. Gate `0 removed/0 injected` (prompt resolveu;
  o gate é a rede de segurança contra regressão do LLM).

## Aceite — status
- [x] 0 itens cross-cômodo nos 4 cômodos.
- [x] Quarto com cama.
- [x] Testes verdes (9/9).

## Follow-up (NÃO deste spec)
- Nomes não-canônicos (`mesa_centro`, `poltrona`, `bidé`, `console_table`…) → mapa de
  sinônimos asset→canonical é **SPEC-B**.
