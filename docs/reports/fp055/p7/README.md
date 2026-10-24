# FP-055 P7 — gate de consumo (integração nominal não volta a passar) (2026-10-24)

## O que entrou
`tools/validation/consumption_baseline.py` mede com o rastreio dinâmico do `pipeline_audit` (processo novo, escala da planta)
o estado de cada capacidade do catálogo (INVOKED / CONSUMED), dos módulos vigiados, dos especialistas e das receitas, e
compara com o retrato versionado `docs/governance/consumption_baseline.v1.json`. Diverge **nas duas direções**:
- `REGRESSAO`: algo que era chamado/consumido deixou de ser (chamada removida, saída descartada);
- `MELHORIA`: algo passou a ser consumido e o retrato não foi atualizado (senão uma regressão futura passaria sem aviso);
- `NOVA` / `REMOVIDA`: capacidade ou módulo vigiado fora do retrato.
Roda no CI (`pytest -m planta74_scale`, `tests/test_fp055_p7_consumption_baseline.py`) e na linha de comando
(`PT_TO_M=0.0259 python -m tools.validation.consumption_baseline [--write]`), que também imprime o **relatório de não consumidos**.

## Estado real da geração do apartamento (develop + #489)
- Capacidades que a geração consome: layouts por cômodo (cozinha, sala, quarto, banho, serviço), `kitchen.sink-anchor-guard`,
  `bathroom.wet-room.guard` (agora bloqueia, #427) e as peças de cama/guarda-roupa/sofá (transitivo).
- **Não consumidas** (INVOKED=false): `shared.cabinet.parametric`, `kitchen.cabinet.plain-fronts`, `kitchen.cabinet.shaker-door`,
  `shared.cabinet.front.shaker` (as 4 de marcenaria L2 — #426), `living.sofa.gate`, `bedroom.wardrobe.gate`, `kitchen.ergonomics.audit`
  e `circulation.gate` (o símbolo do catálogo não é o que os brains chamam — #429).
- Módulos vigiados **não executados** pela geração legada: `specialists.plan`, fragmentos, catálogo, loader de conhecimento,
  F1B/F1C, solver F2 (problem/engine/candidates/solver/ranking/proposal), `furniture_overlap_gate`, `room_collisions`, cabinet
  paramétrico/Shaker. O orquestrador inteligente (`intelligent_pipeline`) os executa no perfil dry-run; levar isso à geração
  integrada é a P6/P8 (#417, #419).
- Especialistas invocados 0/9; receitas consumidas 0/19.

## Mutação de integração
Os testes unitários mutam o retrato/estado e provam que o gate reprova: chamada removida (`REGRESSAO … INVOKED`), saída
descartada (`REGRESSAO … CONSUMED`), módulo vigiado que deixa de rodar, melhoria não registrada e capacidade nova/removida. Já
existiam as mutações do orquestrador (interface ausente → INVALID_INPUT/INVOKED≠CONSUMED, runtime velho → BLOCKED_RUNTIME,
fonte alterada → BLOCKED_SOURCE_REVISION).

## O que NÃO é
Não prova que o `.skp` reflete a capacidade (REFLECTED_IN_MODEL/VALIDATED seguem `NOT_EVALUATED`; isso é a geração completa,
FP-056 P6) nem aprova aparência.
