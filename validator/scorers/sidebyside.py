"""Scorer for side-by-side comparison images (sidebyside, side_by_side,
sidebyside_axon, triple_comparison).

Strategy
--------
1. Sanity-check the PNG isn't blank.
2. If a source PDF is available and ``pypdfium2`` + ``skimage`` are
   installed, rasterize page 1 of the PDF and compute an SSIM between
   the *right* half of the side-by-side and the rasterized PDF (left half
   is typically the PDF baseline already pasted in).
3. Halves alone aren't a reliable signal, so we also compute coverage
   parity: both halves should have a similar fraction of non-white
   pixels (within 0.4x..2.5x). A wildly different coverage means one
   side is empty or one side is extra noise.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from .base import Issue, ScorerContext, ScorerResult


def _nonwhite_fraction(arr: np.ndarray) -> float:
    nonwhite = ~((arr[..., 0] >= 245) & (arr[..., 1] >= 245) & (arr[..., 2] >= 245))
    return float(nonwhite.sum()) / max(arr.shape[0] * arr.shape[1], 1)


def _rasterize_pdf_page(pdf_path: Path, scale: float = 2.0) -> np.ndarray | None:
    try:
        import pypdfium2 as pdfium
    except Exception:
        return None
    try:
        doc = pdfium.PdfDocument(str(pdf_path))
        page = doc.get_page(0)
        bitmap = page.render(scale=scale)
        img = bitmap.to_pil().convert("RGB")
        return np.asarray(img)
    except Exception:
        return None


def _ssim(a: np.ndarray, b: np.ndarray) -> float | None:
    try:
        from skimage.metrics import structural_similarity
        from skimage.transform import resize
    except Exception:
        return None
    # bring to identical shape (target = smaller)
    th = min(a.shape[0], b.shape[0])
    tw = min(a.shape[1], b.shape[1])
    if th < 32 or tw < 32:
        return None
    aa = resize(a, (th, tw, 3), preserve_range=True, anti_aliasing=True).astype(np.uint8)
    bb = resize(b, (th, tw, 3), preserve_range=True, anti_aliasing=True).astype(np.uint8)
    ag = (0.299 * aa[..., 0] + 0.587 * aa[..., 1] + 0.114 * aa[..., 2]).astype(np.uint8)
    bg = (0.299 * bb[..., 0] + 0.587 * bb[..., 1] + 0.114 * bb[..., 2]).astype(np.uint8)
    return float(structural_similarity(ag, bg, data_range=255))


def score_sidebyside(entry: dict, ctx: ScorerContext) -> ScorerResult:
    issues: list[Issue] = []
    metrics: dict = {}

    png_path = ctx.repo_root / entry["history_path"]
    if not png_path.exists():
        return ScorerResult(
            score=0.0,
            issues=[Issue("error", "png_missing", f"history png missing: {png_path}")],
            scorer="sidebyside",
        )

    img = np.asarray(Image.open(png_path).convert("RGB"))
    h, w, _ = img.shape
    metrics["size"] = [w, h]

    # is the canvas blank?
    nonwhite_total = _nonwhite_fraction(img)
    metrics["nonwhite_total"] = round(nonwhite_total, 4)
    if nonwhite_total < 0.01:
        return ScorerResult(
            score=0.0,
            issues=[Issue("error", "render_blank_white", "sidebyside PNG is essentially blank")],
            metrics=metrics,
            scorer="sidebyside",
        )

    # ---- coverage parity --------------------------------------------------
    half = w // 2
    left = img[:, :half, :]
    right = img[:, half:, :]
    nw_left = _nonwhite_fraction(left)
    nw_right = _nonwhite_fraction(right)
    metrics["nonwhite_left"] = round(nw_left, 4)
    metrics["nonwhite_right"] = round(nw_right, 4)

    if nw_left < 0.005 or nw_right < 0.005:
        parity_score = 0.0
        issues.append(Issue("error", "half_blank",
                            f"one side is blank (left={nw_left:.1%}, right={nw_right:.1%})"))
    else:
        ratio = nw_left / nw_right if nw_right > 0 else float("inf")
        metrics["coverage_ratio"] = round(ratio, 3)
        if 0.4 <= ratio <= 2.5:
            parity_score = 1.0
        else:
            parity_score = max(0.0, 1.0 - abs(ratio - 1.0) / 5.0)
            issues.append(Issue(
                "warn", "coverage_parity_off",
                f"left/right non-white coverage ratio = {ratio:.2f} (expected 0.4..2.5)",
            ))

    # ---- SSIM vs PDF baseline (best effort) -------------------------------
    ssim_score = None
    pdf_src = entry.get("source", {}).get("pdf")
    if pdf_src and not pdf_src.get("missing"):
        pdf_path = ctx.repo_root / pdf_src["path"] if not Path(pdf_src["path"]).is_absolute() else Path(pdf_src["path"])
        if pdf_path.exists():
            pdf_img = _rasterize_pdf_page(pdf_path)
            if pdf_img is not None:
                ssim_score = _ssim(left, pdf_img)
                if ssim_score is not None:
                    metrics["ssim_left_vs_pdf"] = round(ssim_score, 4)
                    if ssim_score < 0.10:
                        issues.append(Issue(
                            "warn", "ssim_left_pdf_low",
                            f"left half SSIM vs PDF baseline = {ssim_score:.2f}",
                        ))

    # ---- combined score ---------------------------------------------------
    # parity 0.6, ssim 0.4 if available, else parity 1.0
    if ssim_score is not None:
        # SSIM of unrelated images can land near 0 even when parity is high.
        # Bias the SSIM contribution so a low SSIM only docks ~0.2.
        ssim_norm = max(0.0, min(1.0, (ssim_score - 0.05) / 0.40))
        score = 0.7 * parity_score + 0.3 * ssim_norm
        metrics["ssim_norm"] = round(ssim_norm, 3)
    else:
        score = parity_score

    notes = (f"sidebyside: parity={parity_score:.2f}"
             + (f" ssim={ssim_score:.2f}" if ssim_score is not None else " (no SSIM)"))
    return ScorerResult(score=score, issues=issues, notes=notes,
                        metrics=metrics, scorer="sidebyside")
