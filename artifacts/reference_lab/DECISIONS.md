# Reference Lab — Decisions

## DECISION 001 — REFERENCE_TO_JOINERY_TRANSLATOR v0 validated (2026-06-19)

```
DECISION:
REFERENCE_TO_JOINERY_TRANSLATOR v0 validated.

Evidence:
- EXAMPLE_001 warm compact kitchen: GPT PASS
- EXAMPLE_002 dark walnut moody kitchen: GPT PASS
- Same geometry, distinct skins
- No PDF/layout violation
- Gates detected and fixed material issue (geladeira bloco morto -> inox dark)

Rule learned:
Theme may change skin/material/light/camera.
Theme must NOT change PDF anchors or approved geometry unless explicitly authorized.
```

### O que o pipeline provou (4 coisas)
1. Referência virou **tema**, não cópia.
2. Tema virou **skin-swap**, não rebuild.
3. **Gate pegou problema real**: geladeira bloco morto.
4. **Correção foi material/luz**, não gambiarra geométrica.

### Congelado por esta decisão
- ❄️ Geometria da cozinha planta_74.
- ❄️ `warm_compact_premium` como tema **default** (GOLDEN_SAMPLE_001).
- ❄️ `dark_walnut_moody_premium` como **variante validada** (GOLDEN_SAMPLE_002).
- ❄️ Reference translator pipeline **v0**.

Ver [GOLDEN_SAMPLES.md](GOLDEN_SAMPLES.md).
