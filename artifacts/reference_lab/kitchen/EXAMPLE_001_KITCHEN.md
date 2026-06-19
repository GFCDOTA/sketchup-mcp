# EXAMPLE_001 — Cozinha planejada compacta premium (planta_74)

> O primeiro exemplar golden do lab — a régua de qualidade. Toda referência nova é
> comparada com este caso.

**reference_intent:** cozinha planejada compacta premium (apto 74m², layout linear FIXO).

## Antes → Depois
| | ANTES | DEPOIS |
|---|---|---|
| Forma | "Minecraft" — blocos soltos, geladeira jogada no canto | Torre de geladeira **integrada** (nicho planejado) |
| Cor | branco chapado (lê MDF barato) | **fendi** quente acetinado em cima + **carvalho** claro coordenado embaixo |
| Bancada | cinza liso (parede pintada) | **pedra clara com veio sutil** (tampo + backsplash contínuos) |
| Metal | inox fosco sem vida | inox **reflexivo** (metalness) |
| Luz | flat, sem profundidade | **LED linear quente 2700K** lavando o backsplash + grafite fosco |

**Evidência:**
- Antes/depois: [`cozinha_antes_depois.png`](../../planta_74/furnished/kitchen_angles/cozinha_antes_depois.png)
- Hero V-Ray: [`cozinha_vray_hero.png`](../../planta_74/furnished/kitchen_angles/cozinha_vray_hero.png)
- Montagem 3 ângulos: [`cozinha_vray_montagem.png`](../../planta_74/furnished/kitchen_angles/cozinha_vray_montagem.png)

## Lição-raiz
**`loose_object → planned_niche_system`** — o gesto que separa "blocos do Minecraft"
de "cozinha planejada de verdade". Cada eletro/objeto solto vira um nicho com laterais,
frente flush, filler, respiro e material coordenado.

## O caminho (loop GPT-validado, geometria CONGELADA)
Cada passo foi um defeito de PELE que o GPT (designer de interiores) apontou → regra →
fix → re-render → veredito. **Sem mover pia/parede/porta/módulos.**

1. **Brancão** → BRDF coordenado dos `kc_*` (inox reflexivo, fendi acetinado, pedra
   polida, madeira satin). GPT: "resolveu o brancão".
2. **2 hotspots meia-lua de LED** ("cara de render/teste") → **LED linear** contínuo
   (`LightRectangle`). GPT: "sumiu a cara de teste".
3. **Vazio lateral matando a apresentação** → **reframe** (FOV/crop fechados,
   centralizado, mostra bancada). GPT: "lê como hero de cozinha".
4. **Backsplash chapado** ("parede mineral fosca") → **pedra de veio sutil** (textura
   `A_quartzo_fio`, FFT tileable). GPT: "ficou no ponto, sem virar mármore dramático".
5. **Granulação** → denoise/samples (noise 0.04→0.012, shade 6→14). Resíduo técnico.

**Veredito GPT:** PASS de pele — *"congelaria a pele; o resíduo é só técnico, não
conceito de material."*
**Veredito Felipe:** _pendente_ (golden sample só com o OK dele).

## Cards aplicados neste exemplo
- [Torre de geladeira integrada](examples/integrated_fridge_tower.md)
- [Matar branco chapado (fendi)](examples/fendi_kill_flat_white.md)
- [Pedra de veio sutil](examples/subtle_veined_backsplash.md)
- [LED linear sob aéreo](examples/under_cabinet_linear_led.md)
- [Shadow gap premium](examples/premium_shadow_gap.md)

## Spec
[`specs/modern_warm_kitchen.json`](specs/modern_warm_kitchen.json)

## Forbidden moves (âncoras do PDF)
não mover pia · não mover portas · não alterar parede · não inventar ilha · não mudar
o layout linear do PDF.
