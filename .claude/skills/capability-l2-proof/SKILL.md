---
name: capability-l2-proof
description: >-
  Prova uma capacidade de móvel/marcenaria no SketchUp real (L2) e mantém o catálogo honesto: revoga a evidência quando
  um símbolo provado muda (R-18), roda o script de prova numa cópia sob runs/ num commit limpo, coleta
  summary/trace/negativos, recalcula os digests, restaura L2_PASS e registra os arquivos no inventário FP-042. Use ao
  mudar código de uma capacidade com L2_PASS (gabinete, Shaker, fluxos da cozinha), ao ver BLOCKED_EVIDENCE_STALE ou
  EVIDENCE_STALE, ao promover uma capacidade de L1 para L2, ou em "refaz o L2", "prova no SketchUp real", "evidência
  velha".
---

# capability-l2-proof

Uma capacidade só é `L2_PASS` se a evidência foi gerada **no código que está no catálogo**. O digest de cada símbolo
(`symbol_digests`) e o do seu fecho estático (`closure_digests`: helpers e constantes de `tools.rooms`/`core` alcançados por
nome) amarram as duas coisas; mudou qualquer um, a prova caiu (R-18). Este é o procedimento que mantém isso verdadeiro sem
contorno. Ver o que entra no fecho: `$PY -m tools.rooms.evidence_closure --explain python:<mod.simbolo>`.

## Checklist (copiar e marcar)

```
- [ ] 1. Teste vermelho do comportamento novo (ver o vermelho no código antigo)
- [ ] 2. Implementar até verde; ruff nos arquivos tocados
- [ ] 3. Revogar a prova no catálogo (no MESMO commit da mudança)
- [ ] 4. Script de prova novo (nunca editar o de uma prova já mergeada) + registro FP-042
- [ ] 5. Commit A limpo (git status --porcelain vazio)
- [ ] 6. Rodar o L2 nesse commit, saída em runs/
- [ ] 7. Conferir summary: dirty=false, todos os casos PASS, PIDs fechados, canônicos intactos
- [ ] 8. Copiar evidência + README; restaurar L2_PASS com os digests novos; registrar
- [ ] 9. Suítes completas; commit B; PR; 4 checks verdes no head exato; merge
```

## Passos que não aceitam improviso

**3. Revogar.** Em `tools/rooms/capability_catalog.v1.json`, na capacidade afetada: `"state": "L1_PASS"` e
`"evidence": []`. Sem isso `specialists.plan` devolve `BLOCKED_EVIDENCE_STALE` e o próprio fluxo não roda. Os testes que
exigem `L2_PASS` ficam vermelhos só no commit A — é esperado; o head do PR fica verde.

**4. Script de prova.** Pasta nova `artifacts/review/<frente>/<fase>_l2/` com o script (copiar o anterior e acrescentar o
negativo real do comportamento novo). O script grava `commit` e `dirty` do `git status --porcelain`, confere SHA-256 dos
canônicos antes/depois, fecha só os PIDs que subiu e sai com código ≠ 0 se algum caso falhar. Registrar:
```bash
git add artifacts/review/<frente>/<fase>_l2/
python -m tools.navigation.register_evidence artifacts/review/<frente>/<fase>_l2/<arquivo> ...
```

**6. Rodar** (exemplo da cozinha; base = cópia do `.skp` mobiliado, nunca o canônico):
```bash
mkdir -p runs/<fase> && cp artifacts/planta_74/furnished/planta_74_furnished.skp runs/<fase>/base.skp
PT_TO_M=0.0259 PYTHONPATH=. $PY artifacts/review/<frente>/<fase>_l2/<script>.py runs/<fase>/out runs/<fase>/base.skp <request.json>
```
O log pode sair em cp1252; ler o `summary.json`, não o terminal.

**8. Restaurar.** Digests do commit A:
```bash
$PY -m tools.rooms.capability_catalog --digest python:<mod.simbolo> ...
```
Nova entrada de evidência: `ref` (README da pasta), `commit` (sha curto do A), `sketchup_version`, `scope` (o que a prova
cobre e o que NÃO é — nunca veredito visual) e `symbol_digests` de **todos** os símbolos da capacidade. Prova antiga de
outra fase fica no histórico do git, não no catálogo. Depois, o fecho (helpers e constantes que os símbolos alcançam):
```bash
$PY -m tools.rooms.evidence_closure --backfill            # seco: compara o fecho no commit da prova × HEAD
$PY -m tools.rooms.evidence_closure --backfill --write    # grava closure_digests (recusa se alguma prova estiver velha)
```
Conferir `python -m tools.rooms.capability_catalog` (`errors: {}`).
Editou o README depois do `git add`? Rodar `register_evidence` de novo (refaz o blob sha).

## README da evidência (mínimo)

Defeito/mudança · por que o L2 foi refeito · tabela com commit sob prova (`dirty: false`), SketchUp, PIDs e reprodução ·
resultado caso a caso (positivo, idempotência, negativos com 0 PIDs, FP-047 `strict_identity`, canônicos idênticos) ·
**o que NÃO é** (aparência segue `PENDING_HUMAN`). Não alegar mutação de teste que não rodou de fato.

## Armadilhas

- Mutar o símbolo para "provar" o teste invalida o digest e derruba a suíte inteira — isso prova o R-18, não o teste.
- `human_review` cobre uma recipe e um trecho; o negativo "outra recipe do mesmo vídeo" é obrigatório quando a prova cita fonte.
- Achado preexistente (ex.: `CIRC|r000|corredor_principal`) é registrado como preexistente, nunca como introduzido.
- Relatório datado de fase anterior (P0, promoção) não se reescreve; a correção vai na spec/histórico e numa pasta nova.

Referência de execução real: `artifacts/review/fp046/review_scope_l2/README.md` (PR #358).
