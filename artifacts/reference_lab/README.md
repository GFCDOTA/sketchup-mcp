# Reference Lab — estúdio de tradução referência → marcenaria

> Operado pelo especialista [`reference-to-joinery-translator`](../../.claude/skills/reference-to-joinery-translator/SKILL.md).
> **Pinterest manda na linguagem. PDF manda na posição. Gates mandam na segurança. Felipe manda no PASS.**

## O que é
O lugar dos **exemplos aplicados** (estudos de caso) que ensinam o pipeline a pensar
como marceneiro/designer. Não é scraper, não baixa imagem em massa — o Felipe cura
1–5 referências boas e o agente destila em regra.

**10 cards bem feitos > 500 imagens.** O objetivo não é volume; é destilar referência
boa em regra implementável e provada num render.

## KB (`references/`) vs Lab (`artifacts/reference_lab/`)
- **`references/`** = o livro-texto (conhecimento geral, reusável): materiais,
  ergonomia, anti-padrões, paletas e **tokens** (fonte única dos tokens).
- **`artifacts/reference_lab/`** = o caderno de estudos de caso (exemplos concretos,
  com antes/depois e valores reais). Os tokens são **referenciados** de
  `references/tokens/`, não copiados.

## Estrutura
```
artifacts/reference_lab/
  README.md                         (este arquivo)
  kitchen/
    EXAMPLE_001_KITCHEN.md          ← a régua: cozinha planta_74 (antes/depois + lição)
    examples/                       ← Reference Cards (problema→solução→gate)
      integrated_fridge_tower.md
      fendi_kill_flat_white.md
      subtle_veined_backsplash.md
      under_cabinet_linear_led.md
      premium_shadow_gap.md
    specs/
      modern_warm_kitchen.json      ← DesignGrammarSpec do cômodo
```

## Índice
- **[EXAMPLE_001_KITCHEN](kitchen/EXAMPLE_001_KITCHEN.md)** — cozinha planejada
  compacta premium. Lição-raiz: `loose_object → planned_niche_system`. Status: GPT
  **PASS de pele**; veredito final do Felipe pendente.
- Cards: torre de geladeira integrada · matar branco chapado (fendi) · pedra de veio
  sutil · LED linear sob aéreo · shadow gap premium.
- Spec: [`modern_warm_kitchen.json`](kitchen/specs/modern_warm_kitchen.json).

## Como crescer o lab
Felipe cola uma referência → o especialista lê → cria/atualiza um Card + atualiza o
Spec → reusa/cria token em `references/tokens/` → aplica num componente → renderiza →
GPT julga → Felipe dá o PASS. Cada referência boa vira um Card novo aqui.
