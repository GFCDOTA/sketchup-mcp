# Estúdio Banheiro — Placar do loop (GPT nota 0–10)

Referência: imagem gerada pelo GPT no chat fixo "Estúdio Banheiro — Claude ⇄ GPT"
(2026-08-05). Spec: `REFERENCE_SPEC.md`. Cena: `tools/estudio_banheiro_scene.py`
→ `runs/scenes/estudio_banheiro_v1` → V-Ray theme `estudio_banheiro`.

| Iter | Nota | Principais mudanças |
|------|------|---------------------|
| 01 | 4.4 | Primeira recriação (layout+materiais+luz base). |
| 02 | 5.9 | Câmera 4:5 vertical 1.60m ~37mm; nogueira escura flat; textura `stone_antracite_veins.png` (PIL); luz hierarquizada. |
| 03 | 6.8 | Espelho protagonista (halo transbordando); veios −45%; rain shower octogonal; ducha/comando maiores. |
| 04 | 7.4 | Perfis 22mm (decorative); câmera no limite do vão; espelho reflect real; nicho 65×20 LED full; fill +0.7 stop. |
| 05 | 7.6 | Roughness 0.02 no espelho; +0.5 EV meios-tons; lente 35mm; câmera 7cm esq. |
| 06 | **8.0** | Box iluminado por dentro (conteúdo pro reflexo do espelho); pedra com glints; cuba 44×33; tampo 50mm; nogueira −8%. |

## TOP3 pendentes (da it.6, para a it.7)

1. Espelho com conteúdo refletido legível em ≥50% (ângulo/ambiente refletido).
2. Box menos dominante: perfil frontal/puxador mais leves, câmera +2–3cm esq.
3. Bancada+cuba mais nobres: contraste tampo×cava, veios −10–15%.

## Gotchas do pipeline (pagos nesta sessão)

- `scene_closed.skp` é CACHEADO — deletar antes de re-render quando geometria muda.
- Faixa preta no render = região `rgn_/bmp_/r_` não acompanhava `img_width/height`
  (fix na causa em `tweak_vrscene.py`).
- Bridge `/ask` dá TIMEOUT quando o GPT pensa >~30s — a resposta ESTÁ no chat;
  ler via Chrome (`get_page_text`). Resposta só-imagem também devolve texto velho.
- Fill `LightSphere` invisible aparecia PRETA em reflexo → `affectReflections=0`.
- Espelho preto não era material: fisicamente refletia o interior escuro do box —
  iluminar o CONTEÚDO refletido é o fix honesto.

## Loop no banho REAL da planta_74 (2026-08-05, tarde)

| Iter | Nota | Principais mudanças |
|------|------|---------------------|
| p01 | 6.3 | Primeira com pele completa; GPT valida box parede-a-parede até o teto (janela dentro; pede exaustão). |
| p02 | 7.0 | Gabinete cascata 1.00m nobre; espelho cresce junto; +0.4 EV. |
| p03 | 7.3 | Cuba retangular esculpida; veios −15%; +0.25 EV box. |
| p04/p05 | 6.7 | Porta fora do 1º plano (VRAY_HIDE); burn na janela; box EIXO CURTO; fills longe de parede (mata discos) — mas cena escureceu. |
| p06 | 7.0 | Rectangle Light no box (lavou teto). |
| p07 | 7.2 | Rect baixa/inclinada; faixa dura de sombra. |
| p08 | **7.7** | Rect no TETO dentro do box (vidro segura a luz) = teto luminoso; faixa eliminada. |

TOP3 pendentes (p08→p09): espelho reflexo 25–40%; nicho/chuveiro/comandos
protagonistas (não só teto aceso); 1º plano +8–12% com contraste cuba×tampo.

Gotchas novos: fill esférica colada em parede projeta a própria silhueta
(disco escuro no halo) — manter ≥20in de qualquer parede; rect a meia altura
cria faixa de sombra — colar no teto dentro do box; expandir box no eixo LONGO
bloqueia circulação (usar eixo CURTO); vaso é adjacente à porta (PDF) — hero
cam não o inclui, restrição informada ao juiz.

## LIÇÕES TRANSFERÍVEIS — "cômodo do render = cômodo do .skp" (2026-08-05)

Receita pra QUALQUER cômodo que ganhar a pele do estúdio (aplicar nos demais):

1. **O .skp navegável precisa da MESMA pele do render** — senão o Felipe abre
   e "o cômodo não existe". Mecanismo: `tex_png`/`tile_in` POR PEÇA no brain
   (`_KIND_TEX`) + `alpha` por peça (`_KIND_ALPHA`, vidro=0.30) + furnish
   passando `LAYOUT_TEX_DIR` sempre. Nunca deixar material chapado no
   deliverable de peça que tem textura no render.
2. **Vidro até o teto = vidro ENCOSTA na laje (2.50), sem travessa-tampa.**
   A travessa superior full-footprint era uma PLACA preta (lia como teto do
   box). Perfil de topo só se for moldura fina na LINHA do vidro, nunca tampa.
3. **Laje de render (kb_teto) nasce OCULTA no .skp** (módulo PeleTeto;
   vray_export re-exibe). O SketchUp é pra navegar por dentro.
4. **Luz do render** (não existe no .skp, é normal): Rectangle Light no teto
   DENTRO do box; fills ≥50cm de qualquer parede (disco escuro); VRAY_HIDE
   nas folhas de porta do 1º plano; burn 0.5 pra janela.
5. **Posição vem do PDF; referência manda em linguagem/medida.** Box expande
   no eixo CURTO (nunca bloquear rota até o vaso); gabinete em cascata de
   tamanhos até caber; câmera hero parte da porta (o que fica adjacente à
   porta não entra no quadro — informar o juiz).

## STONE_MONOLITH — prompt oficial do Felipe (2026-08-05, noite)

Virada: sem madeira protagonista; monólito pedra greige; dourado ZERO; cuba
under-mount; espelho maior moldura preta; piso porcelanato área seca; box
antracite. Travas red→green (25/25).

| Iter | Nota | Mudanças |
|------|------|----------|
| p09 | — | Shaft respeitado (clip ao polígono) + porta de correr + chuveiro real + enxoval completo (consultoria GPT). |
| p10 | 7.4 | Primeira STONE_MONOLITH. |
| p11 | **7.8** | stone_greige_veins.png (PIL) + cuba mais funda + box +0.3EV. |

TOP3 (p11→p12): espelho reflexo 30–40%; pedra menos granulada (veios mais
longos/sutis, ruído −25%, separar tampo×cuba×frente); anatomia do box de correr
legível (sobreposição fixo×folha + puxador/trilho + interior +0.2EV).

## Correção de LAYOUT (reprovação do Felipe + consultoria GPT, 2026-08-05)

Felipe pegou de cima: vaso de frente pra porta, gabinete no shaft, chuveiro no
centro, vaso-quadrado. GPT especificou o layout; implementado:
`_directed_pia_vaso` (gabinete 78cm colado na entrada → vaso ao lado, DE LADO
pra porta), chuveiro 33cm do shaft/38cm do vidro, anatomia de privada
(caixa+botão, base estreita, bacia oval, assento/tampa).

| Iter | Nota | Mudanças |
|------|------|----------|
| p12 | **8.2** ⭐ | Layout correto + privada de verdade. RECORDE (lab parou em 8.0). |

TOP3 (p12→p13): box lendo como porta de correr premium (fixo×folha evidente,
sobreposição 4-6cm, puxador 30-40cm, trilho discreto); vaso menos facetado
(bacia/assento mais suaves, menos low-poly); espelho 30-40% reflexo + bancada
com contraste tampo×cuba×frente.

LIÇÃO: o olho do Felipe na PLANTA (top view) pega erro de layout que o render
hero esconde — sempre validar top view com ele antes de polir material/luz.
