---
paths:
  - "artifacts/**"
  - "fixtures/**"
  - "docs/reports/**"
  - "docs/specs/fp042_*.json"
---
# Evidência, canônicos e inventário

- `fixtures/quadrado/`, `fixtures/planta_74/`, `artifacts/planta_74/planta_74.skp`, `artifacts/planta_74/furnished/*.skp` e o PDF são
  **protegidos**: ler e copiar, nunca escrever. Script de prova confere o SHA-256 deles antes e depois.
- Evidência e relatório já mergeados são **retrato datado**: não reescrever. Nova prova vai numa pasta nova
  (`artifacts/review/<frente>/<fase>/`) com README: commit sob prova, SketchUp, PIDs, reprodução, o que é e o que NÃO é.
- `artifacts/review/**` entra em `fp042_inventory.v1.json` **e** `fp042_references.v1.json` (blob sha do índice; arquivo editado depois
  do `git add` precisa do sha refeito). PNG/binário também em `fp042_asset_blobs.v1.json`.
- `.skp` de evidência só em `artifacts/review/<plant>/<branch_or_pr>/final/` (Constitution #8); intermediários ficam em `runs/`.
- Veredito visual em evidência é sempre `PENDING_HUMAN` até o Felipe responder no chat.
