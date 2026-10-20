"""Folha-contato em grade (PIL) para as matrizes de classe de movel — compartilhada por quarto e sala (FP-044/D-012).

Antes morava em `tools.rooms.living.capabilities.sofa_class_matrix` e o quarto (`bed_class`) a importava de la, uma
dependencia quarto -> sala escondida por uma fachada de `tools/`. Helper puro: so le PNGs e escreve um PNG.
"""
from __future__ import annotations


def grid_sheet(cells, out_png, title, cols=3):
    """Grade NxM com label por celula (o _contact_sheet existente e' linear)."""
    from PIL import Image, ImageDraw
    CELL_W, BAND, GAP, HEAD = 480, 26, 10, 40
    tiles = []
    for name, path, cls_r, anat_r in cells:
        im = Image.open(path).convert("RGB")
        h = int(im.height * CELL_W / im.width)
        tiles.append((f"{name} [{cls_r}/{anat_r}]", im.resize((CELL_W, h))))
    rows = (len(tiles) + cols - 1) // cols
    cell_h = max(t.height for _, t in tiles) + BAND
    W = cols * CELL_W + GAP * (cols + 1)
    H = HEAD + rows * (cell_h + GAP) + GAP
    sheet = Image.new("RGB", (W, H), (246, 244, 240))
    dr = ImageDraw.Draw(sheet)
    dr.text((GAP, 12), title, fill=(40, 38, 36))
    for i, (label, t) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = GAP + c * (CELL_W + GAP)
        y = HEAD + r * (cell_h + GAP)
        dr.text((x + 2, y + 4), label, fill=(90, 86, 80))
        sheet.paste(t, (x, y + BAND))
    sheet.save(out_png)
    return str(out_png)
