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

## Pós-auditoria impiedosa (2026-08-05)

Auditoria p12 no rigor máximo: 21 defeitos, régua re-calibrada pra 7.1
(AUDITORIA_P12.md). Ataque ao cluster "look CG":

| Iter | Nota | Mudanças |
|------|------|----------|
| p13 | **8.0** | Piso porcelanato greige CALMO (novo, junta fina) + antracite limpo no box; vaso/chuveiro 16 lados; caixilho + vidro fosco na janela; folha offset 6.5cm + guia; escalas de tile revisadas. (+0.9 em 1 ciclo) |

TOP3 (p13→p14): espelho 30-40% + câmera 3-5cm esq/trás (mostrar cuba+tampo);
box interior +0.2-0.3EV com vidro menos leitoso; monolito com veio mais sutil
+ separação tampo×cuba×frente (menos caixa reta).

## Rumo ao APROVADO_DESIGN (critério do Felipe: parada = veredito de designer)

| Iter | Nota | Veredito | Mudanças |
|------|------|----------|----------|
| p14 | — | — | Privada REDONDA (24 gomos + soft/smooth arestas verticais — padrão do sofá). |
| p15 | 8.1 | AINDA_NÃO | Vidro alpha 0.22 + shadow gap sob tampo + box +0.3EV + câmera recuada. |
| p16 | 8.4 | AINDA_NÃO | Trilho fino + rect fundo (mata barra branca) + tampa suave + espelho inteiro no quadro. |
| p17 | **8.6** ⭐ | AINDA_NÃO | WASH na parede oeste = conteúdo real pro espelho + pedra "ganhou vida" + puxador presente. |

TOP3 (p17→p18): espelho 30-40% reflexo (borda esquerda com intenção);
fixo×folha mais claros + vidro menos leitoso (alpha ~0.16?) + nicho/chuveiro/
misturador revelados; câmera 2-4cm trás/esquerda — 1ª leitura = espelho+
bancada+box, não parede lateral.

| p18 | **8.8** ⭐ | AINDA_NÃO | Montante preto no bordo da folha (correr inequívoco) + alpha 0.16 + câmera trás/esq + wash +2. GPT: "anatomia da porta de correr agora está clara". |

TOP3 (p18→p19): espelho protagonista (conteúdo real 30-40%, halo mais sutil,
peça inteira enquadrada); bancada hero (câmera recuar/abrir +2-4cm, cuba
under-mount + shadow gap, 1ª leitura = lavatório+espelho); box refino final
(nicho/misturador/chuveiro legíveis, menos massa na parede direita, vidro
INCOLOR sofisticado — não leitoso).

| p19 | **9.0** ⭐ | AINDA_NÃO | Folha no theme glass INCOLOR (a cor SU esverdeada era o "leitoso") + halo −20% + wash direita +25% + câmera recuada/alta (espelho inteiro + bancada presente). |

TOP3 (p19→p20): espelho 25-35% conteúdo real, preto menos absoluto, halo ainda
mais refinado; parede direita pesa — textura/luz útil OU cortar mais no
enquadramento (leitura = lavatório+espelho+box); refino portfólio — transição
tampo/frente/shadow gap suave, cuba under-mount nítida, nicho+misturador+
chuveiro presentes.

| p20 | **9.2** 🏆 | **SIM — APROVADO_DESIGN** | Espelho diffuse 5x (preto menos absoluto) + shadow gap void matte + cuba c/ reflexo leve + metais glint + pan esq + wash 34/rect 62. |

| p21 | **9.4** 🏆 | **SIM** | KIT CURADO PELO FELIPE (front :8788): torneira Unic bica baixa + gabinete 2 frentes Elite-like (sai nicho de toalhas; trava atualizada) + ducha de PAREDE FlexMax Ø22 + cuba Slim. Curadoria→builder→render→nota em 1 ciclo. |

TOP3 residual (p21→polish): espelho 20-30% reflexo legível; braço da ducha
mais fino + cabeça mais circular; montante do box cortando janela/chuveiro na
hero (câmera uns cm). Referências reais: REFERENCE_KIT_PRODUTOS.md + fotos em
reference_lab/inbox/kit_banho01/.

## 🏆 APROVADO_DESIGN (2026-08-08) — critério de parada do Felipe ATINGIDO

Placar do banho real: 6.3 → … → 8.6 (p17) → 8.8 (p18) → 9.0 (p19) → **9.2 (p20)
com APROVADO_DESIGN: SIM**. Heroes de portfólio (1500×1875, shutter 75):
`kitchen_angles/banho01_stone_HERO.png` + `banho01_stone_HERO_lavatorio.png`.

TOP3 residual do juiz (polish NÃO-bloqueante, se o Felipe quiser ir além):
espelho 20-30% reflexo útil sem perder mood; veio da bancada mais suave +
antracite da direita menos "massa contínua"; (feito) hero em alta resolução.

Cmd final congelado:
`--eye "520,634,64" --target "533.5,567,45" --fov 60 --iso 160 --shutter 80
--fnum 5.6 --sky 0.16 --sun 0.05 --burn 0.5 --hide "porta,door"
--fill "534,585,72,30,10;525,546,68,36,8;528,588,88,18,10;520,610,72,12,10;523,584,55,34,9;523,596,76,34,9"
--rect "521,545,93,22,16,62,0,0,-1"`

GOTCHA reconfirmado: resposta do /ask em <20s idêntica à anterior = STALE
(streaming não detectado) — SEMPRE conferir no Chrome antes de agir.
GOTCHA novo (2026-08-08): /ask 504 "streaming não começou" ≠ falha — a msg
POSTOU e o GPT respondeu; ler o chat fixo pelo Chrome real (get_page_text)
antes de reenviar (não duplicar o pedido).

| p22 | **9.5** 🏆 | **SIM** | Vaso refeito com anatomia ROCA GAP real (feedback direto do Felipe: "por que manteve esse vaso zuado?") — rounded-rect, saia fechada, caixa slim. |

## Tema POR CÔMODO (2026-08-08, pedido do Felipe "muda o tema deles")

Mecanismo: `bathroom_layout.THEMES` sufixa o `mat_name` por sala (o .rb usa
`b[mat_name] || ph_<kind>`), então cada banheiro tem pele própria e o BANHO 01
(9.6) fica CONGELADO. `tweak_vrscene` pinta os sufixos; `render_banho_auto`
enquadra/ilumina qualquer banho pela receita aprovada no 01.

| Cômodo | Tema | p24 | p25 |
|--------|------|-----|-----|
| BANHO 01 | STONE_MONOLITH (congelado) | 9.6 | — |
| BANHO 02 | OAK_SERENO (paredes claras, piso grafite, carvalho seco) | 8.7 | **8.8** |
| LAVABO | NERO_ARDOSIA (monólito escuro, espelho protagonista) | 8.4 | **8.6** |

Juiz: "FAMILIA: SIM — os três conversam por pedra/mineralidade, metais pretos e
luz quente, sem repetir". TOP3 aberto: parede do box do 02 áspera demais
(concrete → limestone homogêneo −30/40%); câmera do 02 mostrando mais
bancada+carvalho; lavabo precisa da ardósia VEINADA expressiva na parede da
bancada (hoje ficou clara — perdeu ousadia).

GOTCHAS pagos aqui: (1) `PT_TO_M=0.0259` tem que estar no env ANTES de importar
o brain, senão as coords saem 1.36x e a câmera aponta pro vazio (render PRETO);
(2) câmera a <8in da pele = preto total; (3) fill a <18in de parede projeta a
própria silhueta (discos escuros no espelho) — clampar sempre.

## BEAUTY PASS 01 (2026-08-08) — layout congelado, só qualidade de render

Pedra menos granulada (glossiness+4%) + tampo/frente separados por VALOR
(tampo mais claro/polido, frente mais fosca) + vidro mais limpo/incolor
(opacity 0.08) + espelho preto menos absoluto + metais com glint controlado +
noise_threshold exposto no render_banho_vray (0.008 @ 1600x2000 = ruido
praticamente zero). Nota do juiz: **9.3/10**, ganho confirmado em modelagem/
materiais/luz/render-pos. TOP3 aberto: espelho ainda o ponto mais fraco;
parede direita pesa na hero (câmera mais aberta/esquerda); nicho/misturador/
ducha podem ganhar beauty pass LOCALIZADO de luz.

## Espelho — light slot (2026-08-08, modo YOLO)

Diagnostico confirmado com imagem do GPT gerada p/ comparacao: o espelho
reflete fisicamente a parede escura do box, sem conteudo — nao era so luz de
preenchimento, era FALTA DE GEOMETRIA refletivel. GPT deu 3 opcoes; escolhida
OPCAO A (light slot vertical rasante, 3cm x 135cm, LED 2700K) por custo/
beneficio. Implementado como kind proprio `kb_slot_led` nos dois branches
(orient v/h) do espelho, material dedicado (mais fraco que o halo).

Placar: p-BEAUTY05 (slot only) = 9.0, ESPELHO_RESOLVIDO=AINDA_NAO (camera so
mostrava fatia estreita). p-BEAUTY06 (camera fov62 mais aberta + slot mais
forte) = **9.1**, ainda AINDA_NAO. Ganho real e mensurado, nao resolvido 100%.

GOTCHA pago: errei os EIXOS na primeira tentativa — pra parede orient="v" o
rasgo tem que ser FINO em Y (largura ao longo da parede) e ALTO em Z, nao o
contrario; virou um painel 90x70cm que estourou o espelho (branco morto).
Corrigido: fino em Y (~3cm), alto em Z (1.15-2.50, ~135cm).

TOP3 aberto do juiz: (1) precisa YAW no plano do espelho (2deg) pra pegar
mais da linha+box — **builder atual nao suporta rotacao de peca** (feature
nova, nao so parametro); (2) o slot hoje le como "faixa solta" — integrar
melhor a leitura; (3) camera 2-3cm mais a esquerda.

## Aproximando mood da referencia (GPT-gerada) — 2026-08-09

Felipe pediu pra chegar mais perto da imagem que o proprio GPT gerou como
referencia. Separado em DUAS naturezas: (1) qualidade de render/luz/material
— atacavel; (2) generosidade espacial — FIXA pela planta real (~1.2m largura),
nao ajustavel sem mexer em parede de verdade.

Ataque em (1): sky/sun/burn maiores, mais fill quente, iteracoes de ajuste
fino guiadas pelo juiz.

| Iter | Nota | Mudanca |
|---|---|---|
| GPTMATCH02 | 8.5 | Mood mais quente/aberto. Juiz: "CHEGOU_MAIS_PERTO: SIM" + "espelho finalmente deixou de ser o maior problema" (7 iteracoes resolvidas). |
| GPTMATCH03 | 8.9 | Fills -25%, box -0.3EV recupera profundidade/antracite. |
| GPTMATCH04 | — | Highlight da parede esquerda reduzido (TOP3 do 8.9). |

LICAO: pedir ao GPT pra gerar a PROPRIA imagem de referencia + comparar lado
a lado destravou o espelho que travava desde a p14 — ver o alvo visual ajudou
mais que so ler texto de TOP3.
