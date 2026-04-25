# lib/json_parser.rb
# Loader and normaliser for observed_model.json (schema 2.1.0).
#
# Uses the Ruby stdlib `json` library. The SketchUp 2021+ Ruby
# interpreter ships with stdlib so no rubygems install is required.
#
# The output of `parse_observed_model` is a plain Hash with keys
# matching the schema; strings are intentionally NOT symbolised so the
# downstream code can index with the same names as the Python side.

require "json"

module SkpExport
  module JsonParser
    SUPPORTED_SCHEMA_PREFIX = "2."

    # Read the observed_model.json from disk and return a normalised
    # Hash. Raises ArgumentError on missing/malformed input.
    def self.parse_observed_model(path)
      raise ArgumentError, "observed_model.json not found: #{path}" unless File.exist?(path)

      raw = File.read(path, mode: "r:UTF-8")
      data = JSON.parse(raw)

      schema = data["schema_version"].to_s
      unless schema.start_with?(SUPPORTED_SCHEMA_PREFIX)
        warn("[skp_export] WARNING: schema #{schema} is not 2.x; proceeding anyway")
      end

      normalise!(data)
      data
    end

    def self.normalise!(data)
      data["walls"]     ||= []
      data["openings"]  ||= []
      data["rooms"]     ||= []
      data["peitoris"]  ||= []
      data["junctions"] ||= []

      data["walls"].each do |w|
        w["start"]     = w["start"].map(&:to_f)
        w["end"]       = w["end"].map(&:to_f)
        w["thickness"] = w["thickness"].to_f
        w["confidence"] = (w["confidence"] || 1.0).to_f
      end

      data["openings"].each do |o|
        o["center"] = o["center"].map(&:to_f)
        o["width"]  = o["width"].to_f
        # Optional fields tolerated as nil
        o["hinge_side"] ||= nil
        o["swing_deg"]  ||= nil
        o["kind"]       ||= "door"
      end

      data["peitoris"].each do |p|
        p["height_m"] ||= 1.10
        p["bbox"] = p["bbox"].map(&:to_f) if p["bbox"]
      end

      data
    end

    # Build a lookup index: parent_wall_id -> [walls...] (because the
    # pipeline emits split segments that share a parent_wall_id).
    def self.index_walls_by_parent(walls)
      index = Hash.new { |h, k| h[k] = [] }
      walls.each do |w|
        parent = w["parent_wall_id"] || w["wall_id"]
        index[parent] << w
      end
      index
    end

    # Build a lookup index: opening center -> [openings...] grouped by
    # the parent_wall_id they reference (wall_a/wall_b).
    def self.index_openings_by_wall(openings)
      index = Hash.new { |h, k| h[k] = [] }
      openings.each do |o|
        [o["wall_a"], o["wall_b"]].compact.uniq.each do |wid|
          index[wid] << o
        end
      end
      index
    end
  end
end
