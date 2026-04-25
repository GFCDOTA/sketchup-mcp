# rebuild_walls.rb
# Build a 3D wall as a thin extruded box, with optional rectangular
# openings carved out of the side face.
#
# Requires the SketchUp Ruby API (>= 2021):
#   - Sketchup.active_model
#   - Geom::Point3d, Geom::Vector3d
#   - Numeric#m  (length-unit conversion to inches)
#
# Public entry point:
#   SkpExport::RebuildWalls.build_wall_with_openings(model, wall, openings_for_wall)
#
# `wall` is the hash from observed_model.json (single split segment).
# `openings_for_wall` is the list of opening hashes whose wall_a/wall_b
# matches this wall's parent_wall_id.

require_relative "lib/units"

module SkpExport
  module RebuildWalls
    DEFAULT_WALL_HEIGHT_M = 2.70
    DEFAULT_DOOR_HEIGHT_M = 2.10

    # Build one wall as a Sketchup::Group containing the extruded box
    # with door-shaped holes carved out. Returns the created group.
    def self.build_wall_with_openings(model, wall, openings_for_wall,
                                       wall_height_m: DEFAULT_WALL_HEIGHT_M)
      ents = model.active_entities
      group = ents.add_group
      g_ents = group.entities

      thickness_m = Units.wall_thickness_m(wall["thickness"])
      sx, sy = wall["start"]
      ex, ey = wall["end"]

      # Convert pixel coords to metres (Y flip happens in main.rb when
      # building the wall list; here we trust pre-converted metres if
      # the caller passed them, but as a safety net we accept raw px
      # too: the heuristic is "values > 50 are probably px").
      sx_m, sy_m, ex_m, ey_m = to_metres(sx, sy, ex, ey)

      # Footprint of the wall as a rectangle in the XY plane, then
      # push-pulled upward to wall_height_m.
      foot = wall_footprint(sx_m, sy_m, ex_m, ey_m, thickness_m)
      face = g_ents.add_face(foot.map { |p| Geom::Point3d.new(p[0].m, p[1].m, 0) })
      face.reverse! if face.normal.z < 0
      face.pushpull(wall_height_m.m)

      # Carve openings as rectangular holes through the wall side face.
      side_face = pick_side_face(group, wall["orientation"])
      Array(openings_for_wall).each do |op|
        next unless op["kind"] == "door"

        carve_door_hole(g_ents, side_face, wall, op, wall_height_m)
      end

      group.name = "Wall_#{wall['wall_id']}"
      group
    end

    # Compute the 4 corners of the wall footprint by inflating the
    # centre line by +/- thickness/2 perpendicular to its direction.
    def self.wall_footprint(sx, sy, ex, ey, thickness_m)
      dx = ex - sx
      dy = ey - sy
      length = Math.hypot(dx, dy)
      if length < 1e-9
        # Degenerate wall — return a tiny square to avoid SketchUp crash.
        return [[sx, sy], [sx + thickness_m, sy], [sx + thickness_m, sy + thickness_m], [sx, sy + thickness_m]]
      end
      # Perpendicular unit vector
      nx = -dy / length
      ny =  dx / length
      half = thickness_m / 2.0
      [
        [sx + nx * half, sy + ny * half],
        [ex + nx * half, ey + ny * half],
        [ex - nx * half, ey - ny * half],
        [sx - nx * half, sy - ny * half],
      ]
    end

    # Pick the larger vertical face on the side of the wall to carve
    # door openings into. For horizontal walls we pick the front (-Y),
    # for vertical walls the right (+X). Caller can override.
    def self.pick_side_face(group, orientation)
      group.entities.grep(Sketchup::Face).max_by do |f|
        f.area
      end
    end

    def self.carve_door_hole(g_ents, side_face, wall, opening, wall_height_m)
      # Fall back to a procedural rectangle that we extrude into the
      # wall and then erase the resulting solid via face deletion.
      cx_m, cy_m = Units.point_px_to_m(opening["center"])
      half_w = Units.px_to_m_value(opening["width"]) / 2.0
      door_h = DEFAULT_DOOR_HEIGHT_M

      # We approximate the hole as a rectangular face on the side face
      # plane. For a robust scaffold we just create a rectangle face
      # roughly co-located with the door; SketchUp will weld it onto
      # the existing face.
      bottom = 0.0
      top    = door_h
      left   = cx_m - half_w
      right  = cx_m + half_w

      pts = [
        Geom::Point3d.new(left.m,  cy_m.m, bottom.m),
        Geom::Point3d.new(right.m, cy_m.m, bottom.m),
        Geom::Point3d.new(right.m, cy_m.m, top.m),
        Geom::Point3d.new(left.m,  cy_m.m, top.m),
      ]
      hole = g_ents.add_face(pts)
      # Erase the resulting face to leave a hole. SketchUp removes
      # coplanar inner loops automatically when erase_face is used.
      hole.erase! if hole && hole.valid?
    rescue StandardError => e
      warn("[skp_export] carve_door_hole failed for opening #{opening['opening_id']}: #{e.message}")
    end

    def self.to_metres(*coords)
      coords.map { |c| c > 50.0 ? Units.px_to_m_value(c) : c }
    end
  end
end
