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
