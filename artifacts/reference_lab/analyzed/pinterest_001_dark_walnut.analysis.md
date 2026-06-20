# Reference Analysis — pinterest_001_dark_walnut

> Exemplo TRABALHADO do agente v1 (system translator) sobre a 1ª referência real do Felipe
> (cozinha black + walnut moody). Demonstra as 10 saídas + os 4 gates.

## Sidecar
- **Fonte:** Pinterest print manual (curado pelo Felipe)
- **Ambiente:** cozinha contemporânea escura
- **O que gostei:** preto fosco + nogueira quente + LED sob o aéreo + metais pretos
- **O que NÃO copiar:** layout em L, ilha, coifa-caixa gigante de chaminé, piso-parede de madeira contínuo de mansão
- **Medidas visíveis:** nenhuma cotada (só proporções aparentes — HIPÓTESE)
- **Risco:** escurecer demais a cozinha compacta (caverna); madeira na zona molhada
- **Status:** virou tema (GOLDEN_SAMPLE_002 dark_walnut_moody, GPT PASS)

## 10 saídas
1. **Theme extraction:** preto/grafite ultra-fosco dominante; nogueira de veio expressivo
   (backsplash+tampo contínuos); LED quente 2700K lavando a madeira; metais pretos; alto
   contraste, sensação noturna/masculina/premium.
2. **Form/skin separation:**
   - FORMA: slab handle-less, coifa-caixa, torre cheia, gola/reveal. (só dentro do envelope PDF)
   - PELE: preto fosco, nogueira, fixtures pretas. LUZ: low-key quente. CÂMERA: baixa/íntima.
3. **Dimension hints (HIPÓTESE):** aéreo aparenta ~full-height até teto alto; coifa proeminente.
   → **não cravar**: pé-direito da planta_74 ≠ o da foto; valida na ergonomia.
4. **Ergonomics notes:** aéreo até o teto só se o pé-direito permitir alcance; coifa-caixa
   grande rouba circulação em cozinha estreita → usar slim/embutida. Bancada precisa manter
   área de apoio (o print foca na estética, não no uso).
5. **Maintenance notes:** preto fosco MARCA digital e pega poeira → quebrar com madeira (ok no
   tema); madeira no tampo/backsplash na pia/cooktop MANCHA/incha → `wood_wetzone_gate`
   (selar ou inserto). Nogueira escura + pouca luz = difícil de ver sujeira mas vira caverna.
6. **Buildability notes:** slab preto fosco + nogueira = marcenaria padrão (executável). A
   coifa-caixa com tela perfurada é peça especial/cara → simplificar pra slim embutida.
7. **What to copy:** tema (preto+nogueira), paleta, textura de veio, LED linear, sensação moody.
8. **What to adapt:** intensidade de luz (LED mais forte; key pra não virar caverna); coifa
   (slim, não caixa gigante); geladeira (inox-dark, não bloco morto); proporção ao compacto.
9. **What to reject:** layout em L; ilha; coifa-chaminé gigante; madeira contínua piso→parede
   de mansão; qualquer vão aberto que pegue poeira.
10. **Theme preset:** [`themes/DARK_WALNUT_MOODY_PREMIUM.json`](../themes/DARK_WALNUT_MOODY_PREMIUM.json)
    (KITCHEN_THEME=dark_walnut). Aplicado na planta_74, GPT PASS.

## Veredito dos 4 gates
| gate | veredito | nota |
|---|---|---|
| theme_fit_gate | **PASS** | funciona no compacto como variante autoral (GPT: não virou caverna) |
| ergonomics_gate | **PASS** | geometria congelada da planta_74 (12 medidas já PASS); coifa mantida slim |
| maintenance_gate | **WARN** | preto fosco marca digital + madeira na zona molhada → exige selagem/inserto (`wood_wetzone_gate`) |
| buildability_gate | **PASS** | slab + nogueira executável; coifa simplificada pra slim |

**Conclusão:** referência virou SISTEMA, não cópia. Tema aprovado; o único cuidado real é
manutenção (selagem da madeira na zona molhada) — registrado, não bloqueia o tema.
