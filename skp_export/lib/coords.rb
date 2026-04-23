# lib/coords.rb
# Canonical pixel <-> world (metre) conversion for the skp_export bridge.
#
# This is the ONLY place where the raster Y-flip and the pixel/metre
# scale should appear. All other Ruby modules MUST route through
# `SkpExport::Coords` (or `SkpExport::Units` for the scalar helpers
# which now delegate here).
#
# Historical note (F9, 2026-04-22): before F9 the conversion was
# spread across `lib/units.rb` + ad-hoc `to_metres` in
# `rebuild_walls.rb`. That `to_metres` used a fragile "values > 50 are
# probably px" heuristic. F9 consolidates the math so main.rb always
# passes pixels, and rebuild_walls converts once via this module.
#
# SketchUp-Ruby-API awareness: this file constructs `Geom::Point3d`
# via a defensive wrapper (`world_point`) that falls back to a plain
# `Struct` when the SketchUp API is not loaded (for unit testing under
# a vanilla Ruby interpreter).

require_relative "units"

module SkpExport
  module Coords
    # 1.0 / 0.0066 m/px V6.1 calibration.
    # Keep this derived from Units.px_to_m so runtime overrides still
    # take effect (see Units.px_to_m_override=).
    def self.px_per_metre
      1.0 / Units.px_to_m
    end

    # Convert a single pixel length to world metres.
    def self.length_px_to_m(length_px)
      length_px.to_f * Units.px_to_m
    end

    # Convert a [x_px, y_px] point to world metres with optional Y flip.
    # `origin_y_px` is the raster height in pixels; when non-nil the Y
    # coordinate is flipped so SketchUp Y grows "north".
    #
    # Returns a 2-element array [x_m, y_m] — NOT a Point3d — so this
    # function is safe to call outside SketchUp.
    def self.point_px_to_m(point_px, origin_y_px: 0.0)
      x_m = point_px[0].to_f * Units.px_to_m
      y_m = (origin_y_px.to_f - point_px[1].to_f) * Units.px_to_m
      [x_m, y_m]
    end

    # Like point_px_to_m but returns a SketchUp `Geom::Point3d` at z=0.
    # Raises NameError if `Geom::Point3d` is not defined (i.e. called
    # outside SketchUp). Tests should call point_px_to_m instead.
    def self.px_to_world(point_px, origin_y_px: 0.0, z_m: 0.0)
      x_m, y_m = point_px_to_m(point_px, origin_y_px: origin_y_px)
      world_point(x_m, y_m, z_m)
    end

    # Wrap Geom::Point3d construction. In SketchUp the constructor
    # takes inches, so we convert via Numeric#m.
    def self.world_point(x_m, y_m, z_m = 0.0)
      if defined?(Geom) && Geom.const_defined?(:Point3d)
        if x_m.respond_to?(:m)
          Geom::Point3d.new(x_m.m, y_m.m, z_m.m)
        else
          Geom::Point3d.new(x_m, y_m, z_m)
        end
      else
        # Unit-test fallback — no SketchUp loaded.
        Struct.new(:x, :y, :z).new(x_m, y_m, z_m)
      end
    end

    # Convert a wall thickness in pixels to metres, preserving the
    # Units classifier (drywall vs alvenaria). Kept here to keep
    # callers from bypassing Units and producing inconsistent walls.
    def self.wall_thickness_m(thickness_px)
      Units.wall_thickness_m(thickness_px)
    end
  end
end
