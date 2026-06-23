# Estagiários do Arquiteto por TEMA + validação LOCAL de render

> Pedido do Felipe (2026-06-23): "estagiários do arquiteto separados por temas, cada um dono
> do seu tópico multi-schema; e como os agentes locais não veem imagem, traduzir o render pra
> algo que eles entendam e validem." Nasceu do furo que o Felipe apontou: *quem valida se os
> renders estão ficando bons?* (GPT/Felipe eram os únicos; faltava um checkpoint LOCAL.)

## A ideia
Cada **TEMA** (black_wood_gold, dark_walnut, hotel_boutique, warm_compact) é um **tópico com
schema próprio**: seu conjunto de checks + thresholds + anti-patterns + DNA. Cada tema tem um
**estagiário-dono** (perfil: persona + modelo local) que SÓ conhece o schema dele.

## A ponte "agente local não vê imagem" (tradução render→texto)
Híbrido honesto, alinhado ao princípio do projeto (**gate determinístico = verdade, LLM = consultivo**):

| camada | arquivo | papel |
|---|---|---|
| **fingerprint determinístico** | `render_fingerprint.py` | números do PNG: mean_lum (caverna), clipped_px (estouro), paleta dominante, calor, contraste, zonas 3x3. PIL+numpy, sem rede. **AUTORIDADE.** |
| **visão local** | `vision_describe.py` | `qwen2.5vl:7b` responde o semântico (estouro perceptual, fake-gold, hierarquia). **CONSELHO** (ruidoso → WARN-max). |
| **registry de temas** | `theme_registry.py` | cada tema = schema de checks (`det_field` decide; `vision`/`advisory` aconselha) + DNA + anti-patterns + estagiário. |
| **estagiário validador** | `theme_intern.py` | roda os checks (gate) → síntese do estagiário-LLM (taste 0-10 + porquê + próxima ação) → ledger por-tema. |

Regra dos checks (lição da verificação — `qwen2.5vl:7b` super-dispara cave/fake-gold e perde estouro sutil):
- check com `det_field` → o NÚMERO decide FAIL/WARN/PASS; a visão só escala PASS→WARN (**nunca** FAIL).
- check só-visão (`advisory`) → cap em WARN (a visão sozinha não derruba, porque é ruidosa).

## Uso
```
python -m tools.interior_studio.theme_intern <render.png> --theme black_wood_gold --log
python -m tools.interior_studio.render_fingerprint <render.png>          # só os números
```
Ledger: `.ai_bridge/interior_studio/intern_verdicts.jsonl` (progresso render-a-render = responde "está melhorando?").

## O que é confiável (medido na história proof/v1/v5/v6)
- **Eixo CAVERNA/exposição (determinístico)**: discrimina bem — proof PASS · v1 FAIL(mean26) · v5/v6 WARN(35/30).
  Pegou que minhas renders black/wood/gold estão **escuras demais** (o que o Felipe e o `qwen2.5vl` suspeitavam).
- **Eixo ESTOURO sub-clip**: o determinístico (clipped_px=0) NÃO pega o estouro perceptual da proof; a visão deveria,
  mas é ruidosa. **Gap conhecido.**
- **Eixos semânticos (fake-gold, metais, hierarquia)**: visão local NÃO confiável → advisory (WARN-max). Para o
  veredito FINAL de aparência, continua GPT/Felipe (este sistema é o checkpoint LOCAL barato, não o final).

## NÃO é
- NÃO substitui o veredito visual do Felipe/GPT (regra chrome-only). É o primeiro filtro local/barato.
- NÃO é "estagiários viram agentes pesados" — são PERFIS (dado) dispatcháveis; viram mais quando ≥2-3 temas pagarem.
