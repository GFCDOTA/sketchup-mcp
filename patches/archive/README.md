# Patches archive — adiados / gated

Patches aqui **não** são para aplicação normal. Ficam arquivados para
referência histórica e para caso um spike isolado queira revisitá-los.

Veredictos finais consolidados em `../../docs/SOLUTION-FINAL.md` (seção
"Per-patch verdict"). Resumo:

| Patch | Status | Por que está arquivado |
|---|---|---|
| `07-reconnect-fragments-FIXED.py` | **ADIADO** | Depende de `scipy` (não listado em `requirements.txt`). `morph close` funde gaps de porta reais — confirmado empírico. Não aplicar sem spike isolado com `scipy` adicionado à stack e teste de regressão contra portas genuínas. |
| `08-unet-oracle-FIXED.py` | **ADIADO** | Sem offline fallback para weights do CubiCasa5K; depende de Google Drive em runtime. `strict=False` silencioso em `load_state_dict` viola CLAUDE.md §6 (proibido silenciar keys ignoradas). Não aplicar sem pipeline offline de weights + CI vendoring + SHA pinning. |
| `09-afplan-convex-hull.py` | **APROVADO apenas atrás de flag** | Melhor dos três extractors alternativos, mas GPT-4 consultado considerou inferior por introduzir blobs sem trocar classe de bug. Só aceitar atrás de `SKM_EXTRACTOR=afplan` via env, nunca como default. Mantido aqui até alguém decidir integrar o flag. |

## Contexto

O fix real que resolveu a planta despedaçada foi a combinação dedup
colinear + re-extração adaptativa, já integrada no main
(`classify/service.py` + `extract/service.py` desde `a11724a`). Ver
`../README.md` para detalhes.

O ingest atual é SVG-first (ver `../../docs/SVG-INGEST-INTEGRATION.md`);
o raster virou fallback legado. Patches 07/08 foram desenhados para
o pipeline raster e precisariam ser reavaliados à luz da nova
arquitetura antes de qualquer aplicação.

## Se for reativar um patch arquivado

1. Reler o veredicto em `../../docs/SOLUTION-FINAL.md`.
2. Abrir branch dedicado (`spike/patch-NN-...`).
3. Adicionar dependências ao `requirements.txt` (patch 07 → `scipy`;
   patch 08 → `torch`, `torchvision`, `gdown`, `scikit-image`).
4. Rodar `pytest` + comparar runs em `planta_74.pdf` e `p12_red.pdf`.
5. Não fazer merge sem overlay visual antes/depois
   (regra do CLAUDE.md do projeto).
