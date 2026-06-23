# Juízes de Render por TEMA — validação LOCAL de render (imagem)

> Pedido do Felipe (2026-06-23): "validadores temáticos, cada um dono do seu tópico multi-schema;
> e como os agentes locais não veem imagem, traduzir o render pra algo que eles entendam e validem."
> Nasceu do furo que o Felipe apontou: *quem valida se os renders estão ficando bons?* (GPT/Felipe
> eram os únicos; faltava um checkpoint LOCAL.)

> **Desambiguação:** distinto dos **"Estagiários do Arquiteto"** (`interns.py`), que validam o
> **PROGRAMA de mobília** (texto). Aqui o **JUIZ DE RENDER** valida o **RENDER** (aparência/imagem).
> São estágios complementares: programa antes da geometria · render depois.

## A ideia
Cada **TEMA** (black_wood_gold, dark_walnut, hotel_boutique, warm_compact) é um **tópico com
schema próprio**: seu conjunto de checks + thresholds + anti-patterns + DNA. Cada tema tem um
**juiz-de-render-dono** (perfil: persona + modelo local) que SÓ conhece o schema dele.

## A ponte "agente local não vê imagem" (tradução render→texto)
Híbrido honesto, alinhado ao princípio do projeto (**gate determinístico = verdade, LLM = consultivo**):

| camada | arquivo | papel |
|---|---|---|
| **fingerprint determinístico** | `render_fingerprint.py` | números do PNG: mean_lum (caverna), near_black_pct (sombra esmagada), clipped_px (estouro), paleta, calor, contraste, zonas. PIL+numpy, sem rede. **AUTORIDADE.** |
| **visão local** | `vision_describe.py` | `qwen2.5vl:7b` responde o semântico (estouro perceptual, fake-gold, hierarquia). **CONSELHO** (ruidoso → WARN-max). |
| **registry de temas** | `theme_registry.py` | cada tema = schema de checks (`det_field` decide; `vision`/`advisory` aconselha) + DNA + anti-patterns + juiz. |
| **juiz validador** | `render_judge.py` | roda os checks (gate) → síntese do juiz-LLM (taste 0-10 + porquê + próxima ação) → ledger por-tema. |

Regra dos checks (lição da verificação — `qwen2.5vl:7b` super-dispara cave/fake-gold e perde estouro sutil):
- check com `det_field` → o NÚMERO decide FAIL/WARN/PASS; a visão só escala PASS→WARN (**nunca** FAIL).
- check só-visão (`advisory`) → cap em WARN (a visão sozinha não derruba, porque é ruidosa).

## Uso
```
python -m tools.interior_studio.render_judge <render.png> --theme black_wood_gold --log
python -m tools.interior_studio.render_fingerprint <render.png>          # só os números
```
Ledger: `.ai_bridge/interior_studio/render_judge_verdicts.jsonl` (progresso render-a-render = responde "está melhorando?").

## Confiança (verificação adversarial — 4 juízes Claude-visão independentes, trust 6/10)
- **Eixo CAVERNA/exposição (determinístico)**: discrimina e RANKEIA bem — proof PASS · v1 FAIL(mean26) ·
  v5/v6 WARN(35/30). Monotônico, bate com o olho. Pegou que minhas renders black/wood/gold estão **escuras demais**.
- **`crushed_shadows`** (near_black_pct): adicionado pelo achado unânime da verificação — a `mean_lum` é
  enganada por uma janela clara (split-exposure) e mascara que metade da sala some no preto.
- **Eixo ESTOURO sub-clip / semânticos (fake-gold, metais, hierarquia)**: visão local NÃO confiável → advisory
  (WARN-max). **Gap conhecido.**
- **Veredito:** confiável pra **trackear/rankear progresso**, NÃO pra dar PASS absoluto.

## NÃO é
- NÃO substitui o veredito visual do Felipe/GPT (regra chrome-only). É o primeiro filtro local/barato.
- NÃO é "juízes viram agentes pesados" — são PERFIS (dado) dispatcháveis; viram mais quando ≥2-3 temas pagarem.
