---
paths:
  - "tools/rooms/**"
  - "references/sketchup/knowledge/**"
  - "tests/test_fp04*.py"
  - "tests/test_fp05*.py"
---
# Módulos de cômodo, capacidades e conhecimento

- **Um dono por comportamento.** Código de um cômodo vive em `tools/rooms/<cômodo>/`; o que dois cômodos usam vai para
  `tools/rooms/shared/`. Cômodo não importa outro cômodo (gate de ownership no CI); fachada legada precisa de consumidor e data de remoção.
- **Fluxo obrigatório:** pedido → `specialists.plan()` (perfil + allowlist + binding → capability) → gates de domínio → job.
  Executor não ganha argumento de contorno; se a capacidade falta, o fluxo devolve `BLOCKED_*` com o motivo e o próximo passo.
- **Binding ↔ recipe ↔ fonte:** as fontes do binding são exatamente a união das fontes das suas recipes (`BINDING_SOURCE_MISMATCH`);
  binding com `capability_id` precisa de ≥1 fonte inspecionada. `source_verified=true` exige `human_review` da **mesma recipe**.
- **Catálogo** (`capability_catalog.v1.json`): `L2_PASS` exige evidência com `ref`, `commit`, `sketchup_version`, `symbol_digests`
  de todos os símbolos e `closure_digests` dos símbolos Python (fecho de helpers/constantes, T0.1). Mexeu num símbolo provado **ou
  num helper do fecho** → revogar (`L1_PASS`, `evidence: []`) no mesmo commit da mudança, rodar o L2 nesse commit limpo e restaurar no
  commit seguinte. Conferir com `python -m tools.rooms.capability_catalog` (`errors` vazio); ver o fecho com
  `python -m tools.rooms.evidence_closure --explain python:<mod.simbolo>`.
- **Fragmentos** (`tools/rooms/<cômodo>/fragments/*.fragment.v1.json`): cada capacidade e cada binding (inclusive lacuna) do
  cômodo tem exatamente um fragmento dono; o fragmento só aponta (specs, código, testes, alvos FP-052, golden, demos FP-053) e
  nunca autoriza execução. Capacidade/binding novo entra no fragmento certo no mesmo PR (`python -m tools.rooms.specialist_fragments`).
- **Recipe não é permissão:** conhecimento consultivo nunca eleva `implementation`/`validation`; trecho sem revisão humana não promove.
- **Entrada paramétrica:** `{value, unit, origin}` com `origin ∈ {user_request, consensus, pdf, derived}`; recusar com código estável
  (`CabinetInputError`-style) em vez de assumir valor.
- Teste de comportamento novo nasce vermelho; negativo real (o que deve bloquear) vale tanto quanto o positivo.
