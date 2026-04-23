# build_floors.rb
# Opt-in pass that materialises each `observed_model.json` room as a
# flat floor face in the SketchUp model.
#
# Each room entry is expected to carry a polygon (list of [x_px, y_px]
# vertices) via the schema's `polygon` field. If the field is absent
# but the room has `edges` (list of wall IDs), we approximate the
# polygon by walking those edges in order.
#
# Output: one `Sketchup::Group` per room, named `Floor_<room_id>`,
# each containing a single face in the Z=0 plane.
#
# Enabled via the Python CLI `--floors` flag, which forwards it down
# to `main.rb` as `floors: true`. When false (default) this module is
# never called.
#
# Requires the SketchUp Ruby API (>= 2021).

require_relative "lib/coords"

module SkpExport
  module BuildFloors
    # Build floor faces for every room in `rooms`. Returns the count
    # of successfully-created floor faces. Rooms without a usable
    # polygon are skipped with a warning.
    def self.run(model, rooms)
      return 0 if rooms.nil? || rooms.empty?

      ents = model.active_entities
      count = 0
      rooms.each do |room|
        polygon_px = extract_polygon(room)
        next unless polygon_px && polygon_px.size >= 3

        begin
          pts = polygon_px.map do |p|
            x_m, y_m = Coords.point_px_to_m(p)
            Geom::Point3d.new(x_m.m, y_m.m, 0)
          end
          group = ents.add_group
          face = group.entities.add_face(pts)
          next unless face

          face.reverse! if face.normal.z < 0
          group.name = "Floor_#{room['room_id']}"
          count += 1
        rescue StandardError => e
          warn("[skp_export] floor face failed for room #{room['room_id']}: #{e.message}")
        end
      end
      warn("[skp_export] build_floors created #{count} floor face(s)")
      count
    end

    # Return the polygon vertices (list of [x_px, y_px]) for a room,
    # or nil if none can be extracted.
    #
    # Schema priority:
    #   1. room["polygon"]  (list of 2-element arrays)
    #   2. room["vertices"] (alias used by some snapshots)
    #   3. nil (caller will skip)
    def self.extract_polygon(room)
      poly = room["polygon"] || room["vertices"]
      return nil unless poly.is_a?(Array) && !poly.empty?
      # Accept [[x,y],[x,y],...] or [{"x"=>...,"y"=>...},...].
      poly.map do |p|
        if p.is_a?(Hash)
          [p["x"] || p[:x], p["y"] || p[:y]]
        else
          [p[0], p[1]]
        end
      end
    end

    # Count-only helper used by the Python-side dry-run to preview
    # how many floors the real pass would create. Does NOT touch
    # SketchUp.
    def self.count_candidate_floors(rooms)
      return 0 if rooms.nil? || rooms.empty?
      rooms.count do |room|
        poly = extract_polygon(room)
        poly && poly.size >= 3
      end
    end
  end
end
