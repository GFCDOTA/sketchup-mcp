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

require_relative "lib/coords"
require_relative "lib/json_parser"
require_relative "lib/units"
require_relative "rebuild_walls"
require_relative "apply_openings"
require_relative "place_door_component"
require_relative "build_floors"

module SkpExport
  module_function

  def run(run_dir:, door_lib: nil, output_name: "output.skp", floors: false)
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

      # 4. Optional: materialise floor faces per room.
      BuildFloors.run(model, data["rooms"]) if floors

      # 5. Save.
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

  # CLI entry point — parse ARGV passed by SketchUp via
  # `SketchUp.exe -RubyStartup main.rb -- --run-dir DIR ...`.
  # SketchUp forwards everything after `--` verbatim to the Ruby script.
  def parse_argv!(argv)
    require "optparse"
    options = { output_name: "plant.skp", floors: false }
    OptionParser.new do |opts|
      opts.banner = "Usage: sketchup -RubyStartup main.rb -- [options]"
      opts.on("--run-dir DIR", "Run directory with observed_model.json") do |v|
        options[:run_dir] = v
      end
      opts.on("--door-lib PATH", "SKP file with door component (optional)") do |v|
        options[:door_lib] = v
      end
      opts.on("--output-name NAME", "Output .skp filename") do |v|
        options[:output_name] = v
      end
      opts.on("--floors", "Also create Floor_<room_id> faces for each room") do
        options[:floors] = true
      end
      opts.on("-h", "--help", "Show this help") do
        puts opts
        exit 0
      end
    end.parse!(argv)

    raise ArgumentError, "missing --run-dir" unless options[:run_dir]

    options
  end
end

# Auto-dispatch when invoked as a Ruby-startup script inside SketchUp.
# Guarded so that `load "main.rb"` from the Ruby console still works
# the old way (no argv, user calls SkpExport.run manually).
if defined?(Sketchup) && !(ARGV.nil? || ARGV.empty?)
  begin
    opts = SkpExport.parse_argv!(ARGV.dup)
    SkpExport.run(
      run_dir: opts[:run_dir],
      door_lib: opts[:door_lib],
      output_name: opts[:output_name],
      floors: opts[:floors],
    )
    load File.expand_path("validate.rb", __dir__)
    SkpExport::Validate.run(run_dir: opts[:run_dir], output_name: opts[:output_name])
  rescue StandardError => e
    warn("[skp_export] FATAL: #{e.class}: #{e.message}")
    warn(e.backtrace.first(10).join("\n")) if e.backtrace
    exit 1
  end
end
