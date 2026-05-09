"""Generate the Cycle 12b demo SVG: consensus + rasterised PDF
underlay baked into one self-contained SVG file.

Run from the repo root:

    python scripts/cockpit_make_demo_pdf_underlay.py

Output: ``docs/diagnostics/2026-05-08_cockpit_demo_overlay_with_pdf.svg``

Prefers the canonical ``planta_74`` baseline; falls back to the
``cycle11c`` synth round-trip when planta_74 isn't checked in. Pure
read-only against existing artefacts; never mutates ``runs/`` or
``ground_truth/`` (CLAUDE.md §1, §2).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from cockpit.render_overlay import (  # noqa: E402
    OverlayToggles,
    pdf_page_to_data_url,
    render_overlay_svg,
)


def main() -> int:
    candidates = [
        (REPO_ROOT / "runs/vector/consensus_model.json",
         REPO_ROOT / "planta_74.pdf"),
        (REPO_ROOT / "runs/cycle11c/c3.json",
         REPO_ROOT / "runs/cycle11c/synth_l2.pdf"),
    ]
    pair = next(((c, p) for c, p in candidates
                 if c.exists() and p.exists()), None)
    if pair is None:
        print("[skip] no consensus + PDF pair available", file=sys.stderr)
        return 1
    cons_path, pdf_path = pair
    print(f"using consensus={cons_path.relative_to(REPO_ROOT)} "
          f"+ pdf={pdf_path.relative_to(REPO_ROOT)}")

    consensus = json.loads(cons_path.read_text(encoding="utf-8"))
    underlay = pdf_page_to_data_url(pdf_path, dpi=144, opacity=0.55)
    print(f"  page bounds: "
          f"{underlay.page_w_pt:.1f} x {underlay.page_h_pt:.1f} pt")
    print(f"  data URL length: {len(underlay.data_url)} chars")

    svg = render_overlay_svg(
        consensus, toggles=OverlayToggles(), pdf_underlay=underlay,
    )

    out_dir = REPO_ROOT / "docs" / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "2026-05-08_cockpit_demo_overlay_with_pdf.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(svg)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
