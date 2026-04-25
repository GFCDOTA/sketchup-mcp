# preprocess/legacy/

Scripts originais de prototipo (p1..p12) que foram promovidos a producao.

**Estado: legado, nao usar em codigo novo.**

A funcionalidade equivalente esta em `preprocess/color_mask.py` e
`preprocess/skeleton.py`, exposta como API estavel via
`preprocess.apply_preprocessing(image, config)`.

Estes arquivos sao mantidos somente para:
- referencia historica das heuristicas exploradas
- reproduzir runs antigos em `runs/proto/p*` quando necessario para
  bisseccao de regressao

Para novos runs, use o flag `preprocess={"mode": "color_mask", "color": "auto"}`
em `run_pdf_pipeline` / `run_raster_pipeline`.

## Mapeamento proto -> producao

| Legacy script              | Producao                                      |
|---------------------------|-----------------------------------------------|
| proto_red.py              | preprocess.color_mask.extract_color_dominant_mask(color="red") |
| proto_colored.py          | preprocess.color_mask.extract_color_dominant_mask(color="auto") |
| proto_colored_dilate.py   | (nao promovido - dilate agressivo era hack temporario) |
| proto_colored_skel.py     | preprocess.skeleton.skeletonize_mask           |
| proto_skel.py             | preprocess.skeleton.skeletonize_mask           |
| proto_v2.py / proto_runner.py | (substituido pela API unificada apply_preprocessing) |
| preprocess_walls.py       | preprocess.color_mask (color="black")          |
