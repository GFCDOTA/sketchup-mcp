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

---

## DECISION 002 — 3 golden samples ABENÇOADOS pelo Felipe (2026-06-19)

```
🏆 GOLDEN SAMPLES APROVADOS (veredito final Felipe)
001 warm_compact_premium      PASS — default seguro / vendável / amplo
002 dark_walnut_moody         PASS — autoral / noturno / impacto
003 hotel_boutique_warm_luxury PASS — equilibrado / refinado / premium
```

**Regra de ouro dos papéis:**
```
A clara VENDE.
A dark IMPRESSIONA.
A boutique CONVENCE.
```

**Ranking do Felipe pro apê real (hoje):** 1º hotel_boutique · 2º warm_compact · 3º dark_walnut.
(boutique = melhor equilíbrio bonita/não-cansa/parece-cara/funciona-em-compacto.)

Marco de cozinha como prova de conceito do tradutor: **FECHADO e validado.** Próxima fase =
ampliar a biblioteca com mais temas (BLACK_WOOD_GOLD) + evoluir o agente p/ inteligência de uso.

---

## DECISION 003 — preferências reais do Felipe viram RESTRIÇÃO do agente (2026-06-19)

O que o Felipe gostou/não-gostou nesta rodada vira regra inteligente, não achismo. Registrado
em [FELIPE_KITCHEN_PREFERENCES.md](FELIPE_KITCHEN_PREFERENCES.md). Direção alvo:
**BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE** (preto fosco + madeira natural quente + pedra escura/
quente com veios dourados SUTIS + cuba preta + torneira preta/bronze + bronze discreto + LED 2700K).
**Regra:** não escolher material definitivo ainda — gerar variações, julgar A/B/C, e só depois
descer pra pedra/cuba/manutenção/custo.

---

## DECISION 004 — black_wood_gold CONGELADO como GOLDEN_SAMPLE_004 (2026-06-20, Felipe)

```
VEREDITO FINAL (Felipe): CONGELAR como GOLDEN_SAMPLE_004 (black_wood_gold).

A cozinha está aprovada como referência oficial de:
- linguagem · materialidade · paleta · marcenaria · integração de eletros · qualidade visual

NÃO alterar mais: geometria · layout · pia · módulos · paleta · conceito.
```

**Caminho percorrido (tudo validado):** forma validada · pia no ponto do PDF · ergonomia/
modulação validadas (ref de cotas confirmou `kitchen_ergonomics`) · linguagem definida (17 refs
do Felipe unânimes em dark+wood) · paleta/material aprovados · V-Ray hero em nível de
apresentação (loop GPT: PASS de design/material) · `.skp` bakeado e aberto. **O resto agora é
microacabamento, não projeto** — parar antes de "polir até estragar".

**Artefatos:** `.skp` = `artifacts/planta_74/furnished/planta_74_furnished_black_wood_gold.skp`;
hero = `kitchen_angles/cozinha_skp_blackgold_hero_final.png`; theme =
`themes/BLACK_WOOD_GOLD_INDUSTRIAL_BOUTIQUE.json`; exemplo =
`kitchen/EXAMPLE_BLACK_WOOD_GOLD.md`.

**Próximo:** (1) cozinha = exemplo-base do agent; (2) documentar tokens/regras; (3) propagar o
método pro próximo ambiente (sala).
