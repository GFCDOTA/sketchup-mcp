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
# Requires the SketchUp Ruby API (>= 2021).

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
      if definition
        place_real_component(model, placement, definition)
      else
        place_procedural_fallback(model, placement)
      end
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
      scale_trn = Geom::Transformation.scaling(
        Geom::Point3d.new(0, 0, 0),
        scale_x,
        1.0,
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

    def self.reset_cache!
      @cached_definition = nil
    end
  end
end
