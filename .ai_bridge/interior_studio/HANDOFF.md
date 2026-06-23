# INTERIOR STUDIO — HANDOFF (fábrica de repertório, não mural de chat)

> Objetivo: o `:8782` para de ser "PM fala | Lead fala | Arquiteto fala" e vira uma **esteira por
> ciclo/cômodo/móvel**. A unidade principal é o **CYCLE**, não a mensagem de agente.
> O painel responde em 10s: que asset · que ciclo · que referências · que gates · o que GPT/Felipe
> decidiu · o que o Arquiteto aprendeu · qual a próxima ação.

## Estado (2026-06-21)
- `SOFA_REFERENCE_PACK` (MT-SOFA-001) já gerado — 6 referências reais + análise. **NÃO construir sofá** até curadoria.
- Dashboard atual: SPA stdlib (`tools/studio_dashboard.py`), seções `.card` montadas de `/api/state`.
- `consult_gpt_bridge/` existe e funciona (contratos v1, manual MVP, ingest → DNA/anti-patterns/microtask).
- **Travas:** stdlib only (Docker, sem pip) · não tocar `:8765` · não mexer geometria congelada/GOLDEN · sem OpenAI API / Chrome ext ainda.

## Microtarefas (ordem de implementação — começar pela VERDADE DO PROCESSO)
- [x] **MT-001 — entidade `cycle`** — `tools/interior_studio/cycles.py` + `.ai_bridge/interior_cycles/CYCLE-NNN.json` (schema: steps/references/gates/consult/learning). Idempotente, stdlib.
- [x] **MT-002 — painel "Ciclo Atual"** — barra de fábrica no topo + timeline PM→Lead→Scout→Felipe→Arquiteto→Gates→Consult→Learning (cada etapa com status/resumo/modelo).
- [x] **MT-003 — Reference Pack visual** — `tools/interior_studio/reference_packs.py` + `.ai_bridge/reference_packs/sofa_reference_pack_001.json`; painel mostra cada referência com imagem(link)/tags/copiar/evitar.
- [x] **MT-004 — curadoria Felipe** — botões 👍 aprovar · 👎 rejeitar · ⭐ principal · 🚫 anti-pattern (+comentário) → `references/felipe/{approved,rejected,anti_patterns}/` + atualiza o ciclo.
- [x] **MT-005 — Consult Liaison sidecar** — manter o `🔌 Consult GPT Bridge` (já existe) como sidecar do fluxo, não 4ª coluna.
- [x] **MT-006 — Learning Log** — painel lê ingested + judge anti-patterns + DNA "Aprendido" + golden samples → novas regras / anti-patterns / golden samples.
- [x] **MT-007 — SOFA_REFERENCE_PACK** — feito (md+json+inbox). Aguardando curadoria.
- [x] **MT-008 — bloquear Arquiteto até curadoria** — `cycles.architect_blocked()` = sem referência ⭐principal ⇒ etapa Architect fica `blocked`; build do sofá proibido.

## Depois (NÃO agora)
- OpenAI API real (`openai_client.py` é stub seguro) · Chrome extension · automação completa do ciclo · construir a classe sofá (só pós-curadoria → SOFA_BUILD_SPEC).

## Modelo de dados
```
.ai_bridge/interior_cycles/CYCLE-NNN.json     # entidade cycle
.ai_bridge/reference_packs/sofa_reference_pack_001.{json,md}
references/felipe/{approved,rejected,anti_patterns,golden_samples}/   # curadoria persistida
.ai_bridge/interior_consult/{outbox,inbox,ingested,...}               # consult bridge (existe)
.claude/memory/felipe_style_dna.md                                   # DNA canônico
```

## Critério de pronto (deste ciclo de dashboard)
1. painel mostra o ciclo atual · 2. timeline das 8 etapas · 3. SOFA_REFERENCE_PACK existe ·
4. Felipe aprova/rejeita/principal/anti-pattern · 5. Arquiteto bloqueado sem ⭐principal ·
6. Consult gera pergunta GPT · 7. learning log registra regra/anti-pattern · 8. fluxo antigo intacto ·
9. nada toca `:8765` · 10. não constrói sofá sem curadoria.
