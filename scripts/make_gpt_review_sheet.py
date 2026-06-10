#!/usr/bin/env python
"""make_gpt_review_sheet.py — monta a FOLHA DE REVIEW (referencia x sofa gerado)
e emite o PROMPT PADRAO estruturado pro GPT. Parte do harness SOFA_GPT_REVIEW_LOOP.

Uso:
    python make_gpt_review_sheet.py <case_id> [ref_key]
        case_id : pasta em renders/sofa_eval/<case_id> (usa three_quarter/front/side/top)
        ref_key : modern_dark (default) | kivik

Saida:
    renders/sofa_eval/gpt_review/<case_id>_review.png   (referencia em cima, gerado embaixo)
    renders/sofa_eval/gpt_review/<case_id>_prompt.txt    (prompt padrao p/ colar no ChatGPT)
O AGENTE entao: seta clipboard (set_clipboard_image.ps1) -> cola no ChatGPT (Chrome) -> cola o
prompt -> captura a resposta no formato fixo -> aplica TOP_FIX no SISTEMA -> loga em
references/sofas/gpt_review_log.jsonl.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(WT, "renders", "sofa_eval")
OUT = os.path.join(EV, "gpt_review")

REFS = {
    "modern_dark": (os.path.join(WT, "references", "sofas", "audit",
                                 "modern_dark_gray", "modern_dark_gray_iso.png"),
                    "REF 3DW: modern dark gray (baixo, profundo, lounge, escuro)"),
    "kivik": (os.path.join(WT, "artifacts", "review", "furniture",
                           "group_60", "group_60_iso.png"),
              "REF 3DW: KIVIK (3 lugares, bracos largos, tecido escuro pesado)"),
}

# PROMPT PADRAO — formato fixo pra resposta PARSEAVEL todo ciclo. Anti-elogio.
PROMPT = (
    "Voce e o DIRETOR de qualidade de um SISTEMA PROCEDURAL de sofas em SketchUp "
    "(low/mid-poly, NAO copio assets). Na imagem: em cima a REFERENCIA real (3DW), "
    "embaixo o sofa GERADO pelo meu sistema (vistas 3/4, front, side). "
    "Compare gerado vs referencia e responda EXATAMENTE neste formato, sem elogio:\n"
    "VEREDITO: PASS|WARN|FAIL\n"
    "PARTE_PIOR: almofada|encosto|braco|base|perfil|material\n"
    "TOP_FIX: <a UNICA coisa mais importante pra mexer AGORA — concreta, geometrica/parametrica>\n"
    "ONDE_NO_SISTEMA: primitive|component|generator|schema|material\n"
    "POR_QUE: <1 linha>\n"
    "PROXIMO_DEPOIS: <a 2a prioridade>\n"
    "CONVERGIU: sim|nao\n"
    "Regra: NAO recomende textura/V-Ray enquanto a GEOMETRIA do estofado nao estiver boa. "
    "Toda correcao tem que ser de CLASSE (primitiva/componente/parametro), nao de 1 exemplar."
)


def _font(s):
    for n in ("arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(n, s)
        except OSError:
            continue
    return ImageFont.load_default()


def _load(p, h=300):
    im = Image.open(p).convert("RGB")
    return im.resize((max(1, int(im.width * h / im.height)), h))


def build(case_id, ref_key="modern_dark"):
    os.makedirs(OUT, exist_ok=True)
    cdir = os.path.join(EV, case_id)
    gen = []
    for label, fn in (("3/4", "three_quarter.png"), ("front", "front.png"), ("side", "side.png")):
        p = os.path.join(cdir, fn)
        if os.path.exists(p):
            gen.append((label, _load(p, 300)))
    if not gen:
        print("ERRO: sem renders em", cdir)
        return None
    rp, rlabel = REFS.get(ref_key, REFS["modern_dark"])
    ref = _load(rp, 300) if os.path.exists(rp) else None

    gap, lab = 12, 26
    genw = sum(im.width for _, im in gen) + gap * (len(gen) + 1)
    w = max(genw, (ref.width if ref else 0) + gap * 2)
    h = lab + (300 + lab if ref else 0) + lab + 300 + lab
    cv = Image.new("RGB", (w, h), (240, 240, 240))
    d = ImageDraw.Draw(cv)
    f, ft = _font(15), _font(17)
    d.text((10, 5), f"REVIEW  {case_id}   (referencia em cima  x  gerado embaixo)", fill=(15, 15, 15), font=ft)
    y = lab
    if ref:
        d.text((gap, y), rlabel, fill=(150, 30, 30), font=f)
        cv.paste(ref, (gap, y + lab))
        y += lab + 300
    d.text((gap, y), "GERADO PELO SISTEMA:", fill=(20, 110, 20), font=f)
    y += lab
    x = gap
    for label, im in gen:
        cv.paste(im, (x, y))
        d.text((x + 4, y + 302), label, fill=(40, 40, 40), font=f)
        x += im.width + gap
    sheet = os.path.join(OUT, f"{case_id}_review.png")
    cv.save(sheet)
    promptp = os.path.join(OUT, f"{case_id}_prompt.txt")
    with open(promptp, "w", encoding="utf-8") as fh:
        fh.write(PROMPT)
    print("SHEET:", sheet)
    print("PROMPT:", promptp)
    return sheet


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else "eval_low_modern_dark_3seat"
    rk = sys.argv[2] if len(sys.argv) > 2 else "modern_dark"
    build(cid, rk)
