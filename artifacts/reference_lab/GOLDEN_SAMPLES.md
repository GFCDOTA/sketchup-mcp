# Golden Samples — biblioteca de temas validados (planta_74 cozinha)

> Mesma geometria + mesma planta + mesmo layout PDF → múltiplas peles coerentes, julgadas
> por gates, corrigidas por feedback, viram preset reutilizável. Isto é **sistema de escolha
> de linguagem**, não render avulso. Congelado em [DECISIONS.md](DECISIONS.md) (DECISION 001).

| # | tema | papel | veredito | render |
|---|---|---|---|---|
| **001** | `warm_compact_premium` | **default seguro** — amplo, vendável, universal | GPT PASS de pele | `cozinha_vray_hero.png` |
| **002** | `dark_walnut_moody_premium` | **variante autoral** — noturna, masculina, impacto visual | GPT PASS variante | `cozinha_vray_hero_dark.png` |
| 003 | `hotel_boutique_warm_luxury` | premium equilibrado (entre clara e dark) | _em teste_ | `cozinha_vray_hero_boutique.png` |

## GOLDEN_SAMPLE_001 — warm_compact_premium
Fendi acetinado + carvalho coordenado + pedra clara veio sutil + inox reflexivo + LED 2700K +
grafite. Spec: [`kitchen/specs/modern_warm_kitchen.json`](kitchen/specs/modern_warm_kitchen.json).
Exemplo: [EXAMPLE_001](kitchen/EXAMPLE_001_KITCHEN.md).

## GOLDEN_SAMPLE_002 — dark_walnut_moody_premium
Preto fosco + nogueira contínua + inox dark + fixtures pretas + LED moody. Theme:
[`kitchen_dark_walnut/THEME_DARK_WALNUT_MOODY_PREMIUM.json`](kitchen_dark_walnut/THEME_DARK_WALNUT_MOODY_PREMIUM.json).
Exemplo: [EXAMPLE_002](kitchen_dark_walnut/EXAMPLE_002_KITCHEN_DARK_WALNUT.md).

## Como aplicar um tema (skin-swap, geometria congelada)
```
KITCHEN_THEME=<tema> PT_TO_M=0.0259 VRAY_ISOLATE=COZINHA \
  .venv/Scripts/python.exe .claude/scratch/kitchen_vray.py cozinha_vray_hero_<tema>.png
```
Temas: (vazio)=clara default · `dark_walnut` · `hotel_boutique`.
