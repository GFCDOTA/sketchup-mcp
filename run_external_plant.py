"""Generic plant runner — processa qualquer PDF arquitetonico via pipeline.

Uso:
    "E:/Python312/python.exe" run_external_plant.py <pdf_path> [out_dir_name]

Ex:
    "E:/Python312/python.exe" run_external_plant.py test_data/external/apto_3qtos.pdf

Cria runs/external_<basename>/ com observed_model.json, connectivity_report.json,
overlay_audited.png, etc. Imprime metricas summary.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model.pipeline import run_pdf_pipeline


def run_one(pdf_path: Path, out_name: str | None = None) -> dict:
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    base = out_name or f"external_{pdf_path.stem}"
    out_dir = Path("runs") / base
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[run] PDF={pdf_path} -> {out_dir}")
    try:
        run_pdf_pipeline(
            pdf_bytes=pdf_path.read_bytes(),
            filename=pdf_path.name,
            output_dir=out_dir,
        )
    except Exception as exc:
        print(f"[run] ERROR {type(exc).__name__}: {exc}")
        return {
            "plant": base, "pdf": str(pdf_path), "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
    om_path = out_dir / "observed_model.json"
    if not om_path.exists():
        print("[run] observed_model.json missing")
        return {"plant": base, "pdf": str(pdf_path), "ok": False, "error": "no_observed_model"}
    obs = json.loads(om_path.read_text(encoding="utf-8"))
    md = obs.get("metadata") or {}
    conn = md.get("connectivity") or {}
    sc = obs.get("scores") or {}
    metrics = {
        "plant": base,
        "pdf": str(pdf_path),
        "ok": True,
        "walls": len(obs.get("walls") or []),
        "junctions": len(obs.get("junctions") or []),
        "rooms": len(obs.get("rooms") or []),
        "openings": len(obs.get("openings") or []),
        "peitoris": len(obs.get("peitoris") or []),
        "ratio": conn.get("largest_component_ratio"),
        "orphan_nodes": conn.get("orphan_node_count"),
        "topology_quality": md.get("topology_quality"),
        "geometry_score": sc.get("geometry"),
        "topology_score": sc.get("topology"),
        "rooms_score": sc.get("rooms"),
        "warnings": obs.get("warnings") or [],
    }
    print(
        f"[run] walls={metrics['walls']} juncs={metrics['junctions']} rooms={metrics['rooms']} "
        f"openings={metrics['openings']} peitoris={metrics['peitoris']} "
        f"ratio={metrics['ratio']} orphans={metrics['orphan_nodes']} "
        f"q={metrics['topology_quality']}"
    )
    return metrics


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: run_external_plant.py <pdf_path> [out_name]")
        sys.exit(2)
    pdf = Path(sys.argv[1])
    out_name = sys.argv[2] if len(sys.argv) > 2 else None
    metrics = run_one(pdf, out_name)
    print(json.dumps(metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
