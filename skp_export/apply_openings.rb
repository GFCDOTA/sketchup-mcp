# apply_openings.rb
# Two strategies for applying openings to walls:
#
#   apply_cut_into_wall(model, wall, opening)
#       Treats the opening as a NEW cut to be carved into a solid wall
#       group. Used when the opening is detected as a door that does
#       not yet have a gap in the source geometry.
#
#   apply_existing_gap(model, wall, opening)
#       Treats the opening as an ALREADY-EXISTING gap between two
#       split wall segments. Just records metadata so that
#       place_door_component knows where to hang the door leaf.
#
# Both functions return a Hash describing the placement, used by the
# downstream component-placement step.
#
# Requires the SketchUp Ruby API (>= 2021).

require_relative "lib/units"
require_relative "rebuild_walls"

module SkpExport
  module ApplyOpenings
    # Carve a rectangular hole into an existing wall group. Returns
    # a Hash { center_m:, width_m:, wall_thickness_m:, axis: } that
    # `place_door_component` consumes.
    def self.apply_cut_into_wall(model, wall, opening, wall_group: nil)
      thickness_m = Units.wall_thickness_m(wall["thickness"])
      cx_m, cy_m  = Units.point_px_to_m(opening["center"])
      width_m     = Units.px_to_m_value(opening["width"])

      if wall_group && wall_group.valid?
        RebuildWalls.carve_door_hole(
          wall_group.entities,
          nil,
          wall,
          opening,
          RebuildWalls::DEFAULT_WALL_HEIGHT_M,
        )
      end

      {
        opening_id: opening["opening_id"],
        center_m:   [cx_m, cy_m],
        width_m:    width_m,
        wall_thickness_m: thickness_m,
        axis: opening["orientation"], # "horizontal" or "vertical"
        strategy: :cut_into_wall,
        hinge_side: opening["hinge_side"],
        swing_deg:  opening["swing_deg"],
      }
    end

    # Existing-gap path: the opening is already a hole between two
    # split wall segments, so we don't carve anything. We just emit
    # the placement record.
    def self.apply_existing_gap(model, wall, opening)
      thickness_m = Units.wall_thickness_m(wall["thickness"])
      cx_m, cy_m  = Units.point_px_to_m(opening["center"])
      width_m     = Units.px_to_m_value(opening["width"])

      {
        opening_id: opening["opening_id"],
        center_m:   [cx_m, cy_m],
        width_m:    width_m,
        wall_thickness_m: thickness_m,
        axis: opening["orientation"],
        strategy: :existing_gap,
        hinge_side: opening["hinge_side"],
        swing_deg:  opening["swing_deg"],
      }
    end
  end
end
