# Build a single-extruded rectangular wall ring from a consensus JSON.
#
# Loaded by autorun_consume.rb when autorun_control.txt's line 3
# points here instead of consume_consensus.rb.
#
# Reads ENV['CONSENSUS_JSON'] and ENV['SKP_OUT'] (set by autorun).
# Derives a PNG screenshot path from SKP_OUT (replace .skp -> .png).
#
# Geometry strategy (the point of this exporter):
#   1. Find the bounding rectangle of the wall centerlines.
#   2. Build OUTER ring rect = centerline_bbox expanded by +thickness/2.
#   3. Build INNER ring rect = centerline_bbox shrunken by -thickness/2.
#   4. Add the outer face. Add the inner face inside it; SU detects
#      "face within face" and turns the outer into a face-with-hole.
#   5. Erase the inner face (the edges stay, the hole stays).
#   6. PushPull the ring face ONCE -> single hollow box, no internal
#      partitions, no overlapping corner pillars, top of the ring is
#      a continuous rectangular frame.
#
# This is intentionally narrow: it only handles axis-aligned rectangular
# rooms where the 4 wall centerlines form a closed rectangle. It is
# NOT a replacement for consume_consensus.rb, which has to handle
# partial walls, openings, multi-room plans, soft barriers, etc.

require 'json'

PT_TO_M  = 0.19 / 5.4         # same calibration as consume_consensus.rb
M_TO_IN  = 39.3700787402
PT_TO_IN = PT_TO_M * M_TO_IN

WALL_HEIGHT_M  = 2.70
WALL_HEIGHT_IN = WALL_HEIGHT_M * M_TO_IN
WALL_RGB       = [78, 78, 78]
FLOOR_RGB      = [232, 224, 208]  # light beige, reads as "interior floor"

def pdf_pt_to_su(pt)
  Geom::Point3d.new(pt[0] * PT_TO_IN, pt[1] * PT_TO_IN, 0.0)
end

def compute_outer_inner(walls, thickness_pt, dimension_mode)
  # The bbox of the wall start/end points means different things
  # depending on the consensus' dimension_mode:
  #
  #   "centerline"  (default, legacy) - bbox IS the wall centerlines.
  #                  Outer rect = bbox grown by +thickness/2.
  #                  Inner rect = bbox shrunk by -thickness/2.
  #
  #   "inner_clear" - bbox IS the inner boundary of the room (the
  #                  clear interior). Outer rect = bbox grown by
  #                  +thickness. Inner rect = bbox unchanged. This
  #                  is the mode an architect uses when stating
  #                  "I want a 4.0 x 4.0 room".
  #
  #   "outer"      - bbox IS the outer boundary of the wall ring.
  #                  Outer rect = bbox unchanged.
  #                  Inner rect = bbox shrunk by -thickness.
  #
  # In all three modes the resulting wall thickness is identical;
  # only the anchor changes.
  xs = walls.flat_map { |w| [w['start'][0], w['end'][0]] }
  ys = walls.flat_map { |w| [w['start'][1], w['end'][1]] }
  cx_min, cx_max = xs.minmax
  cy_min, cy_max = ys.minmax

  case dimension_mode
  when 'centerline'
    half = thickness_pt / 2.0
    ox_min, ox_max = cx_min - half, cx_max + half
    oy_min, oy_max = cy_min - half, cy_max + half
    ix_min, ix_max = cx_min + half, cx_max - half
    iy_min, iy_max = cy_min + half, cy_max - half
  when 'inner_clear'
    ix_min, ix_max = cx_min, cx_max
    iy_min, iy_max = cy_min, cy_max
    ox_min, ox_max = cx_min - thickness_pt, cx_max + thickness_pt
    oy_min, oy_max = cy_min - thickness_pt, cy_max + thickness_pt
  when 'outer'
    ox_min, ox_max = cx_min, cx_max
    oy_min, oy_max = cy_min, cy_max
    ix_min, ix_max = cx_min + thickness_pt, cx_max - thickness_pt
    iy_min, iy_max = cy_min + thickness_pt, cy_max - thickness_pt
  else
    raise "unknown dimension_mode: #{dimension_mode.inspect} " \
          "(expected centerline | inner_clear | outer)"
  end

  outer = [[ox_min, oy_min], [ox_max, oy_min],
           [ox_max, oy_max], [ox_min, oy_max]]
  inner = [[ix_min, iy_min], [ix_max, iy_min],
           [ix_max, iy_max], [ix_min, iy_max]]
  [outer, inner]
end

def build_wall_shell(parent_ents, outer, inner, material)
  # Builds the ring inside its own named Group ("WallShell_Group")
  # so the wall geometry is isolated from any sibling group (e.g.
  # Floor_Group). Returns the group.
  group = parent_ents.add_group
  group.name = 'WallShell_Group'
  ents = group.entities

  outer_pts = outer.map { |p| pdf_pt_to_su(p) }
  inner_pts = inner.map { |p| pdf_pt_to_su(p) }

  # Step A: outer face.
  outer_face = ents.add_face(outer_pts)
  raise 'outer face creation failed' if outer_face.nil?

  # Step B: inner face. SU sees it lies entirely inside outer_face
  # and automatically converts outer into a face-with-hole.
  inner_face = ents.add_face(inner_pts)
  raise 'inner face creation failed' if inner_face.nil?

  # Step C: erase the inner core; edges stay (they bound the donut).
  inner_face.erase!

  # Re-locate the donut face after SU's split.
  ring_face = ents.grep(Sketchup::Face).find { |f| f.loops.length == 2 }
  raise 'ring face not found after hole carve' if ring_face.nil?
  ring_face.reverse! if ring_face.normal.z < 0

  # Step D: ONE pushpull -> single hollow solid.
  ring_face.pushpull(WALL_HEIGHT_IN)

  # Apply wall material to every face of the resulting solid.
  ents.grep(Sketchup::Face).each do |f|
    f.material      = material
    f.back_material = material
  end
  group
end

def build_floor(parent_ents, inner, material)
  # A flat floor face at z=0 inside the inner ring. No pushpull —
  # it must remain a single 2D face, "carpet style".
  group = parent_ents.add_group
  group.name = 'Floor_Group'
  ents = group.entities

  inner_pts = inner.map { |p| pdf_pt_to_su(p) }
  face = ents.add_face(inner_pts)
  raise 'floor face creation failed' if face.nil?
  face.reverse! if face.normal.z < 0
  face.material      = material
  face.back_material = material
  group
end

def setup_axon_camera(model)
  view = model.active_view
  bbox = model.bounds
  center = bbox.center
  diag = bbox.diagonal

  # Place the camera FAR along the iso direction. In orthographic
  # mode, the eye position only sets the viewing direction; cam.height
  # controls the visible extent. Make height >= the bbox diagonal so
  # the model fits with some margin.
  d = diag * 5.0
  eye = Geom::Point3d.new(
    center.x + d,
    center.y - d,
    center.z + d,
  )
  cam = Sketchup::Camera.new(eye, center, Geom::Vector3d.new(0, 0, 1))
  cam.perspective = false
  cam.height = diag * 1.4   # orthographic vertical extent (in inches)
  view.camera = cam
end

def group_face_records(group)
  faces = group.entities.grep(Sketchup::Face)
  faces.map do |fc|
    n = fc.normal
    {
      'loops'       => fc.loops.length,
      'outer_verts' => fc.outer_loop.vertices.length,
      'normal'      => [n.x.round(4), n.y.round(4), n.z.round(4)],
      'area_in2'    => fc.area.round(2),
      'area_m2'     => (fc.area / (M_TO_IN * M_TO_IN)).round(4),
    }
  end
end

def write_geometry_report(model, report_path, ctx)
  ents = model.active_entities
  groups = ents.grep(Sketchup::Group)
  wall_group  = groups.find { |g| g.name == 'WallShell_Group' }
  floor_group = groups.find { |g| g.name == 'Floor_Group' }

  wall_faces  = wall_group  ? wall_group.entities.grep(Sketchup::Face)  : []
  wall_edges  = wall_group  ? wall_group.entities.grep(Sketchup::Edge)  : []
  floor_faces = floor_group ? floor_group.entities.grep(Sketchup::Face) : []
  floor_edges = floor_group ? floor_group.entities.grep(Sketchup::Edge) : []

  top_or_bottom = wall_faces.select { |f| f.normal.z.abs > 0.99 }
  report = {
    'schema_version' => '1.0.0',
    'tool'           => 'build_room_ring_skp',
    'consensus_path' => ctx[:consensus_path],
    'skp_path'       => ctx[:skp_path],
    'dimension_mode' => ctx[:dimension_mode],
    'wall_shell' => {
      'group_name'           => 'WallShell_Group',
      'present'              => !wall_group.nil?,
      'faces'                => wall_faces.length,
      'edges'                => wall_edges.length,
      'faces_with_holes'     => wall_faces.count { |f| f.loops.length > 1 },
      'top_bottom_face_count' => top_or_bottom.length,
      'top_bottom_loops'     => top_or_bottom.map { |f| f.loops.length },
      'faces_detail'         => group_face_records(wall_group),
    },
    'floor_face' => {
      'group_name' => 'Floor_Group',
      'present'    => !floor_group.nil?,
      'faces'      => floor_faces.length,
      'edges'      => floor_edges.length,
      'faces_detail' => group_face_records(floor_group),
    },
    'totals' => {
      'groups' => groups.length,
      'faces' => wall_faces.length + floor_faces.length,
      'edges' => wall_edges.length + floor_edges.length,
    },
    'bbox' => {
      'outer_x_m'        => ctx[:outer_w_m].round(4),
      'outer_y_m'        => ctx[:outer_h_m].round(4),
      'inner_x_m'        => ctx[:inner_w_m].round(4),
      'inner_y_m'        => ctx[:inner_h_m].round(4),
      'wall_thickness_m' => ctx[:thickness_m].round(4),
      'wall_height_m'    => WALL_HEIGHT_M.round(4),
    },
  }
  File.write(report_path, JSON.pretty_generate(report))
end

def write_png(model, png_path)
  options = {
    :filename   => png_path,
    :width      => 1600,
    :height     => 1200,
    :antialias  => true,
    :compression => 0.95,
    :transparent => false,
  }
  model.active_view.write_image(options)
end

# ===== Main =====

cjson    = ENV['CONSENSUS_JSON'] or raise 'CONSENSUS_JSON env not set'
outskp   = ENV['SKP_OUT']        or raise 'SKP_OUT env not set'
# PNG_OUT and REPORT_OUT are optional; sensible defaults derive from
# the .skp basename if the launcher didn't pass explicit paths.
outpng    = ENV['PNG_OUT']    || outskp.sub(/\.skp$/i, '.png')
outreport = ENV['REPORT_OUT'] || outskp.sub(/\.skp$/i, '_geometry_report.json')

puts "[ring] consensus=#{cjson}"
puts "[ring] out_skp=#{outskp}"
puts "[ring] out_png=#{outpng}"
puts "[ring] out_report=#{outreport}"

data = JSON.parse(File.read(cjson))
thickness_pt = data['wall_thickness_pts'] or raise 'wall_thickness_pts missing'
walls = data['walls'] || []
raise 'walls array empty' if walls.empty?

# Legacy consensus files (no dimension_mode key) default to centerline,
# which is the historical interpretation of walls.start/end.
dimension_mode = data['dimension_mode'] || 'centerline'
puts "[ring] dimension_mode=#{dimension_mode}"

outer, inner = compute_outer_inner(walls, thickness_pt, dimension_mode)

# Compute metres for the report (outer/inner are in PDF points).
ox = outer.map { |p| p[0] }
oy = outer.map { |p| p[1] }
ix = inner.map { |p| p[0] }
iy = inner.map { |p| p[1] }
outer_w_m = (ox.max - ox.min) * PT_TO_M
outer_h_m = (oy.max - oy.min) * PT_TO_M
inner_w_m = (ix.max - ix.min) * PT_TO_M
inner_h_m = (iy.max - iy.min) * PT_TO_M
thickness_m = thickness_pt * PT_TO_M
puts "[ring] outer=#{outer_w_m.round(3)}×#{outer_h_m.round(3)}m " \
     "inner=#{inner_w_m.round(3)}×#{inner_h_m.round(3)}m " \
     "wall=#{(thickness_m*100).round(1)}cm"

model = Sketchup.active_model
model.entities.clear!
model.definitions.purge_unused
model.start_operation('build_room', true)

wall_mat = model.materials.add('wall_ring')
wall_mat.color = Sketchup::Color.new(*WALL_RGB)
floor_mat = model.materials.add('floor_interior')
floor_mat.color = Sketchup::Color.new(*FLOOR_RGB)

build_wall_shell(model.active_entities, outer, inner, wall_mat)
build_floor(model.active_entities, inner, floor_mat)

model.commit_operation

# Geometry report (JSON) before save — same file appears in the
# golden fixtures alongside the .skp.
ctx = {
  consensus_path: cjson,
  skp_path:       outskp,
  dimension_mode: dimension_mode,
  outer_w_m:      outer_w_m,
  outer_h_m:      outer_h_m,
  inner_w_m:      inner_w_m,
  inner_h_m:      inner_h_m,
  thickness_m:    thickness_m,
}
write_geometry_report(model, outreport, ctx)
puts "[ring] wrote #{outreport}"

# Screenshot FIRST (before saving .skp): the Python launcher polls
# for the .skp and terminates SU the instant the file appears.
setup_axon_camera(model)
write_png(model, outpng)
puts "[ring] wrote #{outpng}"

# Save the .skp last — this is the launcher's exit signal.
status = model.save(outskp)
puts "[ring] saved #{outskp} (status=#{status})"
