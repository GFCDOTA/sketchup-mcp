# consume_consensus.rb
# V6.2 — adapter that consumes the new `consensus_model.json` contract
# (schema 1.0.0) instead of the legacy `observed_model.json`.
#
# Differences vs observed_model:
#   - coordinate space is `pdf_points` (1pt = 1/72 inch = 0.000352778 m),
#     NOT pixels. SketchUp Ruby API exposes `Numeric#pt` to convert pt
#     -> internal inches directly.
#   - walls have no thickness / orientation fields. We infer:
#       * orientation from start->end vector (horizontal/vertical/oblique)
#       * thickness from V6.1 default (alvenaria 0.14m) — refinement TBD.
#   - walls have no parent_wall_id; each entry IS a split segment.
#   - openings have:
#       * `chord_pt` (NOT `width`) for the door chord length in points
#       * `geometry_origin` ∈ {"svg_arc", "pipeline_gap"}
#       * `confidence` in [0..~1.2]
#       * no wall_a/wall_b — host wall must be searched geometrically
#         via nearest-segment lookup (deferred; the dry-run reports
#         the search step but does not commit to a host).
#   - rooms carry `polygon` (pt) and `label_qwen` (e.g. "Suite 01").
#
# This file does NOT replace `place_door_component.rb`; instead it
# delegates to `PlaceDoorComponent.place_door` for the svg_arc branch.
#
# Modes:
#   Consume.from_consensus(json_path, su_model)
#       Live mode — requires SketchUp Ruby API (Sketchup, Geom, Numeric#pt).
#   Consume.dry_run(json_path)
#       Vanilla-Ruby mode — emits a textual plan, no API calls.
#
# Usage from the SketchUp Ruby console:
#   load "E:/Claude/sketchup-mcp/skp_export/consume_consensus.rb"
#   Consume.from_consensus(
#     "E:/Claude/sketchup-mcp-exp-dedup/runs/final_planta_74/consensus_model.json",
#     Sketchup.active_model,
#   )

require "json"

module Consume
  WALL_HEIGHT_M             = 2.70
  ALVENARIA_THICKNESS_M     = 0.14
  DRYWALL_THICKNESS_M       = 0.075
  PT_TO_M                   = 0.000352778       # 1/72 inch in metres
  CONF_DOOR_COMPONENT_MIN   = 0.5               # threshold per spec
  ARC_ORIGIN                = "svg_arc"
  GAP_ORIGIN                = "pipeline_gap"

  # Override empirico de escala (debug knob). Quando setado, substitui
  # PT_TO_M na conversao pt -> world. Padrao nil = usa PT_TO_M.
  # Setar via env var CONSUME_SCALE_OVERRIDE quando precisar iterar
  # visualmente (ex: 0.01, 0.005). Memoria do user 2026-04-25:
  # planta sai "em pe / colapsada" sugere preciso testar valores.
  SCALE_OVERRIDE = (ENV["CONSUME_SCALE_OVERRIDE"] || "").strip.empty? ? nil : ENV["CONSUME_SCALE_OVERRIDE"].to_f

  # Default door component path (Trimble SketchUp 2026 sampler component
  # copiado para skp_export/components/ em 2026-04-25 como substituto
  # do "Porta de 70/80cm.skp" historico — folder E:/Claude/Cursos/ foi
  # removido). Resolvido relative a este arquivo.
  DEFAULT_DOOR_LIB = File.expand_path(
    "components/Door Interior.skp", __dir__
  )

  # Origem em pt-space, populada por compute_origin antes de criar
  # geometria. Permite normalizar todos os pts pra (0,0)+ no SU world
  # e inverter Y (PDF raster y-down -> SU y-up).
  @origin_pt = { min_x: 0.0, max_y: 0.0 }

  module_function

  # ---------------------------------------------------------------
  # PUBLIC ENTRY POINTS
  # ---------------------------------------------------------------

  # Live mode: builds geometry inside SketchUp.
  def from_consensus(json_path, su_model, door_lib: nil)
    raise "no active SketchUp model passed" if su_model.nil?
    raise "consensus_model.json not found: #{json_path}" unless File.exist?(json_path)

    require_relative "place_door_component" # SketchUp-only deps

    # Resolve door_lib: explicit param > DEFAULT_DOOR_LIB if exists > nil.
    # Quando nil, place_door_component cai em fallback procedural.
    if door_lib.nil? && File.exist?(DEFAULT_DOOR_LIB)
      door_lib = DEFAULT_DOOR_LIB
      warn("[consume_consensus] using default door component: #{door_lib}")
    end

    data  = JSON.parse(File.read(json_path, mode: "r:UTF-8"))
    plan  = build_plan(data)

    # Calcula origin (min_x, max_y) das walls em pt-space. Todas as
    # conversoes pt -> SU world em build_wall_su, build_room_su e
    # placement_record usam @origin_pt + Y invert + scale via
    # pt_to_world_m. Sem isso, planta fica off-origin no SU e Y
    # invertido (PDF raster y-down vs SU y-up).
    compute_origin(plan[:walls])

    su_model.start_operation("consume_consensus build", true)
    begin
      wall_groups = plan[:walls].map { |w| build_wall_su(su_model, w) }
      room_groups = plan[:rooms].map { |r| build_room_su(su_model, r) }

      placements = plan[:doors].map do |door|
        host = nearest_wall_for(door[:center_pt], plan[:walls])
        placement_record(door, host)
      end
      placements.each do |p|
        SkpExport::PlaceDoorComponent.place_door(
          su_model, p,
          doors_lib_path: door_lib,
          assume_upright: true,  # Default: SU sampler Door Interior.skp e modelado em pe
        )
      end

      plan[:gaps].each do |g|
        host = nearest_wall_for(g[:center_pt], plan[:walls])
        carve_gap_su(su_model, g, host) if host
      end

      summary = {
        walls: wall_groups.size,
        doors: placements.size,
        gaps:  plan[:gaps].size,
        rooms: room_groups.size,
      }
      warn("[consume_consensus] live build done: #{summary.inspect}")
      summary
    ensure
      su_model.commit_operation
    end
  end

  # Dry-run mode: prints what would happen, NO SketchUp API touched.
  # Returns the summary hash.
  def dry_run(json_path)
    raise "consensus_model.json not found: #{json_path}" unless File.exist?(json_path)

    data = JSON.parse(File.read(json_path, mode: "r:UTF-8"))
    plan = build_plan(data)
    compute_origin(plan[:walls])

    puts "=== consume_consensus DRY-RUN ==="
    puts "input: #{json_path}"
    puts "schema_version: #{data.dig('metadata', 'schema_version')}"
    puts "coordinate_space: #{data.dig('metadata', 'coordinate_space')}"
    puts "page_bounds: #{data.dig('metadata', 'page_bounds').inspect}"
    puts "origin_pt: #{@origin_pt.inspect}  scale: #{effective_scale} (#{SCALE_OVERRIDE ? 'override' : 'PT_TO_M default'})"
    puts ""

    puts "WALLS — would create #{plan[:walls].size} wall groups (height #{WALL_HEIGHT_M} m)"
    plan[:walls].first(3).each do |w|
      puts "  ex: #{w[:wall_id]} #{w[:orientation]} length=#{w[:length_m].round(3)}m thick=#{w[:thickness_m]}m"
    end
    puts "  ...(#{plan[:walls].size - 3} more)" if plan[:walls].size > 3
    puts ""

    puts "DOORS — would place #{plan[:doors].size} real components " \
         "(geometry_origin=#{ARC_ORIGIN}, confidence>=#{CONF_DOOR_COMPONENT_MIN})"
    plan[:doors].each do |d|
      host = nearest_wall_for(d[:center_pt], plan[:walls])
      host_id = host ? host[:wall_id] : "<none>"
      cx_m, cy_m = world_xy_m(*d[:center_pt])
      puts "  #{d[:opening_id]} chord=#{d[:chord_m].round(3)}m " \
           "center_m=(#{cx_m.round(3)}, #{cy_m.round(3)}) " \
           "host=#{host_id} thick=#{d[:wall_thickness_m]}m"
    end
    puts ""

    puts "GAPS  — would carve #{plan[:gaps].size} simple voids " \
         "(geometry_origin=#{GAP_ORIGIN}, no door component)"
    plan[:gaps].first(5).each do |g|
      host = nearest_wall_for(g[:center_pt], plan[:walls])
      host_id = host ? host[:wall_id] : "<none>"
      puts "  #{g[:opening_id]} chord=#{g[:chord_m].round(3)}m host=#{host_id}"
    end
    puts "  ...(#{plan[:gaps].size - 5} more)" if plan[:gaps].size > 5
    puts ""

    puts "ROOMS — would create #{plan[:rooms].size} named groups (label_qwen)"
    plan[:rooms].each do |r|
      puts "  #{r[:room_id]}  '#{r[:label]}' poly_pts=#{r[:polygon].size} area_m2=#{r[:area_m2].round(2)}"
    end
    puts ""

    summary = {
      walls: plan[:walls].size,
      doors: plan[:doors].size,
      gaps:  plan[:gaps].size,
      rooms: plan[:rooms].size,
    }
    puts "would create #{summary[:walls]} walls / #{summary[:doors]} doors / " \
         "#{summary[:gaps]} gaps / #{summary[:rooms]} rooms"
    summary
  end

  # ---------------------------------------------------------------
  # PLAN BUILDING (mode-agnostic — pure Ruby, no SketchUp API)
  # ---------------------------------------------------------------

  def build_plan(data)
    walls = (data["walls"] || []).map { |w| normalise_wall(w) }
    doors, gaps = [], []

    (data["openings"] || []).each do |o|
      record = normalise_opening(o)
      origin = o["geometry_origin"]
      conf   = (o["confidence"] || 0.0).to_f
      if origin == ARC_ORIGIN && conf >= CONF_DOOR_COMPONENT_MIN
        doors << record
      elsif origin == GAP_ORIGIN
        gaps << record
      else
        # Low-confidence svg_arc, or unknown origin — log and skip.
        warn("[consume_consensus] skipping opening #{o['opening_id']} " \
             "(origin=#{origin} conf=#{conf})")
      end
    end

    rooms = (data["rooms"] || []).map { |r| normalise_room(r) }

    { walls: walls, doors: doors, gaps: gaps, rooms: rooms }
  end

  def normalise_wall(w)
    sx, sy = w["start"].map(&:to_f)
    ex, ey = w["end"].map(&:to_f)
    dx     = ex - sx
    dy     = ey - sy
    length_pt = Math.hypot(dx, dy)
    angle_deg = (w["angle_deg"] || Math.atan2(dy, dx) * 180.0 / Math::PI).to_f
    orientation = classify_orientation(angle_deg)
    {
      wall_id:      w["wall_id"],
      start_pt:     [sx, sy],
      end_pt:       [ex, ey],
      length_pt:    length_pt,
      length_m:     length_pt * effective_scale,  # consistente com pt->world transform
      angle_deg:    angle_deg,
      orientation:  orientation,
      thickness_m:  ALVENARIA_THICKNESS_M, # default; refinement TBD
      confidence:   (w["confidence"] || 1.0).to_f,
      sources:      w["sources"] || [],
    }
  end

  def normalise_opening(o)
    cx_pt, cy_pt = o["center"].map(&:to_f)
    chord_pt     = (o["chord_pt"] || 0.0).to_f
    {
      opening_id:       o["opening_id"],
      center_pt:        [cx_pt, cy_pt],
      # center_m calculado em placement_record via pt_to_world_m
      # (precisa @origin_pt setado por compute_origin).
      chord_pt:         chord_pt,
      chord_m:          chord_pt * effective_scale,  # chord eh delta, sem origin shift / Y invert; mesmo scale que walls
      kind:             o["kind"] || "door",
      hinge_side:       o["hinge_side"],
      swing_deg:        o["swing_deg"],
      room_a:           o["room_a"],
      room_b:           o["room_b"],
      confidence:       (o["confidence"] || 0.0).to_f,
      geometry_origin:  o["geometry_origin"],
      wall_thickness_m: ALVENARIA_THICKNESS_M, # default; refined later
      axis:             nil,                   # set after host lookup
    }
  end

  def normalise_room(r)
    poly_pt_raw = r["polygon"] || []
    area_pt2 = (r["area"] || 0.0).to_f
    s = effective_scale
    {
      room_id:    r["room_id"],
      label:      r["label_qwen"] || r["room_id"],
      polygon_pt: poly_pt_raw.map { |xy| xy.map(&:to_f) },  # RAW pt — convertido em build_room_su via su_point
      area_m2:    area_pt2 * s * s,  # consistente com walls/openings; pt^2 -> m^2
      sources:    r["sources"] || [],
    }
  end

  def classify_orientation(angle_deg)
    a = angle_deg.abs % 180.0
    return "horizontal" if a <= 15.0 || a >= 165.0
    return "vertical"   if a >= 75.0 && a <= 105.0
    "oblique"
  end

  # ---------------------------------------------------------------
  # GEOMETRIC HELPERS
  # ---------------------------------------------------------------

  # Pick the wall whose centre line is closest to a point (in pt space).
  def nearest_wall_for(point_pt, walls)
    return nil if walls.empty?
    walls.min_by { |w| dist_point_to_segment(point_pt, w[:start_pt], w[:end_pt]) }
  end

  def dist_point_to_segment(p, a, b)
    px, py = p
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    seg_len2 = dx * dx + dy * dy
    return Math.hypot(px - ax, py - ay) if seg_len2 < 1e-9
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len2
    t = 0.0 if t < 0.0
    t = 1.0 if t > 1.0
    cx = ax + t * dx
    cy = ay + t * dy
    Math.hypot(px - cx, py - cy)
  end

  def placement_record(door, host)
    axis = host ? host[:orientation] : "horizontal"
    cx_pt, cy_pt = door[:center_pt]
    cx_m, cy_m   = world_xy_m(cx_pt, cy_pt)  # normalized + Y-inverted + scaled (meters)
    {
      opening_id:       door[:opening_id],
      center_m:         [cx_m, cy_m],
      width_m:          door[:chord_m],
      wall_thickness_m: host ? host[:thickness_m] : ALVENARIA_THICKNESS_M,
      axis:             axis,
      strategy:         :consensus_arc,
      hinge_side:       door[:hinge_side],
      swing_deg:        door[:swing_deg],
    }
  end

  # ---------------------------------------------------------------
  # COORD TRANSFORM (pt PDF-space -> SU world meters)
  # ---------------------------------------------------------------

  # Calcula origem (min_x, max_y) em pt-space a partir das walls.
  # Setado uma vez por run, antes de criar qualquer geometria.
  # Loga ranges pt + world (pre-validacao) pra debug determinacao.
  def compute_origin(walls)
    if walls.empty?
      @origin_pt = { min_x: 0.0, max_y: 0.0 }
      warn("[consume_consensus] empty walls — origin_pt zeroed")
      return @origin_pt
    end
    xs = walls.flat_map { |w| [w[:start_pt][0], w[:end_pt][0]] }
    ys = walls.flat_map { |w| [w[:start_pt][1], w[:end_pt][1]] }
    @origin_pt = { min_x: xs.min, max_y: ys.max }

    s = effective_scale
    # Preview do range em SU world (metros) ANTES de criar geometria
    # — sanity check do scale aplicado.
    world_x_max = (xs.max - xs.min) * s
    world_y_max = (ys.max - ys.min) * s
    warn("[consume_consensus] walls_pt_range:    x[#{xs.min.round(1)}..#{xs.max.round(1)}] y[#{ys.min.round(1)}..#{ys.max.round(1)}]")
    warn("[consume_consensus] origin_pt:         #{@origin_pt}")
    warn("[consume_consensus] effective_scale:   #{s}  (#{SCALE_OVERRIDE ? 'CONSUME_SCALE_OVERRIDE active' : 'PT_TO_M default'})")
    warn("[consume_consensus] walls_world_range: x[0..#{world_x_max.round(3)}m] y[0..#{world_y_max.round(3)}m] (pos Y-invert)")
    @origin_pt
  end

  def effective_scale
    SCALE_OVERRIDE || PT_TO_M
  end

  # ---------------------------------------------------------------
  # PRIMARY COORD TRANSFORM — single source of truth
  # ---------------------------------------------------------------

  # Converte (x_pt, y_pt) PDF coord-space pra (x_m, y_m) SU world meters:
  # 1) normaliza origem ao (min_x, max_y) das walls (compute_origin)
  # 2) inverte Y (PDF raster y-down -> SU world y-up)
  # 3) aplica effective_scale
  # Retorna pair de floats em metros — sem .m aplicado. Useful pra
  # dry-run mode (Ruby plain) onde Geom::Point3d nao existe.
  def world_xy_m(x_pt, y_pt)
    s = effective_scale
    nx_m = (x_pt - @origin_pt[:min_x]) * s
    ny_m = (@origin_pt[:max_y] - y_pt) * s   # INVERT Y
    [nx_m, ny_m]
  end

  # Live-mode wrapper: world_xy_m + Numeric#m + Point3d.
  # Use this pra QUALQUER conversao pt -> SU geometry. Single source
  # of truth pra walls, rooms, openings, doors. Z opcional em metros.
  def su_point(x_pt, y_pt, z_m = 0.0)
    nx_m, ny_m = world_xy_m(x_pt, y_pt)
    Geom::Point3d.new(nx_m.m, ny_m.m, z_m.m)
  end

  # DEPRECATED alias — mantido temporariamente pra compat externa.
  # Novos calls devem usar su_point (live) ou world_xy_m (pure).
  def pt_to_world_m(x_pt, y_pt)
    world_xy_m(x_pt, y_pt)
  end

  # ---------------------------------------------------------------
  # SKETCHUP-ONLY GEOMETRY (only called from from_consensus)
  # ---------------------------------------------------------------

  def build_wall_su(model, w)
    ents = model.active_entities
    group = ents.add_group
    g_ents = group.entities
    sx, sy = w[:start_pt]
    ex, ey = w[:end_pt]
    dx = ex - sx; dy = ey - sy
    length_pt = Math.hypot(dx, dy)
    return group if length_pt < 1e-6

    # half_thick em pt-space pra perp displacement no PDF coord-space.
    # Conversao pra SU world acontece DEPOIS via su_point. Usa
    # effective_scale (nao PT_TO_M) pra manter aspect ratio correto
    # quando SCALE_OVERRIDE estiver ativo.
    nx = -dy / length_pt
    ny =  dx / length_pt
    half_thick_pt = (w[:thickness_m] / effective_scale) / 2.0

    pts_pt = [
      [sx + nx * half_thick_pt, sy + ny * half_thick_pt],
      [ex + nx * half_thick_pt, ey + ny * half_thick_pt],
      [ex - nx * half_thick_pt, ey - ny * half_thick_pt],
      [sx - nx * half_thick_pt, sy - ny * half_thick_pt],
    ]
    # su_point: normaliza origem + inverte Y + aplica scale + retorna Point3d.
    face = g_ents.add_face(pts_pt.map { |x, y| su_point(x, y) })
    face.reverse! if face.normal.z < 0
    face.pushpull(WALL_HEIGHT_M.m)
    group.name = "Wall_#{w[:wall_id]}"
    group
  end

  def build_room_su(model, r)
    return nil if r[:polygon_pt].size < 3
    ents = model.active_entities
    group = ents.add_group
    g_ents = group.entities
    pts = r[:polygon_pt].map { |x, y| su_point(x, y) }
    face = g_ents.add_face(pts) rescue nil
    group.name = "Room_#{r[:label].to_s.gsub(/\s+/, '_')}"
    group
  end

  def carve_gap_su(model, gap, host)
    # Minimal scaffold — just records a face on the wall side. Real
    # carving is delegated to RebuildWalls.carve_door_hole in the live
    # build wired through main.rb. Here we noop and let a follow-up
    # pass do the boolean.
    nil
  end
end
