# FP-046 — pacote visual (L3) da porta Shaker na cozinha real: ANTES × DEPOIS

**Estado: `PENDING_HUMAN`.** Este pacote existe para o Felipe revisar. **Nenhum veredito visual foi emitido por IA**, e nada aqui muda o
catálogo: `visual` continua `NOT_REVIEWED` nas capacidades `shared.cabinet.front.shaker` e `kitchen.cabinet.shaker-door` até existir uma decisão sua.

## O que está sendo comparado (mesmo modelo, mesmas câmeras)
| | Arquivo `.skp` (SHA-256 em [`manifest.json`](manifest.json)) | Significado |
|---|---|---|
| **ANTES** | `kitchen_parent.skp` — `94685b5e…` | cozinha real da planta_74 (cópia do mobiliado) + gabinete de **frente lisa** (o pai da Shaker) |
| **DEPOIS** | `kitchen_shaker.skp` — `893829ba…` | o mesmo gabinete com a frente substituída pela **porta Shaker** (2 montantes, 2 travessas, painel recuado) |

Gerado pelo fluxo `shaker_flow.run_request` (estado `DONE_L2_VERIFIED`) no commit `05d810fe`, árvore **limpa**, SketchUp 26.0.429; `render_l3.py` reproduz tudo.
Os `.skp` ficam em `runs/` (não versionados); as imagens estão em [`package/`](package/) com SHA-256 no manifesto.

## O que olhar
| Vista | Arquivo | Para quê |
|---|---|---|
| **Top** (planta, ortográfica) | [`sheet_top.png`](package/sheet_top.png) | posição do gabinete na cozinha (a porta quase não aparece de cima) |
| **Iso** (3/4 frontal, elevada) | [`sheet_iso.png`](package/sheet_iso.png) | relevo: moldura × painel recuado, vizinhança |
| **Frente** | [`sheet_front.png`](package/sheet_front.png) | proporção moldura/painel, de frente (aqui o recuo só aparece pelas **arestas**: frame e painel têm o mesmo material) |
| **Detalhe oblíquo** (extra) | [`sheet_detail_oblique.png`](package/sheet_detail_oblique.png) | de cima/lado, para ver o degrau do rebaixo |

Resumos: [`overview_1_top_iso.png`](package/overview_1_top_iso.png), [`overview_2_front_detail.png`](package/overview_2_front_detail.png).
Cada vista tem o par `<vista>_before.png` / `<vista>_after.png` em tamanho cheio (1600×1200).

## O que o pacote NÃO mostra (leia antes de julgar)
- **Cores não são acabamento.** O SketchUp recebe só o *nome* do material (`mdf_nogueira`) e a cor sai de um hash do nome: o rosa/roxo é arbitrário, não a madeira real. Não há textura, veio, sombra nem V-Ray. Julgue **geometria e proporção**, não cor.
- Os valores da porta são do **pedido de teste**, não decisão de design: montantes e travessas de **50 mm**, moldura de **16 mm** (= espessura da frente do gabinete), painel de **6 mm** recuado **4 mm**. Se a proporção não agrada, o ajuste é de insumo do pedido, não de código.
- Uma posição de gabinete (a do P7) e uma única porta. Isto não é projeto de cozinha nem prova de que a posição é boa — só de que passou nos gates de âncora, arquitetura, mobília e circulação.
- Ferragem (dobradiça, puxador), veneziana e gaveta não existem. O veio da madeira é `NOT_SUPPORTED`.
- A circulação da SUITE 01 reprova antes e depois (preexistente, #351); não faz parte deste pacote.

## Como registrar a sua decisão
Responda no chat com **`APPROVED`** ou **`CHANGES_REQUESTED`** (+ o que mudar: largura de montante/travessa, profundidade do recuo, outra vista...). Eu registro em
[`visual_review.json`](visual_review.json) (reviewer, data, decisão, comentário), valendo **só para estes hashes** (`applies_to`), e só então atualizo o `visual` da capacidade
por PR. Qualquer mudança no `.skp` ou na porta invalida a decisão (R-25: um render antigo não vale para um commit novo).
