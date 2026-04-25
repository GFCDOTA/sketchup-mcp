# main.rb
# Entry point for the skp_export bridge.
#
# Reads observed_model.json from <run_dir>, builds walls + doors using
# the V6.1-validated pipeline, and writes <run_dir>/output.skp.
#
# Requires the SketchUp Ruby API (>= 2021). Cannot be run from a
# vanilla Ruby interpreter.
#
# Usage from the SketchUp Ruby console:
#
#   load "E:/Claude/sketchup-mcp/skp_export/main.rb"
#   SkpExport.run(
#     run_dir:  "E:/Claude/sketchup-mcp/runs/proto/p12_v1_run",
#     door_lib: "E:/Claude/sketchup-mcp/skp_export/components/Porta de 70_80cm.skp",
#   )
#
# `door_lib:` may be nil to force the procedural fallback.

require_relative "lib/json_parser"
require_relative "lib/units"
require_relative "rebuild_walls"
require_relative "apply_openings"
require_relative "place_door_component"

module SkpExport
  module_function

  def run(run_dir:, door_lib: nil, output_name: "output.skp")
    json_path = File.join(run_dir, "observed_model.json")
    data = JsonParser.parse_observed_model(json_path)

    model = sketchup_active_model
    raise "no active SketchUp model — open SketchUp first" unless model

    model.start_operation("skp_export build", true)
    begin
      walls_index    = JsonParser.index_walls_by_parent(data["walls"])
      openings_index = JsonParser.index_openings_by_wall(data["openings"])

      # 1. Build walls (one group per split segment).
      wall_groups = {}
      data["walls"].each do |wall|
        parent = wall["parent_wall_id"] || wall["wall_id"]
        ops_for_wall = openings_index[parent] || []
        # We pass openings purely so build_wall_with_openings can
        # decide to carve them. For the V6.1 path the existing-gap
        # detection is done below; passing the empty list keeps walls
        # solid and lets apply_openings do the carving.
        group = RebuildWalls.build_wall_with_openings(model, wall, [])
        wall_groups[wall["wall_id"]] = group
      end

      # 2. Apply openings (cut OR record existing gap).
      placements = []
      data["openings"].each do |opening|
        wall = pick_host_wall(opening, data["walls"], walls_index)
        next unless wall

        wg = wall_groups[wall["wall_id"]]
        if existing_gap?(opening, data["walls"])
          placements << ApplyOpenings.apply_existing_gap(model, wall, opening)
        else
          placements << ApplyOpenings.apply_cut_into_wall(
            model, wall, opening, wall_group: wg,
          )
        end
      end

      # 3. Place door components.
      placements.each do |placement|
        PlaceDoorComponent.place_door(model, placement, doors_lib_path: door_lib)
      end

      # 4. Save.
      output_path = File.join(run_dir, output_name)
      saved = model.save(output_path)
      warn("[skp_export] saved #{output_path} (success=#{saved})")
      output_path
    ensure
      model.commit_operation
    end
  end

  # Pick the host wall for an opening. Prefers wall_a, falls back to
  # wall_b, then to the first split segment under that parent_wall_id.
  def pick_host_wall(opening, walls, walls_index)
    [opening["wall_a"], opening["wall_b"]].compact.each do |parent_id|
      candidates = walls_index[parent_id]
      return candidates.first if candidates && !candidates.empty?
    end
    nil
  end

  # Heuristic: an existing gap means there is more than one split
  # segment for the same parent_wall_id, with a discontinuity near
  # the opening centre. A scaffold-grade check: just look at the
  # split segment count.
  def existing_gap?(opening, walls)
    parent_a = opening["wall_a"]
    parent_b = opening["wall_b"]
    return true if parent_a && parent_b && parent_a != parent_b

    same_parent = walls.count do |w|
      (w["parent_wall_id"] == parent_a) || (w["parent_wall_id"] == parent_b)
    end
    same_parent >= 2
  end

  # Return Sketchup.active_model when the SketchUp Ruby API is
  # loaded. Wrapped in a method so this file can be `require`d
  # outside SketchUp without raising NameError at load time.
  def sketchup_active_model
    return nil unless defined?(Sketchup)

    Sketchup.active_model
  end
end
