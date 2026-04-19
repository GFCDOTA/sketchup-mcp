from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class IngestError(RuntimeError):
    pass


@dataclass(frozen=True)
class RasterPage:
    index: int
    image: np.ndarray
    width: int
    height: int


@dataclass(frozen=True)
class IngestedDocument:
    source_name: str
    pages: list[RasterPage]


def ingest_pdf(pdf_bytes: bytes, filename: str, scale: float = 2.0) -> IngestedDocument:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise IngestError("pypdfium2 is required to ingest PDF files.") from exc

    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
    except Exception as exc:
        raise IngestError(f"Unable to open PDF: {filename}") from exc

    pages: list[RasterPage] = []

    try:
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = page.render(scale=scale).to_numpy()
            if bitmap.ndim == 3:
                bitmap = bitmap[:, :, :3]
            image = np.ascontiguousarray(bitmap)
            pages.append(
                RasterPage(
                    index=index,
                    image=image,
                    width=int(image.shape[1]),
                    height=int(image.shape[0]),
                )
            )
    except Exception as exc:
        raise IngestError(f"Unable to render PDF pages for: {filename}") from exc
    finally:
        pdf.close()

    if not pages:
        raise IngestError("PDF has no pages.")

    return IngestedDocument(source_name=filename, pages=pages)
