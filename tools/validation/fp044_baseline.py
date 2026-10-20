"""FP-044/F0 — linha de base de SAIDA IDENTICA para as fatias de consolidacao (movimento + religacao, nunca comportamento).

Captura, sem SketchUp: hash por comodo das caixas da planta_74 (`collect_boxes`), SHA-256 dos canonicos, entradas da raiz e
`tools/*.py`. `compare` falha se qualquer hash de comodo ou canonico mudou. Rodar com `PT_TO_M=0.0259` (escala da planta_74).

uso: python -m tools.validation.fp044_baseline capture <saida.json>
     python -m tools.validation.fp044_baseline compare <baseline.json>
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ("artifacts/planta_74/planta_74.skp", "artifacts/planta_74/geometry_report.json",
             "artifacts/planta_74/furnished/planta_74_furnished.skp",
             "fixtures/planta_74/consensus_with_human_walls_and_soft_barriers.json",
             "fixtures/quadrado/consensus_with_window.json")


def _sha(path: Path) -> str:
    """SHA-256; texto (.json) com fim de linha normalizado (CRLF do checkout Windows x LF do CI), binario (.skp) cru."""
    data = path.read_bytes()
    if path.suffix == ".json":
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def room_hashes() -> dict[str, str]:
    from tools.furnish_apartment import CONSENSUS, collect_boxes
    boxes, _ = collect_boxes(json.loads(Path(CONSENSUS).read_text("utf-8")))
    per_room: dict[str, list[str]] = defaultdict(list)
    for b in boxes:
        per_room[str(b.get("room"))].append(json.dumps(b, sort_keys=True, default=str))
    return {room: hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest() for room, rows in sorted(per_room.items())}


def tracked() -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    return [f for f in out if f]


def capture() -> dict:
    files = tracked()
    return {
        "schema_version": "fp044_baseline.v1",
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "room_box_hashes": room_hashes(),
        "canonical_sha256": {p: _sha(ROOT / p) for p in CANONICAL},
        "root_entries": sorted({f.split("/")[0] for f in files}),
        "tools_py_top_level": sorted(f for f in files if f.startswith("tools/") and f.count("/") == 1 and f.endswith(".py")),
    }


def compare(baseline: dict) -> list[str]:
    now = capture()
    errors = []
    for room, h in baseline["room_box_hashes"].items():
        if now["room_box_hashes"].get(room) != h:
            errors.append(f"CAIXAS_MUDARAM: {room}")
    errors += [f"CANONICO_MUDOU: {p}" for p, h in baseline["canonical_sha256"].items() if now["canonical_sha256"].get(p) != h]
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("capture", "compare"):
        print(__doc__)
        return 2
    if argv[1] == "capture":
        Path(argv[2]).write_text(json.dumps(capture(), indent=1, ensure_ascii=False), encoding="utf-8")
        return 0
    errors = compare(json.loads(Path(argv[2]).read_text("utf-8")))
    print("\n".join(errors) or "IDENTICO")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
