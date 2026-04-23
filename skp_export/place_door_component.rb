# place_door_component.rb
# Place a SketchUp door component at a previously-recorded opening
# placement. Reproduces the V6.1-validated pipeline:
#
#   - Native component "Porta de 70/80cm.skp" has bbox X = 0.19 m
#   - Walls alvenaria (0.14 m) -> scale_x = 0.737
#   - Walls drywall  (0.075 m) -> scale_x = 0.395
#   - Transformation order: trn * rot * scale_trn (scale FIRST)
#   - Rotation: -90 deg around the X axis to stand the door upright
#
# Falls back to a parametric procedural door (rectangle face
# extruded) if the component file path is nil or the file is
# missing.
#
# F9 additions:
#   - hinge_side == "right" mirrors the door leaf horizontally so the
#     hinge lands on the opposite jamb. Defaults to "left" / nil.
#   - swing_deg > 0 draws an auxiliary arc (ArcCurve) at the hinge
#     with radius = width/2, spanning 0..swing_deg on the side the
#     door opens to. Stored in a separate group Door_<id>_swing so
#     it can be hidden without touching the leaf.
#
# Requires the SketchUp Ruby API (>= 2021).

require_relative "lib/coords"
require_relative "lib/units"

module SkpExport
  module PlaceDoorComponent
    NATIVE_COMPONENT_BBOX_X_M = 0.19
    DEFAULT_DOOR_HEIGHT_M     = 2.10
    DEFAULT_DOOR_THICKNESS_M  = 0.04

    @cached_definition = nil

    # Place one door at the given placement record.
    # Returns the created Sketchup::ComponentInstance (or Group for
    # the procedural fallback), or nil on hard failure.
    def self.place_door(model, placement, doors_lib_path: nil)
      definition = load_component_definition(model, doors_lib_path)
      leaf = if definition
               place_real_component(model, placement, definition)
             else
               place_procedural_fallback(model, placement)
             end
      draw_swing_arc(model, placement) if placement[:swing_deg].to_f > 0.0
      leaf
    end

    # Load and cache the door component definition. Returns nil if the
    # file is absent (caller will use the procedural fallback).
    def self.load_component_definition(model, path)
      return @cached_definition if @cached_definition && @cached_definition.valid?
      return nil if path.nil?
      return nil unless File.exist?(path)

      defs = model.definitions
      @cached_definition = defs.load(path)
      @cached_definition
    rescue StandardError => e
      warn("[skp_export] failed to load door component '#{path}': #{e.message}")
      nil
    end

    def self.place_real_component(model, placement, definition)
      cx_m, cy_m = placement[:center_m]
      thickness_m = placement[:wall_thickness_m]
      axis = placement[:axis] # "horizontal" / "vertical"

      scale_x = thickness_m / NATIVE_COMPONENT_BBOX_X_M
      # Flip Y scale to mirror the leaf when hinge is on the right jamb
      # (the native component hinges on the left). `hinge_side` may be
      # nil when the detector couldn't decide — default to left.
      hinge_y_scale = placement[:hinge_side] == "right" ? -1.0 : 1.0

      scale_trn = Geom::Transformation.scaling(
        Geom::Point3d.new(0, 0, 0),
        scale_x,
        hinge_y_scale,
        1.0,
      )

      # Stand door upright: native component lies flat, rotate -90 deg
      # around the X axis.
      rot = Geom::Transformation.rotation(
        Geom::Point3d.new(0, 0, 0),
        Geom::Vector3d.new(1, 0, 0),
        -Math::PI / 2.0,
      )

      # If wall is "vertical" (runs north-south in the source PDF) we
      # also rotate the door 90 deg around Z so its width aligns with
      # the wall direction.
      if axis == "vertical"
        z_rot = Geom::Transformation.rotation(
          Geom::Point3d.new(0, 0, 0),
          Geom::Vector3d.new(0, 0, 1),
          Math::PI / 2.0,
        )
        rot = z_rot * rot
      end

      trn = Geom::Transformation.translation(
        Geom::Vector3d.new(cx_m.m, cy_m.m, 0),
      )

      transform = trn * rot * scale_trn
      instance = model.active_entities.add_instance(definition, transform)
      instance.name = "Door_#{placement[:opening_id]}"
      instance
    rescue StandardError => e
      warn("[skp_export] place_real_component failed (#{placement[:opening_id]}): #{e.message}")
      nil
    end

    # Fallback: procedural door = rectangle face extruded by
    # DEFAULT_DOOR_THICKNESS_M.
    def self.place_procedural_fallback(model, placement)
      cx_m, cy_m = placement[:center_m]
      width_m = placement[:width_m]
      half_w = width_m / 2.0
      thick = DEFAULT_DOOR_THICKNESS_M
      h = DEFAULT_DOOR_HEIGHT_M

      ents = model.active_entities
      group = ents.add_group
      g_ents = group.entities

      if placement[:axis] == "vertical"
        # Door runs along the Y axis: width in Y, thickness in X.
        pts = [
          Geom::Point3d.new(cx_m.m - thick / 2.0.m, (cy_m - half_w).m, 0),
          Geom::Point3d.new(cx_m.m + thick / 2.0.m, (cy_m - half_w).m, 0),
          Geom::Point3d.new(cx_m.m + thick / 2.0.m, (cy_m + half_w).m, 0),
          Geom::Point3d.new(cx_m.m - thick / 2.0.m, (cy_m + half_w).m, 0),
        ]
      else
        # Horizontal: width in X, thickness in Y.
        pts = [
          Geom::Point3d.new((cx_m - half_w).m, cy_m.m - thick / 2.0.m, 0),
          Geom::Point3d.new((cx_m + half_w).m, cy_m.m - thick / 2.0.m, 0),
          Geom::Point3d.new((cx_m + half_w).m, cy_m.m + thick / 2.0.m, 0),
          Geom::Point3d.new((cx_m - half_w).m, cy_m.m + thick / 2.0.m, 0),
        ]
      end

      face = g_ents.add_face(pts)
      face.reverse! if face.normal.z < 0
      face.pushpull(h.m)
      group.name = "Door_#{placement[:opening_id]}_proc"
      group
    rescue StandardError => e
      warn("[skp_export] procedural fallback failed (#{placement[:opening_id]}): #{e.message}")
      nil
    end

    # Draw the swing arc: an ArcCurve centred at the hinge corner,
    # radius = width/2, spanning 0..swing_deg in the ground plane.
    # Stored in its own group so it can be toggled off independently
    # of the door leaf.
    #
    # The hinge corner is placed at cx +/- half_w depending on
    # `hinge_side`. For a "left" hinge on a horizontal wall the hinge
    # is at the LEFT end of the opening and the arc sweeps INTO the
    # room along +Y. For "right" we flip the X offset and Y direction.
    def self.draw_swing_arc(model, placement)
      cx_m, cy_m = placement[:center_m]
      width_m = placement[:width_m]
      half_w = width_m / 2.0
      swing_rad = placement[:swing_deg].to_f * Math::PI / 180.0
      axis = placement[:axis]
      hinge_side = placement[:hinge_side] == "right" ? "right" : "left"

      # Hinge offset along the wall and swing direction perpendicular
      # to the wall. For a "horizontal" wall, the wall runs in X, the
      # door width is in X, and the swing arc sweeps in +Y (default
      # left hinge) or -Y (right hinge). Vertical walls swap X<->Y.
      if axis == "vertical"
        hx = hinge_side == "left" ? 0.0 : 0.0
        hy = hinge_side == "left" ? -half_w : +half_w
        start_vec_x = hinge_side == "left" ? +half_w : -half_w
        start_vec_y = 0.0
      else
        hx = hinge_side == "left" ? -half_w : +half_w
        hy = 0.0
        start_vec_x = 0.0
        start_vec_y = hinge_side == "left" ? +half_w : -half_w
      end

      hinge_pt = Geom::Point3d.new((cx_m + hx).m, (cy_m + hy).m, 0)
      # Arc start direction in the XY plane.
      normal = Geom::Vector3d.new(0, 0, 1)
      xaxis = Geom::Vector3d.new(start_vec_x, start_vec_y, 0)
      xaxis.normalize!
      radius = (width_m).m

      ents = model.active_entities
      group = ents.add_group
      g_ents = group.entities
      g_ents.add_arc(hinge_pt, xaxis, normal, radius, 0.0, swing_rad)
      group.name = "Door_#{placement[:opening_id]}_swing"
      group
    rescue StandardError => e
      warn("[skp_export] draw_swing_arc failed (#{placement[:opening_id]}): #{e.message}")
      nil
    end

    def self.reset_cache!
      @cached_definition = nil
    end
  end
end
