# SPEC-B — Aprovar programa → inventário DINÂMICO

- **Sessão:** 2026-06-22 · linha STUDIO · branch `feat/sofa-class-from-reference`
- **Status:** ✅ FECHADO (modelo+teste; badge visual no dash = polish opcional)

## Goal
Ao aprovar um `furniture_program` no dash, o inventário do cômodo passa a ser o programa
aprovado (não o `ROOMS` hardcoded).

## Gotcha (handoff)
Reconciliar nomes: o Arquiteto diz `mesa_centro`/`tv_console`/`sofa_2_places`; o
`project_state` usa `coffee_table`/`rack`/`sofa`. Precisa de mapa de sinônimos asset→canônico.

## Implementação (`tools/interior_studio/project_state.py`)
- **`ASSET_SYNONYMS`** (canônico → keywords) + **`canonical_asset(name, room_key)`**:
  mapeia a linguagem do Arquiteto pro modelo de 10 assets. **Cozinha/banheiro colapsam** no
  asset único do cômodo (`SINGLE_ASSET_ROOM`: kitchen/vanity) — coerente com o modelo canônico.
- **`room_asset_keys(room_key, default)`**: lê `proposals.approved_program(room_key)`; se houver,
  o inventário = itens do programa mapeados (deduped, na ordem do programa); senão, o `ROOMS`
  hardcoded. Item sem canônico entra 'loose' (estado not_started) — reflete a escolha do Arquiteto.
- **`project_state()`** usa o overlay e expõe `assets_source` ∈ {program, default} por cômodo.
- Sem programa aprovado → comportamento idêntico ao anterior (compat retro).

## Prova
- 3 testes novos em `tests/test_project_state.py`: mapa de sinônimos (tv_console→rack,
  mesa_centro→coffee_table, bancada→kitchen, cuba→vanity, inexistente→None) · **aprovar sala →
  inventário = [sofa, coffee_table, rack]** (mapeado+deduped, source=program) · sem programa →
  default. Fixture `sandbox` agora isola `proposals.PDIR` (determinismo). **27/27 verdes.**
- Live: 4 pending / 0 approved → todos os cômodos `default` (sem regressão); o dash já consome
  `rooms[].assets`, então aprovar um programa muda o inventário sozinho.

## Aceite — status
- [x] Aprovar a sala → inventário mostra os itens do Arquiteto (mapeados).
- [x] Teste verde (27/27).

## Follow-up opcional
- Badge no dash ("📋 do Arquiteto" vs "padrão") lendo `assets_source` — UI polish, não bloqueia.
