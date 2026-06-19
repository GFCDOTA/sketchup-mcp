# CARD: LED linear sob aéreo

**Problema:** cozinha fica chapada e sem profundidade. E o erro comum ao "tentar" LED:
luzes pontuais que viram **hotspots meia-lua** — chamam mais atenção que a pedra e dão
"cara de render/teste".

**Solução:** **fita linear** quente 2700K–3000K (uma área de luz comprida e fina, não
pontos) lavando o backsplash de forma uniforme. No V-Ray = `LightRectangle` fino e longo
sob o aéreo, normal apontando p/ parede + baixo.

**Aplicável em:** sob aéreo, sob nicho, sob prateleira, dentro de torre.

**Gate:**
- não parecer neon (cor 2700K quente, não saturada).
- não estourar a exposição (intensidade calibrada; aqui ~8–9 radiância).
- contínuo — nunca hotspots pontuais.

**Valores (golden sample):** `LightRectangle` center (62, 648, 56.5), `normal (−0.37,0,−0.93)`
(wall+baixo), u_size 50 / v_size 2.5, cor (1.0, 0.74, 0.45) ≈ 2700K. Substituiu 2 esferas
que faziam meia-luas.

**Token:** `references/tokens/under_cabinet_led.json`

**Evidência:** GPT — *"o LED virou faixa contínua e sumiu a cara de dois spots de teste;
agora lava melhor o backsplash"*. Helper em `tools/tweak_vrscene.py::_light_rectangle`.
