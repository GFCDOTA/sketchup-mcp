"""LLM architect oracle: ask Claude Vision to diagnose defects in a plan-extract-v2 run.

Dev-time tool only. Reads the rendered overlay PNG plus observed_model.json from a
run directory, sends them to Claude with a tool that forces structured JSON
output, validates the response against scripts/oracle/diagnosis_schema.json, and
writes the diagnosis next to the run.

Usage:
    python scripts/oracle/llm_architect.py --run runs/openings_refine_final
    python scripts/oracle/llm_architect.py --run runs/foo --out diag.json --model claude-sonnet-4-6

Requires ANTHROPIC_API_KEY in the environment. Fails loud on any missing input,
oversized image we cannot resize, missing tool_use block, or schema violation.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

import anthropic
import jsonschema

# Keep this script self-contained. PIL is shipped via anthropic's transitive deps
# (it is not in requirements.txt directly, but is available because pillow is a
# dep of several pipeline stages). We only use it for an optional resize.
try:
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover - resize is best-effort
    Image = None  # type: ignore


SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR / "diagnosis_schema.json"
DEFAULT_MODEL = "claude-opus-4-7"
MAX_IMAGE_DIM = 1024  # Claude Vision handles larger inputs but we stay tight.

SYSTEM_PROMPT = """You are the architect oracle for plan-extract-v2, a Python pipeline that converts PDF/SVG architectural floor plans into a canonical observed_model.json (walls, rooms, openings, junctions). The pipeline is currently producing visibly inflated output: too many walls, sliver rooms, mis-hosted openings.

You will receive (a) a rendered overlay PNG of one run, with walls/rooms/openings drawn on top of the source plan, and (b) the observed_model.json that produced it. Your job is to identify the most actionable defects you can see in the image, naming them by their actual IDs from observed_model.json so downstream code can act on them.

Visual cues to look for:
- Sliver rooms: very small filled polygons, often tucked into wall thickness or near junctions.
- Triangle / wedge rooms: 3-vertex polygons that hug a corner — almost always a topology artifact, not a real room.
- Thin-strip rooms: extreme aspect ratio (long and ~1 wall-thickness wide), usually formed inside a doubled wall.
- Fragmented walls: a single architectural wall split into 3+ collinear segments with tiny gaps.
- Duplicate walls: two near-identical wall segments overlapping (one is a redraw of the other).
- Stub walls: short walls dangling into open space with no junction at the free end.
- Mis-hosted openings: doors/windows whose center sits in a corner, on a sliver, or with no plausible host wall.

Rules:
- Only report defects you can actually see in the image. Do NOT invent defects to pad the list.
- Prefer specific element IDs (room-12, wall-83, opening-5). Use element_id="global" only for run-wide issues like "model is roughly 3x inflated".
- 5 to 15 defects is the target; pick the ones most worth fixing first.
- Hypotheses should reference plausible geometric/topological causes (snap_tolerance, polygonize closure, hough fragmentation, etc.), not vague language.
- Suggested fixes should be concrete enough to implement (a filter rule, a parameter change, a merge step).

Return your answer ONLY by calling the `report_diagnosis` tool. Do not respond in plain text."""


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _die(msg: str, code: int = 2) -> "NoReturn":  # type: ignore[name-defined]
    """Print to stderr and exit. Used everywhere we want to fail loud."""
    print(f"llm_architect: {msg}", file=sys.stderr)
    sys.exit(code)


def load_schema() -> dict[str, Any]:
    if not SCHEMA_PATH.exists():
        _die(f"diagnosis_schema.json missing next to script at {SCHEMA_PATH}")
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def schema_to_tool_input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strip the JSON Schema 2020-12 metadata that the Anthropic tool input_schema does not accept."""
    drop = {"$schema", "$id", "title"}
    cleaned = {k: v for k, v in schema.items() if k not in drop}
    # Anthropic's tool input_schema is JSON-Schema-shaped but only consumes a
    # standard subset; $defs + $ref work fine. Keep them.
    return cleaned


def resolve_overlay(run_dir: Path) -> Path:
    audited = run_dir / "overlay_audited.png"
    if audited.exists():
        return audited
    fallback = run_dir / "overlay_0.png"
    if fallback.exists():
        return fallback
    _die(f"no overlay PNG in {run_dir} (looked for overlay_audited.png and overlay_0.png)")


def encode_image(path: Path) -> tuple[str, str]:
    """Return (base64 data, media_type). Resizes to MAX_IMAGE_DIM on the long edge if PIL is available."""
    raw = path.read_bytes()
    media_type = "image/png"
    if Image is None:
        return base64.standard_b64encode(raw).decode("ascii"), media_type
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.load()
            w, h = img.size
            longest = max(w, h)
            if longest <= MAX_IMAGE_DIM:
                return base64.standard_b64encode(raw).decode("ascii"), media_type
            scale = MAX_IMAGE_DIM / float(longest)
            new_size = (max(1, int(round(w * scale))), max(1, int(round(h * scale))))
            resized = img.resize(new_size, Image.LANCZOS)
            buf = io.BytesIO()
            # Keep PNG so the overlay's crisp lines stay legible.
            resized.save(buf, format="PNG", optimize=True)
            return base64.standard_b64encode(buf.getvalue()).decode("ascii"), media_type
    except Exception as exc:  # noqa: BLE001 - we want the message, then exit
        _die(f"failed to read/resize {path}: {exc}")


def summarize_model(observed: dict[str, Any]) -> str:
    """Produce a compact text recap of the run for the model. We do NOT dump the
    full JSON (it's large and most of it is geometry the image already shows);
    we send IDs + a few key metrics so the LLM can name elements correctly."""
    lines: list[str] = []
    run_id = observed.get("run_id", "<missing>")
    lines.append(f"run_id: {run_id}")
    walls = observed.get("walls", []) or []
    rooms = observed.get("rooms", []) or []
    openings = observed.get("openings", []) or []
    junctions = observed.get("junctions", []) or []
    lines.append(
        f"counts: walls={len(walls)} rooms={len(rooms)} openings={len(openings)} junctions={len(junctions)}"
    )
    if walls:
        lines.append("walls (id, len, thickness):")
        for w in walls:
            wid = w.get("wall_id", "?")
            start = w.get("start") or [0, 0]
            end = w.get("end") or [0, 0]
            try:
                length = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
            except Exception:  # noqa: BLE001
                length = -1.0
            thick = w.get("thickness", "?")
            lines.append(f"  {wid}: len~{length:.1f} thick={thick}")
    if rooms:
        lines.append("rooms (id, area, vertex_count):")
        for r in rooms:
            rid = r.get("room_id") or r.get("id", "?")
            area = r.get("area", "?")
            polygon = r.get("polygon") or r.get("vertices") or []
            lines.append(f"  {rid}: area={area} verts={len(polygon)}")
    if openings:
        lines.append("openings (id, kind, host_wall, center):")
        for o in openings:
            oid = o.get("opening_id") or o.get("id", "?")
            kind = o.get("kind") or o.get("type", "?")
            host = o.get("host_wall_id") or o.get("wall_id", "?")
            center = o.get("center", "?")
            lines.append(f"  {oid}: {kind} host={host} center={center}")
    return "\n".join(lines)


def call_claude(
    client: anthropic.Anthropic,
    model: str,
    schema: dict[str, Any],
    image_b64: str,
    media_type: str,
    model_recap: str,
) -> dict[str, Any]:
    tool = {
        "name": "report_diagnosis",
        "description": "Report observed defects in the floor-plan extraction run. Must conform to OracleDiagnosis.",
        "input_schema": schema_to_tool_input_schema(schema),
    }
    user_blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
        },
        {
            "type": "text",
            "text": (
                "Here is the run's observed_model.json recap (ids you should reference):\n\n"
                f"{model_recap}\n\n"
                "Inspect the overlay image, identify 5-15 actionable defects, and call "
                "the report_diagnosis tool. Use element_ids from the recap above."
            ),
        },
    ]
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "tool", "name": "report_diagnosis"},
        messages=[{"role": "user", "content": user_blocks}],
    )
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "report_diagnosis":
            return block.input  # type: ignore[return-value]
    _die(
        "Claude did not return a tool_use block for report_diagnosis "
        f"(stop_reason={response.stop_reason!r}, blocks={[getattr(b, 'type', '?') for b in response.content]})"
    )


def print_summary(diagnosis: dict[str, Any]) -> None:
    defects = diagnosis.get("defects", [])
    by_severity = {"high": 0, "medium": 0, "low": 0}
    for d in defects:
        sev = d.get("severity", "low")
        by_severity[sev] = by_severity.get(sev, 0) + 1
    print(f"Diagnosis for run {diagnosis.get('run_id', '?')}:")
    print(f"  total defects: {len(defects)}")
    print(
        f"  by severity: high={by_severity['high']} "
        f"medium={by_severity['medium']} low={by_severity['low']}"
    )
    print("  top 3:")
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    top = sorted(defects, key=lambda d: sev_rank.get(d.get("severity", "low"), 9))[:3]
    for d in top:
        print(
            f"    - [{d.get('severity', '?')}] {d.get('element_id', '?')} "
            f"({d.get('defect_kind', '?')})"
        )


# --------------------------------------------------------------------------- #
# Main                                                                        #
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="llm_architect",
        description="Diagnose a plan-extract-v2 run with the Claude Vision architect oracle.",
    )
    p.add_argument("--run", required=True, type=Path, help="Run directory (e.g. runs/openings_refine_final)")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: <run>/oracle_diagnosis_llm.json)",
    )
    p.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Anthropic model id (default: {DEFAULT_MODEL}). Tested with claude-opus-4-7 and claude-sonnet-4-6.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_dir: Path = args.run
    if not run_dir.exists() or not run_dir.is_dir():
        _die(f"run dir not found: {run_dir}")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        _die("ANTHROPIC_API_KEY is not set in the environment", code=3)

    overlay_path = resolve_overlay(run_dir)
    model_path = run_dir / "observed_model.json"
    if not model_path.exists():
        _die(f"observed_model.json missing in {run_dir}")
    with model_path.open("r", encoding="utf-8") as f:
        observed = json.load(f)

    schema = load_schema()
    image_b64, media_type = encode_image(overlay_path)
    model_recap = summarize_model(observed)

    print(
        f"llm_architect: model={args.model} run={run_dir} overlay={overlay_path.name} "
        f"image_b64_bytes={len(image_b64)}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    diagnosis = call_claude(client, args.model, schema, image_b64, media_type, model_recap)

    # Anthropic returns the tool input as a plain dict already; validate it.
    try:
        jsonschema.validate(instance=diagnosis, schema=schema)
    except jsonschema.ValidationError as exc:
        _die(
            "Claude's tool response failed schema validation: "
            f"{exc.message} at path {list(exc.absolute_path)}"
        )

    # If run_id came back wrong/missing, force-correct it from observed_model.json.
    declared_run_id = observed.get("run_id")
    if declared_run_id and diagnosis.get("run_id") != declared_run_id:
        diagnosis["run_id"] = declared_run_id

    out_path: Path = args.out or (run_dir / "oracle_diagnosis_llm.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(diagnosis, f, indent=2, ensure_ascii=False)
    print(f"llm_architect: wrote {out_path}")
    print_summary(diagnosis)
    return 0


if __name__ == "__main__":
    sys.exit(main())
