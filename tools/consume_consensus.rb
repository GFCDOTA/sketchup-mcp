# Consume consensus_model.json -> generate .skp
#
# Usage (run inside SketchUp via -RubyStartup):
#   ENV['CONSENSUS_JSON'] = 'E:/path/consensus_model.json'
#   ENV['SKP_OUT']        = 'E:/path/out.skp'
#   load 'consume_consensus.rb'
#
# Coordinate system: PDF points -> SketchUp inches.
# Each wall: filled rectangle (centerline + thickness) extruded WALL_HEIGHT_M up.
# Each room: floor face at z=0, colored.
# Soft barriers: short parapets (peitoril) at PARAPET_HEIGHT_M.

require 'json'

PT_TO_M = 0.19 / 5.4        # calibrated: wall thickness 5.4 pt -> 19 cm
M_TO_IN = 39.3700787402
PT_TO_IN = PT_TO_M * M_TO_IN

WALL_HEIGHT_M    = 2.70
PARAPET_HEIGHT_M = 1.10
WALL_HEIGHT_IN    = WALL_HEIGHT_M * M_TO_IN
PARAPET_HEIGHT_IN = PARAPET_HEIGHT_M * M_TO_IN

WALL_FILL_RGB    = [78, 78, 78]
PARAPET_RGB      = [130, 135, 140]   # médio cinza-concreto; antes era [200,220,230] (papel-de-parede)
PASSAGE_RGB      = [102, 187, 230]   # azul claro destacado pra ler em axon
PASSAGE_MARKER_HEIGHT_IN = 1.0       # 1 in (~2.5 cm) acima do chão pra ficar visível

# Door leaf (rendered for door_arc openings, post-carve)
DOOR_HEIGHT_M    = 2.10
DOOR_THICK_M     = 0.04
DOOR_HEIGHT_IN   = DOOR_HEIGHT_M * M_TO_IN
DOOR_THICK_IN    = DOOR_THICK_M  * M_TO_IN
DOOR_RGB         = [140, 95, 55]     # madeira escura
DOOR_SWING_DEG   = 30.0              # visual swing angle (deg open)

# Window panel (rendered for wall_gap openings, additive to passage marker)
WINDOW_SILL_M    = 0.90              # peitoril height (concrete to glass bottom)
WINDOW_HEAD_M    = 2.10              # verga / lintel bottom (glass top)
WINDOW_SILL_IN   = WINDOW_SILL_M  * M_TO_IN
WINDOW_HEAD_IN   = WINDOW_HEAD_M  * M_TO_IN
GLASS_RGB        = [180, 220, 240]   # azul-glass
GLASS_ALPHA      = 0.45
LINTEL_RGB       = [110, 115, 120]   # mesmo família do PARAPET_RGB

# Openings whose host wall must be split around them (true carving).
# wall_gap origin is intentionally absent: the gap is already in the wall
# data (the source PDF drew the flanking walls as separate filled
# rectangles), so carving would double-shrink the geometry.
CARVING_OPENING_ORIGINS = ['svg_arc', 'svg_segments'].freeze
ROOM_PALETTE = [
  [253, 226, 192], [200, 230, 201], [187, 222, 251], [248, 187, 208],
  [220, 237, 200], [255, 224, 178], [209, 196, 233], [179, 229, 252],
  [255, 249, 196], [245, 224, 208], [207, 216, 220],
]

def pdf_pt_to_su_pt(x, y)
  # Map PDF points (y-up) to SU inches (y-up). SU "1.0" unit = 1 inch.
  Geom::Point3d.new(x * PT_TO_IN, y * PT_TO_IN, 0.0)
end

def add_wall_volume(parent_entities, wall, thickness_pt, material)
  start_pt = wall['start']
  end_pt   = wall['end']
  ori = wall['orientation']
  if ori == 'h'
    x0 = [start_pt[0], end_pt[0]].min
    x1 = [start_pt[0], end_pt[0]].max
    cy = start_pt[1]
    corners_pdf = [
      [x0, cy - thickness_pt / 2.0],
      [x1, cy - thickness_pt / 2.0],
      [x1, cy + thickness_pt / 2.0],
      [x0, cy + thickness_pt / 2.0],
    ]
  else
    cx = start_pt[0]
    y0 = [start_pt[1], end_pt[1]].min
    y1 = [start_pt[1], end_pt[1]].max
    corners_pdf = [
      [cx - thickness_pt / 2.0, y0],
      [cx + thickness_pt / 2.0, y0],
      [cx + thickness_pt / 2.0, y1],
      [cx - thickness_pt / 2.0, y1],
    ]
  end
  pts = corners_pdf.map { |p| pdf_pt_to_su_pt(*p) }
  # Wrap each wall in its own Group so pushpull merging on adjacent
  # walls cannot delete refs we still hold.
  group = parent_entities.add_group
  group.name = wall['id'] if wall['id']
  face = group.entities.add_face(pts)
  return nil if face.nil?
  face.reverse! if face.normal.z < 0
  face.pushpull(WALL_HEIGHT_IN)
  group.entities.grep(Sketchup::Face).each do |fc|
    fc.material = material
    fc.back_material = material
  end
  group
end

def add_floor_face(entities, room, color)
  pts = room['polygon_pts'].map { |p| pdf_pt_to_su_pt(*p) }
  return nil if pts.length < 3
  begin
    face = entities.add_face(pts)
    return nil if face.nil?
    face.reverse! if face.normal.z < 0
    mat = Sketchup.active_model.materials.add("room_#{room['id']}")
    mat.color = Sketchup::Color.new(*color)
    mat.alpha = 0.6
    face.material = mat
    face.back_material = mat
    face
  rescue => e
    puts "[warn] room #{room['id']} face failed: #{e.message}"
    nil
  end
end

def _wall_footprints_in(walls, thickness_pt)
  # Pre-compute every wall's [xmin, ymin, xmax, ymax] footprint in SU
  # inches, so add_parapet can reject segments whose midpoint sits
  # inside a wall (= peitoril coincident with the building perimeter,
  # which renders as a "papel-de-parede" band on the wall).
  half = thickness_pt / 2.0
  walls.map do |w|
    sx, sy = w['start']
    ex, ey = w['end']
    if w['orientation'] == 'h'
      x0, x1 = [sx, ex].minmax
      y0, y1 = sy - half, sy + half
    else
      x0, x1 = sx - half, sx + half
      y0, y1 = [sy, ey].minmax
    end
    [x0 * PT_TO_IN, y0 * PT_TO_IN, x1 * PT_TO_IN, y1 * PT_TO_IN]
  end
end

def _segment_overlaps_wall?(p1, p2, footprints, tol_in: 1.0)
  # Sample 3 points (p1, midpoint, p2) and reject the segment if ANY of
  # them sits inside a wall footprint (within tol_in inches). Earlier
  # version sampled only the midpoint with tol_in=0.5, which let two
  # families through:
  #   1. long segments crossing a wall whose midpoint landed outside
  #   2. peitoris running parallel to the exterior wall face, offset
  #      ~1-3 cm by extractor jitter — these rendered as a 1.10m
  #      "rodapé" band on the wall.
  pts = [
    [p1.x, p1.y],
    [(p1.x + p2.x) / 2.0, (p1.y + p2.y) / 2.0],
    [p2.x, p2.y],
  ]
  footprints.any? do |x0, y0, x1, y1|
    pts.any? do |px, py|
      px >= x0 - tol_in && px <= x1 + tol_in &&
        py >= y0 - tol_in && py <= y1 + tol_in
    end
  end
end

def _kept_segments(axis_start, axis_end, carve_ranges)
  # Subtract the union of carve_ranges from [axis_start, axis_end].
  # Returns a list of [start, end] kept segments. Carve ranges may
  # extend past the wall axis on either side (clamped) or overlap each
  # other (merged via the cursor). Empty input or fully-carved input
  # both yield an empty list, in which case the wall is omitted entirely
  # — matching the pipeline invariant "do not invent geometry".
  return [] if axis_end <= axis_start
  sorted = carve_ranges.map { |s, e| [[s, e].min, [s, e].max] }
                       .sort_by { |s, _| s }
  kept = []
  cursor = axis_start.to_f
  sorted.each do |c_start, c_end|
    c_start = [c_start, axis_start].max
    c_end   = [c_end,   axis_end].min
    next if c_end <= cursor
    if c_start > cursor
      kept << [cursor, c_start]
    end
    cursor = [cursor, c_end].max
  end
  kept << [cursor, axis_end] if cursor < axis_end
  kept
end

def _carve_ranges_for(wall, openings_on_wall)
  # Each carving opening contributes [center_axis - width/2, center_axis + width/2]
  # along the wall's variable axis. The host wall's orientation decides
  # which coordinate component is the axis.
  axis_idx = wall['orientation'] == 'h' ? 0 : 1
  openings_on_wall.map do |op|
    half = op['opening_width_pts'].to_f / 2.0
    cx = op['center'][axis_idx]
    [cx - half, cx + half]
  end
end

def _wall_axis_range(wall)
  # Returns [axis_start, axis_end] along the wall's variable axis, sorted
  # ascending. start/end in the consensus may be in either direction.
  axis_idx = wall['orientation'] == 'h' ? 0 : 1
  s = wall['start'][axis_idx].to_f
  e = wall['end'][axis_idx].to_f
  [[s, e].min, [s, e].max]
end

def _emit_carved_wall(parent_entities, wall, segment, seg_idx, thickness_pt, material)
  # Build a sub-wall whose extent along the axis is [segment[0], segment[1]],
  # otherwise identical to the parent wall (same cross-axis centerline,
  # same orientation, same thickness). Group is named '<wall_id>_seg_<n>'
  # so the inspector can reconstruct the parent->sub mapping.
  s_start, s_end = segment
  return nil if s_end - s_start < 0.5  # smaller than 0.5 PDF pt -> drop
  if wall['orientation'] == 'h'
    cy = wall['start'][1]
    sub_wall = {
      'id'          => "#{wall['id']}_seg_#{seg_idx}",
      'start'       => [s_start, cy],
      'end'         => [s_end,   cy],
      'orientation' => 'h',
    }
  else
    cx = wall['start'][0]
    sub_wall = {
      'id'          => "#{wall['id']}_seg_#{seg_idx}",
      'start'       => [cx, s_start],
      'end'         => [cx, s_end],
      'orientation' => 'v',
    }
  end
  add_wall_volume(parent_entities, sub_wall, thickness_pt, material)
end

def add_carved_wall(parent_entities, wall, openings_on_wall, thickness_pt, material)
  # Splits the wall into sub-segments around each carving opening and
  # emits one SU group per kept segment. Returns the list of emitted
  # groups (may be empty if the wall is fully consumed by openings —
  # which would be a detector pathology, but we don't fabricate
  # geometry to compensate).
  axis_start, axis_end = _wall_axis_range(wall)
  carve = _carve_ranges_for(wall, openings_on_wall)
  segments = _kept_segments(axis_start, axis_end, carve)
  segments.each_with_index.map do |seg, idx|
    _emit_carved_wall(parent_entities, wall, seg, idx, thickness_pt, material)
  end.compact
end

def add_passage_marker(parent_entities, opening, walls_by_id, thickness_pt,
                        marker_material, layer)
  # Visual sentinel for an "open_passage" opening. The wall geometry already
  # has the gap (the source PDF drew the two flanking wall rectangles
  # separately), so there is nothing to CARVE — but a human reviewing the
  # SKP cannot tell whether a wall-line break is "passage detected" or
  # "wall ended here". This marker resolves that ambiguity by drawing a
  # thin floor-level rectangle inside the gap, oriented along the host
  # wall axis, sized to the detector's reported opening_width_pts.
  #
  # Schema: this function fires only for openings with
  # ``geometry_origin == "wall_gap"`` (see tools/detect_wall_gaps.py).
  # Other geometry_origins (svg_arc, svg_segments) sit on continuous
  # walls and require true carving — out of scope here.
  wall_id = opening['wall_id']
  wall = walls_by_id[wall_id]
  return nil unless wall
  center = opening['center']
  return nil unless center.is_a?(Array) && center.length >= 2
  width_pt = opening['opening_width_pts']
  return nil if width_pt.nil? || width_pt <= 0

  cx, cy = center
  ori = wall['orientation']
  if ori == 'h'
    corners_pdf = [
      [cx - width_pt / 2.0, cy - thickness_pt / 2.0],
      [cx + width_pt / 2.0, cy - thickness_pt / 2.0],
      [cx + width_pt / 2.0, cy + thickness_pt / 2.0],
      [cx - width_pt / 2.0, cy + thickness_pt / 2.0],
    ]
  else
    corners_pdf = [
      [cx - thickness_pt / 2.0, cy - width_pt / 2.0],
      [cx + thickness_pt / 2.0, cy - width_pt / 2.0],
      [cx + thickness_pt / 2.0, cy + width_pt / 2.0],
      [cx - thickness_pt / 2.0, cy + width_pt / 2.0],
    ]
  end
  pts = corners_pdf.map { |p| pdf_pt_to_su_pt(*p) }
  group = parent_entities.add_group
  group.name = "passage_#{opening['id']}" if opening['id']
  group.layer = layer if layer
  face = group.entities.add_face(pts)
  return nil if face.nil?
  face.reverse! if face.normal.z < 0
  face.pushpull(PASSAGE_MARKER_HEIGHT_IN)
  group.entities.grep(Sketchup::Face).each do |fc|
    fc.material = marker_material
    fc.back_material = marker_material
  end
  group
end

def add_parapet(entities, polyline_pts, parapet_material, layer,
                thickness_in: 1.5, wall_footprints: nil)
  return if polyline_pts.length < 2
  polyline_pts.each_cons(2).with_index do |(a, b), idx|
    next if a == b
    p1 = pdf_pt_to_su_pt(*a)
    p2 = pdf_pt_to_su_pt(*b)
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    len = Math.sqrt(dx * dx + dy * dy)
    next if len < 0.01
    # Drop parapet segments whose midpoint sits inside a wall footprint
    # — those are the perimeter of the building outline that the
    # vector extractor catches as soft_barrier, not real peitoris. They
    # were rendering as a 1.10m-tall "wallpaper" band on the wall.
    if wall_footprints && _segment_overlaps_wall?(p1, p2, wall_footprints)
      next
    end
    nx = -dy / len * (thickness_in / 2.0)
    ny =  dx / len * (thickness_in / 2.0)
    quad = [
      Geom::Point3d.new(p1.x + nx, p1.y + ny, 0),
      Geom::Point3d.new(p2.x + nx, p2.y + ny, 0),
      Geom::Point3d.new(p2.x - nx, p2.y - ny, 0),
      Geom::Point3d.new(p1.x - nx, p1.y - ny, 0),
    ]
    group = entities.add_group
    group.name = "parapet_#{idx}"
    group.layer = layer if layer
    face = group.entities.add_face(quad) rescue nil
    next if face.nil?
    face.reverse! if face.normal.z < 0
    face.pushpull(PARAPET_HEIGHT_IN)
    group.entities.grep(Sketchup::Face).each do |fc|
      fc.material = parapet_material
      fc.back_material = parapet_material
    end
  end
end

def _opening_axis_basis(wall)
  # Returns [axis_idx, cross_idx, cross_value] for the wall.
  # axis_idx is the index (0=x, 1=y) of the wall's variable axis;
  # cross_idx is the perpendicular index; cross_value is the wall
  # centerline coordinate on the cross axis (in PDF pts).
  if wall['orientation'] == 'h'
    [0, 1, wall['start'][1].to_f]
  else
    [1, 0, wall['start'][0].to_f]
  end
end

def add_door_leaf(parent_entities, opening, walls_by_id, thickness_pt,
                   door_material, layer)
  # Render a door leaf (single panel, swung open by DOOR_SWING_DEG)
  # at the hinge side of the opening. The host wall is already CARVED
  # by add_carved_wall (see CARVING_OPENING_ORIGINS); this function
  # just inserts the visible swing geometry inside the carved gap.
  #
  # Schema: fires only for openings with kind_v5 == 'door_arc' AND
  # geometry_origin == 'svg_arc' (= already carved).
  # Reads: wall_id, center, opening_width_pts, hinge ('left'|'right').
  wall_id = opening['wall_id']
  wall = walls_by_id[wall_id]
  return nil unless wall
  center = opening['center']
  return nil unless center.is_a?(Array) && center.length >= 2
  width_pt = opening['opening_width_pts']
  return nil if width_pt.nil? || width_pt <= 0
  hinge_side = opening['hinge'] || 'left'

  axis_idx, cross_idx, cross_value = _opening_axis_basis(wall)
  axis_center = center[axis_idx].to_f
  half = width_pt / 2.0

  # Hinge axis location along the wall: 'left' = lower axis coord,
  # 'right' = higher. Door leaf base sits at the hinge edge of the
  # opening, panel extends along the wall axis CLOSED, then we rotate
  # DOOR_SWING_DEG around the hinge (vertical Z axis at hinge point).
  hinge_axis = hinge_side == 'right' ? axis_center + half : axis_center - half
  panel_far_axis  = hinge_side == 'right' ? axis_center - half : axis_center + half
  cross_inner = cross_value - thickness_pt / 2.0  # arbitrary face of wall
  cross_outer = cross_value + thickness_pt / 2.0

  # Build closed panel as 4 PDF-pt corners. Panel sits at the
  # cross-centerline (centro da espessura da parede), so swung edges
  # don't overlap the wall.
  panel_cross = cross_value
  if axis_idx == 0
    # horizontal wall: axis is X, cross is Y
    p_hinge_inner = [hinge_axis,    panel_cross]
    p_hinge_outer = [hinge_axis,    panel_cross]  # degenerate; panel has no thickness in PDF coords
    p_far_inner   = [panel_far_axis, panel_cross]
    p_far_outer   = [panel_far_axis, panel_cross]
  else
    p_hinge_inner = [panel_cross, hinge_axis]
    p_far_inner   = [panel_cross, panel_far_axis]
  end
  # We render the leaf as a vertical face in SU 3D (pushpull thickness
  # afterwards). Build the 2 floor-level base points first.
  hinge_pt = pdf_pt_to_su_pt(*p_hinge_inner)
  far_pt   = pdf_pt_to_su_pt(*p_far_inner)
  hinge_pt_top = Geom::Point3d.new(hinge_pt.x, hinge_pt.y, DOOR_HEIGHT_IN)
  far_pt_top   = Geom::Point3d.new(far_pt.x,   far_pt.y,   DOOR_HEIGHT_IN)

  group = parent_entities.add_group
  group.name = "door_leaf_#{opening['id']}" if opening['id']
  group.layer = layer if layer
  face = group.entities.add_face([hinge_pt, far_pt, far_pt_top, hinge_pt_top])
  return nil if face.nil?
  face.reverse! if face.normal.z < 0
  # Give it physical thickness (pushpull along face normal)
  face.pushpull(DOOR_THICK_IN)
  group.entities.grep(Sketchup::Face).each do |fc|
    fc.material = door_material
    fc.back_material = door_material
  end

  # Rotate the panel DOOR_SWING_DEG around the hinge vertical axis so
  # the swing is visible. Rotation point = hinge floor-level; axis = Z.
  swing_dir = hinge_side == 'right' ? -1.0 : 1.0
  rotation = Geom::Transformation.rotation(
    hinge_pt,
    Geom::Vector3d.new(0, 0, 1),
    swing_dir * DOOR_SWING_DEG.degrees,
  )
  group.transform!(rotation)
  group
rescue => e
  puts "[warn] door_leaf opening=#{opening['id']} failed: #{e.message}"
  nil
end

def _wall_gap_corners_pdf(wall, center, width_pt, thickness_pt)
  cx, cy = center
  if wall['orientation'] == 'h'
    [
      [cx - width_pt / 2.0, cy - thickness_pt / 2.0],
      [cx + width_pt / 2.0, cy - thickness_pt / 2.0],
      [cx + width_pt / 2.0, cy + thickness_pt / 2.0],
      [cx - width_pt / 2.0, cy + thickness_pt / 2.0],
    ]
  else
    [
      [cx - thickness_pt / 2.0, cy - width_pt / 2.0],
      [cx + thickness_pt / 2.0, cy - width_pt / 2.0],
      [cx + thickness_pt / 2.0, cy + width_pt / 2.0],
      [cx - thickness_pt / 2.0, cy + width_pt / 2.0],
    ]
  end
end

def _emit_box_at(parent_entities, corners_pdf, z_bottom_in, z_top_in,
                  material, name, layer)
  return nil if z_top_in - z_bottom_in <= 0.001
  pts_floor = corners_pdf.map { |p| pdf_pt_to_su_pt(*p) }
  pts_floor.each { |p| p.z = z_bottom_in }
  group = parent_entities.add_group
  group.name = name if name
  group.layer = layer if layer
  face = group.entities.add_face(pts_floor)
  return nil if face.nil?
  face.reverse! if face.normal.z < 0
  face.pushpull(z_top_in - z_bottom_in)
  group.entities.grep(Sketchup::Face).each do |fc|
    fc.material = material
    fc.back_material = material
  end
  group
end

def add_window_panel(parent_entities, opening, walls_by_id, thickness_pt,
                      sill_material, glass_material, lintel_material, layer)
  # Render a 3-band window assembly inside a wall_gap: peitoril
  # (concrete 0 -> WINDOW_SILL_IN) + vidro (glass WINDOW_SILL_IN ->
  # WINDOW_HEAD_IN) + verga (concrete WINDOW_HEAD_IN -> WALL_HEIGHT_IN).
  # Width = opening_width_pts; depth = wall thickness.
  #
  # CAVEAT (caminho A): we render every wall_gap as a window. Some
  # wall_gaps in real plants are interior passages (e.g. sala -> jantar
  # without a door). Caminho B will classify wall_gap into
  # window | passage based on adjacent room context. For now the
  # passage_marker rectangle still emits to the 'passages' layer so a
  # human can isolate / delete window groups that should be passages.
  wall_id = opening['wall_id']
  wall = walls_by_id[wall_id]
  return nil unless wall
  center = opening['center']
  return nil unless center.is_a?(Array) && center.length >= 2
  width_pt = opening['opening_width_pts']
  return nil if width_pt.nil? || width_pt <= 0

  corners = _wall_gap_corners_pdf(wall, center, width_pt, thickness_pt)
  oid = opening['id']
  groups = []
  groups << _emit_box_at(parent_entities, corners, 0.0, WINDOW_SILL_IN,
                         sill_material, "window_sill_#{oid}", layer)
  groups << _emit_box_at(parent_entities, corners, WINDOW_SILL_IN,
                         WINDOW_HEAD_IN, glass_material,
                         "window_glass_#{oid}", layer)
  groups << _emit_box_at(parent_entities, corners, WINDOW_HEAD_IN,
                         WALL_HEIGHT_IN, lintel_material,
                         "window_lintel_#{oid}", layer)
  groups.compact
rescue => e
  puts "[warn] window_panel opening=#{opening['id']} failed: #{e.message}"
  []
end

def reset_model(model)
  # Wipe everything that came from the template (default Sree figure,
  # template-bundled materials/components/layers) AND from any previous
  # consume run. Without this the same file builds 2x or 3x in place,
  # producing wall_dark1/wall_dark2 + room_r1..r11/r12..r22 duplicates
  # and z-fighting white seams along every wall.
  model.entities.clear!
  model.definitions.purge_unused
  begin
    model.materials.purge_unused
  rescue
  end
  begin
    # Layers API renamed to layers/tags in newer SU; either works.
    layers = model.layers
    layers.purge_unused if layers.respond_to?(:purge_unused)
  rescue
  end
end

def ensure_layer(model, name)
  existing = model.layers[name]
  return existing if existing
  model.layers.add(name)
end

def main
  # Paths set by the launcher (tools/skp_from_consensus.py): the
  # launcher overwrites these two lines before launching SketchUp.
  cjson = 'CONSENSUS_PATH_PLACEHOLDER'
  out   = 'SKP_OUT_PATH_PLACEHOLDER'
  cjson = ENV['CONSENSUS_JSON'] if ENV['CONSENSUS_JSON']
  out   = ENV['SKP_OUT'] if ENV['SKP_OUT']
  puts "[consume] reading #{cjson}"
  data = JSON.parse(File.read(cjson))

  model = Sketchup.active_model
  reset_model(model)
  model.start_operation('build_from_consensus', true)
  ents = model.active_entities

  walls_layer    = ensure_layer(model, 'walls')
  parapets_layer = ensure_layer(model, 'parapets')
  rooms_layer    = ensure_layer(model, 'rooms')
  passages_layer = ensure_layer(model, 'passages')
  doors_layer    = ensure_layer(model, 'doors')
  windows_layer  = ensure_layer(model, 'windows')

  thickness_pt = data['wall_thickness_pts']
  walls = data['walls'] || []
  openings_all = data['openings'] || []
  # Index carving openings by host wall_id. Skip wall_gap origin: the gap
  # is already in the wall data and re-carving would shrink the flanking
  # walls a second time. See CARVING_OPENING_ORIGINS above.
  carving_openings_by_wall = Hash.new { |h, k| h[k] = [] }
  openings_all.each do |op|
    next unless CARVING_OPENING_ORIGINS.include?(op['geometry_origin'])
    next unless op['wall_id']
    carving_openings_by_wall[op['wall_id']] << op
  end
  puts "[consume] walls: #{walls.length}"
  carving_count = carving_openings_by_wall.values.map(&:length).sum
  puts "[consume] carving_openings: #{carving_count}"

  wall_mat = model.materials.add('wall_dark')
  wall_mat.color = Sketchup::Color.new(*WALL_FILL_RGB)

  carved_subwall_count = 0
  walls.each do |w|
    openings_on_w = carving_openings_by_wall[w['id']]
    if openings_on_w.empty?
      grp = add_wall_volume(ents, w, thickness_pt, wall_mat)
      grp.layer = walls_layer if grp
    else
      grps = add_carved_wall(ents, w, openings_on_w, thickness_pt, wall_mat)
      grps.each { |g| g.layer = walls_layer if g }
      carved_subwall_count += grps.length
    end
  end
  if carving_count > 0
    puts "[consume] carved subwalls emitted: #{carved_subwall_count}"
  end

  rooms = data['rooms'] || []
  puts "[consume] rooms: #{rooms.length}"
  rooms.each_with_index do |r, i|
    f = add_floor_face(ents, r, ROOM_PALETTE[i % ROOM_PALETTE.length])
    f.layer = rooms_layer if f
  end

  parapet_mat = model.materials.add('parapet')
  parapet_mat.color = Sketchup::Color.new(*PARAPET_RGB)
  barriers = data['soft_barriers'] || []
  puts "[consume] soft_barriers: #{barriers.length}"
  wall_footprints = _wall_footprints_in(walls, thickness_pt)
  barriers.each do |b|
    add_parapet(ents, b['polyline_pts'], parapet_mat, parapets_layer,
                wall_footprints: wall_footprints)
  end

  # Wall-gap passage markers — visible sentinels for openings whose
  # gap is already in the wall geometry (geometry_origin == 'wall_gap').
  # See tools/detect_wall_gaps.py for the producer side.
  # door_arc / svg_segments openings are carved into walls in the loop
  # above (search add_carved_wall); they don't get markers because the
  # carved gap is the marker.
  openings = openings_all
  walls_by_id = walls.each_with_object({}) { |w, h| h[w['id']] = w if w['id'] }
  passage_mat = model.materials.add('passage_marker')
  passage_mat.color = Sketchup::Color.new(*PASSAGE_RGB)
  passage_count = 0
  openings.each do |op|
    next unless op['geometry_origin'] == 'wall_gap'
    grp = add_passage_marker(ents, op, walls_by_id, thickness_pt,
                              passage_mat, passages_layer)
    passage_count += 1 if grp
  end
  puts "[consume] passages: #{passage_count}"

  # Door leaves — visible swing panel inside each carved door_arc gap.
  # Reads opening['hinge'] to decide swing direction. door_arc openings
  # are already CARVED above; this adds the panel.
  door_mat = model.materials.add('door_leaf')
  door_mat.color = Sketchup::Color.new(*DOOR_RGB)
  door_count = 0
  openings.each do |op|
    next unless op['kind_v5'] == 'door_arc' || op['geometry_origin'] == 'svg_arc'
    grp = add_door_leaf(ents, op, walls_by_id, thickness_pt, door_mat,
                         doors_layer)
    door_count += 1 if grp
  end
  puts "[consume] door_leaves: #{door_count}"

  # Window panels — peitoril + glass + verga inside each wall_gap.
  # Caminho A: every wall_gap rendered as window. Passage marker still
  # emitted (above) so designer can isolate misclassified wall_gaps.
  sill_mat = model.materials.add('window_sill')
  sill_mat.color = Sketchup::Color.new(*PARAPET_RGB)
  glass_mat = model.materials.add('window_glass')
  glass_mat.color = Sketchup::Color.new(*GLASS_RGB)
  glass_mat.alpha = GLASS_ALPHA
  lintel_mat = model.materials.add('window_lintel')
  lintel_mat.color = Sketchup::Color.new(*LINTEL_RGB)
  window_count = 0
  openings.each do |op|
    next unless op['geometry_origin'] == 'wall_gap'
    grps = add_window_panel(ents, op, walls_by_id, thickness_pt,
                             sill_mat, glass_mat, lintel_mat,
                             windows_layer)
    window_count += 1 unless grps.empty?
  end
  puts "[consume] windows: #{window_count}"

  model.commit_operation
  status = model.save(out)
  puts "[consume] saved -> #{out} (status=#{status})"
  # Frame the build: zoom extents + iso view
  begin
    Sketchup.send_action('viewIso:')
    Sketchup.active_model.active_view.zoom_extents
  rescue
  end
end

begin
  main
rescue => e
  puts "[ERR] #{e.class}: #{e.message}"
  e.backtrace.each { |l| puts "  #{l}" }
end
