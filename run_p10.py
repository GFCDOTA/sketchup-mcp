"""Roda o pipeline sobre p10_red.pdf (gerado de paredes_v5.png)
e renderiza overlay_semantic.png com as mesmas cores do v4."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).parent))

from model.pipeline import run_pdf_pipeline

PDF = Path("runs/proto/p10_red.pdf")
PEITORIS = Path("runs/proto/p10_peitoris.json")
OUT = Path("runs/proto/p10_v1_run"); OUT.mkdir(parents=True, exist_ok=True)

peitoris = json.loads(PEITORIS.read_text())
print(f"peitoris input: {len(peitoris)}")

result = run_pdf_pipeline(
    pdf_bytes=PDF.read_bytes(),
    filename="p10_red.pdf",
    output_dir=OUT,
    peitoris=peitoris,
)

obs = json.loads((OUT / "observed_model.json").read_text())
print(f"walls={len(obs['walls'])} juncs={len(obs['junctions'])} rooms={len(obs['rooms'])} "
      f"openings={len(obs.get('openings',[]))} peitoris={len(obs.get('peitoris',[]))} "
      f"geom={obs['scores']['geometry']} topo={obs['scores']['topology']} rooms={obs['scores'].get('rooms','n/a')}")
