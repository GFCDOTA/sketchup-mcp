"""Corta e amplia a legenda do PDF."""
from PIL import Image
img = Image.open("runs/planta_74/raw_page.png")
# legenda fica em cerca de y=1340..1620, x=80..900 na pagina 1785x2526
crop = img.crop((40, 1300, 950, 1640))
crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
crop.save("runs/planta_74/legend_zoom.png")
print(f"{crop.width}x{crop.height}")
