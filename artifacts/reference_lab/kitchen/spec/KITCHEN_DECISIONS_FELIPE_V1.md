# KITCHEN_DECISIONS — Felipe v1 (2026-06-20)

> Decisões batidas pelo Felipe sobre o COMPLETE_KITCHEN_SPEC. **NÃO implementar default
> automático** — estas são as escolhas oficiais. Isto é `KITCHEN_MATERIAL_SPEC_LAB`:
> camada de spec/material, **NÃO reabre o GOLDEN_SAMPLE_004** (geometria/pia/layout/módulos
> CONGELADOS; mudança só com aprovação explícita).

## D1–D9 (decisões oficiais)
| # | Decisão | Escolha do Felipe |
|---|---|---|
| **D1** | Cooktop | **Indução** 4 zonas vidro preto — **condicionado a confirmar 220V/circuito dedicado**; fallback gás/vidro preto se a infra não permitir |
| **D2** | Airfryer | **Nicho ventilado** (torre quente ou armário técnico) — nunca solta na bancada |
| **D3** | Coifa | **Slim depurador preto/grafite** (default); duto só se o prédio permitir + fizer sentido na obra |
| **D4** | Bronze/dourado | **Sutil, 1 ponto só** — candidato: torneira champagne/bronze OU detalhe fino do nicho/LED. NÃO espalhar dourado |
| **D5** | Cuba | **Render: preta undermount.** Execução real PENDENTE entre inox escovado/grafite e cuba preta premium → criar `maintenance_check` específico da cuba preta |
| **D6** | Lava-louças | Obrigatória. Default **45cm integrável**; testar 60cm só se não prejudicar armazenamento/circulação |
| **D7** | Pedra | **Default: porcelanato/lâmina preto-dourado MATE, veio controlado/elegante.** Dekton Laurent = premium; quartzito natural = alternativa c/ selagem; **mármore descartado** |
| **D8** | Geladeira | **Black inox/preto fosco inverse.** Testar nicho 75×70 como VARIANTE, mas **NÃO alterar módulos sem validar circulação/scorecard** |
| **D9** | Piso | **Porcelanato cimento/concreto grafite MÉDIO acetinado, contínuo cozinha+sala.** Não preto absoluto. Não amadeirado escuro na cozinha agora |

**Bloqueador de ordem:** D1 (cooktop) e D3 (coifa) mudam a infra → bater ANTES do elétrico/hidráulico.

## Direção alvo (Felipe): MOODY PREMIUM com manutenção inteligente
`black_wood_gold + pedra escura veio dourado CONTROLADO + piso cimento queimado médio fosco + LED quente`.
Cara de Felipe, sem virar caverna nem showroom brega. **Não voltar pro claro.**

## Matriz de 3 variantes (NÃO sobrescrever GOLDEN_SAMPLE_004)
| Variante | Pedra | Piso | Geladeira | Luz | Papel |
|---|---|---|---|---|---|
| **A** Golden preservado | atual | neutro | inox-dark atual | atual | baseline seguro de comparação |
| **B** Felipe moody premium ⭐ | preto-dourado mate veio **controlado** | cimento grafite médio | **black inox** | LED quente | **candidata principal** |
| **C** Stress test dark luxury | **nero-gold** marcado | mais escuro | preta | dramática | só testa limite cave/fake-luxury — NÃO default |

**Gates obrigatórios por variante:** `cave_check` · `fake_luxury_check` · `maintenance_check`
(+ cuba preta) · `continuity_check` (conversa c/ a sala) · ergonomia/circulação · GPT critique → Felipe decide.

**Regra:** B é a candidata; A é o baseline seguro; C é stress test. Não alterar geometria
congelada do GOLDEN_SAMPLE_004 sem aprovação explícita.
