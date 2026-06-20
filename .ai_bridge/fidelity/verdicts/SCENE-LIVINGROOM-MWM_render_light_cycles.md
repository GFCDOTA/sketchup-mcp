# SCENE-LIVINGROOM-MWM — fase RENDER, ciclos de LUZ (2026-06-11)

- **Juiz:** ChatGPT (web, GPT-5 thinking "Alto"), mesma conversa do track.
  Chat: https://chatgpt.com/c/6a2b600b-3800-83e9-bfe9-dbea5da1596e
- Composicao = PASS limpo (cycle003); geometria INTOCADA nesta fase.

## Ciclos julgados

| pass | receita | veredito |
|---|---|---|
| baseline (@d795be6) | iso100 f7 sh160 sky0.3 sun1.0 | **BROKEN** — subexposto no interior, janela estourada/recortada, patch de sol "holofote", sem bounce |
| pass5 (@063c489) | iso200 sky0.9 sun0.55 | **AINDA_NEEDS_WORK** — melhorou; alcance dinamico mal equilibrado (1o plano estoura, sofa/fundo comprimidos); janela segue buraco |
| pass6 (@d6ae2e7) | + sun_size=6 (penumbra larga) + 2 fills warm (janela int5 + lado sofa int3) | **AINDA_NEEDS_WORK** — "a luz interna melhorou, o patch esta mais suave e os fills ajudaram"; falta SO a janela |

## O UNICO ajuste que falta (palavras do juiz)

> "Resolver a JANELA como fonte luminosa crivel — exterior/sky visivel e calibrar a
> abertura para ela parar de ser um buraco preto com borda explodida. Depois que a
> janela estiver 'viva' e com transicao luminosa plausivel, ai sim eu passaria
> para materiais."

**Caminho tecnico candidato (proximo ciclo):** highlight compression no color mapping do
.vrscene (SettingsColorMapping burn/type — Reinhard burn <1 comprime o ceu estourado e
revela gradacao na janela) e/ou plano-billboard exterior simples atras do vao. Implementar
via set_block_param (mesmo mecanismo de sun/sky), expor --burn no render_scene_vray.

## Aprendizados tecnicos do ciclo (ja commitados)

- `tweak --sky` antigo invertia a intencao: regex global pegava so o 1o intensity_multiplier
  (TexSky) — `set_block_param` agora seta TexSky (ambiente) e SunLight (sol) SEPARADOS.
- sun <= 0.2 mata o bounce (o sol e' a fonte primaria do interior); domar patch = sun_size
  (penumbra), nao intensity.
- O brilho na poltrona creme vem da LUZ DA JANELA sobre material claro — fix de material.
- Fills em METROS no render_scene_vray --fill "x,y,z,int[,raio];...".

## 2026-06-11 (madrugada) — LUZ APROVADA ✅

| pass | receita | veredito |
|---|---|---|
| pass7 (@e170490) | + _flatten_alpha (RGBA->RGB) + burn 0.35 | NEEDS_WORK — "janela deixou de sabotar, ótimo; gargalo = contraste interno" |
| pass8 (@124c3a7) | sun 0.38 size8 + fills 8/6/4 + burn 0.3 | **APROVADA_SEGUIR_PARA_MATERIAIS** |

> "O patch ainda existe, mas deixou de ser o erro principal; a janela está crível, o
> ambiente tem leitura, e o que ainda parece pesado vem mais de material escuro/chapado
> do que de exposição."

**DESCOBERTA RAIZ da "janela morta" (3 ciclos):** o V-Ray escreve o background com
**alpha=0** — o RGB do céu SEMPRE esteve no arquivo; browser/visualizador mostra
transparente como branco. Fix: `_flatten_alpha` no orquestrador.

**RECEITA DE LUZ APROVADA (congelar):** `--iso 200 --sky 1.1 --sun 0.38 --sun-size 8
--burn 0.3 --fill "4.7,2.4,1.7,8,0.4;1.6,3.4,2.0,6,0.35;2.6,2.0,2.2,4,0.4"`

**ORDEM DOS MATERIAIS (juiz):** 1) SOFÁ (quase-preto -> charcoal/marrom quente,
reflectance maior, roughness de tecido, microvariação; braço/assento/encosto legíveis);
2) TAPETE (textura sutil, variação tonal, leitura de fibra); 3) PISO (madeira sem
"plano laranja", veio + roughness natural). "Não mexeria mais no sol/fill antes desses três."
