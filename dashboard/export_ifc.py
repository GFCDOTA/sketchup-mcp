"""Best-effort IFC4 export from consensus_model.json.

Tries to install ifcopenshell (60s timeout). If install/import fails, drops a
.PENDING placeholder file explaining why. If it succeeds, generates a minimal
IFC4 file with IfcWall (per consolidated wall), IfcDoor/IfcWindow (per opening),
and IfcSpace (per room).

Output:
  runs/final_planta_74/generated_from_consensus.ifc          (success)
  runs/final_planta_74/generated_from_consensus.ifc.PENDING  (failure)
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"E:/Claude/sketchup-mcp-exp-dedup")
CONSENSUS = ROOT / "runs" / "final_planta_74" / "consensus_model.json"
OUT_IFC = ROOT / "runs" / "final_planta_74" / "generated_from_consensus.ifc"
OUT_PENDING = OUT_IFC.with_suffix(".ifc.PENDING")

SCALE = 0.01
WALL_HEIGHT = 2.70


def try_install_ifcopenshell() -> bool:
    try:
        import ifcopenshell  # noqa: F401
        print("[ifc] ifcopenshell already importable")
        return True
    except ImportError:
        pass
    print("[ifc] attempting `pip install ifcopenshell` (60s timeout)")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "ifcopenshell"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"[ifc] pip install failed (rc={result.returncode})")
            print(result.stderr[-800:])
            return False
    except subprocess.TimeoutExpired:
        print("[ifc] pip install timed out after 60s")
        return False
    except Exception as exc:
        print(f"[ifc] pip install raised: {exc}")
        return False
    try:
        import ifcopenshell  # noqa: F401
        print("[ifc] install + import OK")
        return True
    except ImportError as exc:
        print(f"[ifc] post-install import still failed: {exc}")
        return False


def write_pending(reason: str):
    OUT_PENDING.write_text(
        "IFC export pending — ifcopenshell unavailable.\n"
        f"Reason: {reason}\n\n"
        "To finish the IFC export manually, install ifcopenshell\n"
        "  (https://docs.ifcopenshell.org/ifcopenshell-python/installation.html)\n"
        "and re-run dashboard/export_ifc.py.\n",
        encoding="utf-8",
    )
    print(f"[pending] {OUT_PENDING}  ({OUT_PENDING.stat().st_size} bytes)")


def build_ifc(data: dict):
    import ifcopenshell
    from ifcopenshell.api import run as ifc_run

    print(f"[ifc] ifcopenshell version: {ifcopenshell.version}")

    # Bootstrap empty IFC4 project with site/building/storey hierarchy
    model = ifcopenshell.file(schema="IFC4")
    project = ifc_run("root.create_entity", model, ifc_class="IfcProject",
                      name="planta_74_consensus")
    ifc_run("unit.assign_unit", model)
    ctx = ifc_run("context.add_context", model, context_type="Model")
    body = ifc_run("context.add_context", model, context_type="Model",
                   context_identifier="Body", target_view="MODEL_VIEW",
                   parent=ctx)
    site = ifc_run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = ifc_run("root.create_entity", model, ifc_class="IfcBuilding",
                       name="Building")
    storey = ifc_run("root.create_entity", model, ifc_class="IfcBuildingStorey",
                     name="Floor 0")
    ifc_run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifc_run("aggregate.assign_object", model, products=[building], relating_object=site)
    ifc_run("aggregate.assign_object", model,
            products=[storey], relating_object=building)

    walls = data.get("walls_consolidated", [])
    openings = data.get("openings", [])
    rooms = data.get("rooms", [])

    n_wall = n_door = n_win = n_space = 0

    # Walls — represent as extruded rectangles. Use raw geometry helpers.
    for w in walls:
        sx, sy = w["centerline_start"]
        ex, ey = w["centerline_end"]
        thickness = w["thickness_pt"] * SCALE
        length = math.hypot(ex - sx, ey - sy) * SCALE
        if length < 1e-4:
            continue
        cx = (sx + ex) * 0.5 * SCALE
        cy = (sy + ey) * 0.5 * SCALE
        angle = math.atan2(ey - sy, ex - sx)

        wall = ifc_run("root.create_entity", model, ifc_class="IfcWall",
                       name=w["wall_id"])
        # Profile: rectangle length x thickness, centered at origin
        profile = model.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            ProfileName=None,
            Position=model.create_entity(
                "IfcAxis2Placement2D",
                Location=model.create_entity("IfcCartesianPoint",
                                             Coordinates=(0.0, 0.0)),
            ),
            XDim=length,
            YDim=thickness,
        )
        # Solid extrusion upward
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity("IfcCartesianPoint",
                                             Coordinates=(0.0, 0.0, 0.0)),
            ),
            ExtrudedDirection=model.create_entity("IfcDirection",
                                                  DirectionRatios=(0.0, 0.0, 1.0)),
            Depth=WALL_HEIGHT,
        )
        rep = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )
        prod_def = model.create_entity("IfcProductDefinitionShape",
                                       Representations=[rep])
        wall.Representation = prod_def

        # Local placement (rotate around Z by 'angle', translate to (cx,cy,0))
        wall.ObjectPlacement = model.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity("IfcCartesianPoint",
                                             Coordinates=(cx, cy, 0.0)),
                Axis=model.create_entity("IfcDirection",
                                         DirectionRatios=(0.0, 0.0, 1.0)),
                RefDirection=model.create_entity(
                    "IfcDirection",
                    DirectionRatios=(math.cos(angle), math.sin(angle), 0.0),
                ),
            ),
        )
        ifc_run("spatial.assign_container", model,
                products=[wall], relating_structure=storey)
        n_wall += 1

    # Openings as floating IfcDoor / IfcWindow markers (no host wall ref)
    for o in openings:
        cx, cy = o["center"]
        chord = o.get("chord_pt", 80.0) * SCALE
        kind = o.get("kind", "door")
        ifc_class = "IfcWindow" if kind == "window" else "IfcDoor"
        height = 1.20 if kind == "window" else 2.10
        ent = ifc_run("root.create_entity", model, ifc_class=ifc_class,
                      name=o["opening_id"])
        ent.OverallHeight = height
        ent.OverallWidth = chord
        ent.ObjectPlacement = model.create_entity(
            "IfcLocalPlacement",
            RelativePlacement=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity(
                    "IfcCartesianPoint",
                    Coordinates=(cx * SCALE, cy * SCALE, 0.0),
                ),
            ),
        )
        ifc_run("spatial.assign_container", model,
                products=[ent], relating_structure=storey)
        if kind == "window":
            n_win += 1
        else:
            n_door += 1

    # Rooms as IfcSpace (no geometry). IfcSpace IS a spatial element, so use
    # aggregate.assign_object (storey decomposes into spaces) instead of
    # spatial.assign_container.
    for r in rooms:
        space = ifc_run("root.create_entity", model, ifc_class="IfcSpace",
                        name=r.get("label_qwen") or r["room_id"])
        ifc_run("aggregate.assign_object", model,
                products=[space], relating_object=storey)
        n_space += 1

    OUT_IFC.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(OUT_IFC))
    print(f"[ifc] wrote {OUT_IFC}")
    print(f"[ifc] walls={n_wall} doors={n_door} windows={n_win} spaces={n_space}")
    print(f"[ifc] file size: {OUT_IFC.stat().st_size:,} bytes")


def main():
    print(f"[load] {CONSENSUS}")
    data = json.loads(CONSENSUS.read_text(encoding="utf-8"))
    print(f"[input] walls_consolidated={len(data.get('walls_consolidated', []))} "
          f"openings={len(data.get('openings', []))} "
          f"rooms={len(data.get('rooms', []))}")

    if not try_install_ifcopenshell():
        write_pending("ifcopenshell could not be installed within 60s timeout "
                      "or was not importable after install.")
        return 1
    try:
        build_ifc(data)
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        print("[ifc] build failed:")
        print(tb[-2000:])
        write_pending(f"ifcopenshell installed but build_ifc raised: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
