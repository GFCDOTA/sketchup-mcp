from __future__ import annotations

import io
import json
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from main import main


def _write_synthetic_pdf(path: Path, pages: int = 1) -> None:
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(200, 200)
    buf = io.BytesIO()
    doc.save(buf)
    path.write_bytes(buf.getvalue())


def test_extract_returns_zero_and_writes_artifacts(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    pdf_path = tmp_path / "synthetic.pdf"
    out_dir = tmp_path / "run_out"
    _write_synthetic_pdf(pdf_path, pages=1)

    rc = main(["extract", str(pdf_path), "--out", str(out_dir)])
    assert rc == 0

    assert (out_dir / "observed_model.json").exists()
    assert (out_dir / "debug_walls.svg").exists()
    assert (out_dir / "debug_junctions.svg").exists()
    assert (out_dir / "connectivity_report.json").exists()

    model = json.loads((out_dir / "observed_model.json").read_text(encoding="utf-8"))
    assert model["source"]["source_type"] == "pdf"
    assert model["source"]["filename"] == "synthetic.pdf"

    out = capsys.readouterr().out
    assert "run_id:" in out
    assert "walls:" in out
    assert "warnings:" in out


def test_extract_missing_pdf_returns_two(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = main(["extract", str(tmp_path / "does_not_exist.pdf"), "--out", str(tmp_path / "out")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "PDF not found" in err


def test_extract_uses_default_output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "named_plan.pdf"
    _write_synthetic_pdf(pdf_path, pages=1)
    monkeypatch.chdir(tmp_path)  # so "runs/named_plan" resolves under tmp_path

    rc = main(["extract", str(pdf_path)])
    assert rc == 0
    assert (tmp_path / "runs" / "named_plan" / "observed_model.json").exists()


def test_no_command_exits_nonzero(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code != 0
    err = capsys.readouterr().err
    assert "required" in err.lower() or "usage" in err.lower()
