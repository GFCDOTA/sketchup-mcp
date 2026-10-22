# Handoff por arquivo — Banheiro

> Gerado por `python -m tools.navigation.file_audit --out docs/reports/file_audit` em `66fd65b`.
> Retrato datado: regenere, não edite. Estados e regras no docstring de `tools/navigation/file_audit.py`.

Contagem: ACTIVE_ENTRYPOINT 1, ACTIVE_IMPORTED 2, CLI_DOC_ONLY 2, CONFIG 2, DOC 1, PACKAGE_MARKER 2

| Arquivo | Estado | Por quê | Importado por | Citado por | Último toque | Próximo passo |
|---|---|---|---|---|---|---|
| `tools/rooms/bathroom/__init__.py` | PACKAGE_MARKER | pacote sem logica | 0 | 10 | 2026-10-18 | manter |
| `tools/rooms/bathroom/capabilities/__init__.py` | PACKAGE_MARKER | pacote sem logica | 0 | 2 | 2026-10-19 | manter |
| `tools/rooms/bathroom/capabilities/estudio_banheiro_scene.py` | CLI_DOC_ONLY | CLI manual citada so em documentacao (6 doc); nenhum teste/CI a executa | 0 | 6 | 2026-10-20 | dar teste de fumaca (vira ACTIVE) ou arquivar com decisao do Felipe |
| `tools/rooms/bathroom/capabilities/render_banho_auto.py` | CLI_DOC_ONLY | CLI manual citada so em documentacao (6 doc); nenhum teste/CI a executa | 0 | 6 | 2026-10-19 | dar teste de fumaca (vira ACTIVE) ou arquivar com decisao do Felipe |
| `tools/rooms/bathroom/capabilities/render_banho_vray.py` | ACTIVE_ENTRYPOINT | citado por 2 arquivo(s) de codigo/CI/config/skill | 0 | 7 | 2026-10-20 | manter |
| `tools/rooms/bathroom/knowledge/index.v1.json` | CONFIG | configuracao/outro |  | 2 | 2026-10-19 | manter |
| `tools/rooms/bathroom/layout.py` | ACTIVE_IMPORTED | importado por 6 arquivo(s) | 6 | 8 | 2026-10-19 | manter |
| `tools/rooms/bathroom/specialist.md` | DOC | documentacao |  | 3 | 2026-10-19 | manter |
| `tools/rooms/bathroom/specialist.v1.json` | CONFIG | configuracao/outro |  | 2 | 2026-10-19 | manter |
| `tools/rooms/bathroom/validation.py` | ACTIVE_IMPORTED | importado por 2 arquivo(s) | 2 | 2 | 2026-10-19 | manter |
