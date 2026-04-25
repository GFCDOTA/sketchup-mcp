"""Ad-hoc runner for planta_74 — mirrors run_p12.py but for F7 validation."""
from pathlib import Path
import json, sys
sys.path.insert(0, str(Path(__file__).parent))
from model.pipeline import run_pdf_pipeline

PDF = Path("planta_74.pdf")
OUT = Path("runs/f7_planta_74"); OUT.mkdir(parents=True, exist_ok=True)

run_pdf_pipeline(
    pdf_bytes=PDF.read_bytes(),
    filename="planta_74.pdf",
    output_dir=OUT,
)
obs = json.loads((OUT / "observed_model.json").read_text())
conn = obs.get("metadata", {}).get("connectivity", {})
print(
    f"walls={len(obs['walls'])} juncs={len(obs['junctions'])} rooms={len(obs['rooms'])} "
    f"openings={len(obs.get('openings', []))} ratio={conn.get('largest_component_ratio')} "
    f"orphan={conn.get('orphan_node_count')}"
)
