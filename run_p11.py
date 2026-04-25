from pathlib import Path
import json, sys
sys.path.insert(0, str(Path(__file__).parent))
from model.pipeline import run_pdf_pipeline

PDF = Path("runs/proto/p11_red.pdf")
PEITORIS = Path("runs/proto/p11_peitoris.json")
OUT = Path("runs/proto/p11_v1_run"); OUT.mkdir(parents=True, exist_ok=True)

peitoris = json.loads(PEITORIS.read_text())
result = run_pdf_pipeline(
    pdf_bytes=PDF.read_bytes(),
    filename="p11_red.pdf",
    output_dir=OUT,
    peitoris=peitoris,
)
obs = json.loads((OUT / "observed_model.json").read_text())
print(f"walls={len(obs['walls'])} juncs={len(obs['junctions'])} rooms={len(obs['rooms'])} "
      f"openings={len(obs.get('openings',[]))} peitoris={len(obs.get('peitoris',[]))} "
      f"geom={obs['scores']['geometry']} topo={obs['scores']['topology']} rooms={obs['scores'].get('rooms','n/a')}")
