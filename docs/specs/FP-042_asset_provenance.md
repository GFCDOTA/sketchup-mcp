# FP-042/P6 — preservação determinística dos assets

A snapshot `fp042_asset_blobs.v1.json` registra 707 blobs binários versionados, inclusive `.skp`, PDFs e renders, com Git blob SHA, tamanho e agrupamento de diretório no commit `60aa9991f680bef4d3c0139b36ef4ff90d7d72f5`.

O gate `python -m tools.rooms.asset_provenance` falha se qualquer arquivo binário for adicionado, removido ou alterar bytes sem atualização explícita do manifesto; GitHub Actions e pytest verificam a mesma condição. Isto audita a **integridade do repositório**, não a integridade estrutural interna do SketchUp, o render, nem arquivos externos não versionados. Novo baseline exige revisão consciente, não bypass no CI.

A classificação `owner_group` é **agrupamento de pasta**, não avaliação artística, ergonomia ou comprovação de propriedade humana. A P6 permanece pendente para bibliotecas/arquivos não versionados e validação SketchUp L2/visual. A P5 ganhou teste de integridade referencial entre os dois catálogos de receitas, também consultivos e sem autorização de execução.
