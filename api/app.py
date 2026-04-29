from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile

from model.pipeline import PipelineError, run_pdf_pipeline, run_svg_pipeline


app = FastAPI(title="plan-extract-v2", version="2.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "plan-extract-v2"}


@app.post("/extract")
async def extract(pdf: UploadFile = File(...)) -> dict:
    if not pdf.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
    lower = pdf.filename.lower()
    if not (lower.endswith(".pdf") or lower.endswith(".svg")):
        raise HTTPException(status_code=400, detail="Input must be a PDF or SVG file.")

    payload = await pdf.read()
    output_dir = Path("artifacts") / uuid4().hex

    try:
        if lower.endswith(".svg"):
            result = run_svg_pipeline(
                svg_bytes=payload,
                filename=pdf.filename,
                output_dir=output_dir,
            )
        else:
            result = run_pdf_pipeline(
                pdf_bytes=payload,
                filename=pdf.filename,
                output_dir=output_dir,
            )
    except PipelineError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "observed_model": result.observed_model,
        "artifacts": {
            "output_dir": str(result.output_dir),
            "observed_model_json": str(result.output_dir / "observed_model.json"),
            "debug_walls_svg": str(result.output_dir / "debug_walls.svg"),
            "debug_junctions_svg": str(result.output_dir / "debug_junctions.svg"),
            "connectivity_report_json": str(result.output_dir / "connectivity_report.json"),
        },
    }
