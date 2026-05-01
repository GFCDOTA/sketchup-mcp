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

PT_TO_M = 0.0254 / 8.0      # 1 PDF pt at this drawing scale ≈ 3.5 cm
                             # (calibrated: wall thickness 5.4 pt = 19 cm)
M_TO_IN = 39.3700787402
PT_TO_IN = PT_TO_M * M_TO_IN

WALL_HEIGHT_M    = 2.70
PARAPET_HEIGHT_M = 1.10
WALL_HEIGHT_IN    = WALL_HEIGHT_M * M_TO_IN
PARAPET_HEIGHT_IN = PARAPET_HEIGHT_M * M_TO_IN

WALL_FILL_RGB    = [78, 78, 78]
PARAPET_RGB      = [200, 220, 230]
ROOM_PALETTE = [
  [253, 226, 192], [200, 230, 201], [187, 222, 251], [248, 187, 208],
  [220, 237, 200], [255, 224, 178], [209, 196, 233], [179, 229, 252],
  [255, 249, 196], [245, 224, 208], [207, 216, 220],
]

def pdf_pt_to_su_pt(x, y)
  # Map PDF points (y-up) to SU inches (y-up). SU "1.0" unit = 1 inch.
  Geom::Point3d.new(x * PT_TO_IN, y * PT_TO_IN, 0.0)
end

def add_wall_volume(entities, wall, thickness_pt)
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
  face = entities.add_face(pts)
  face.reverse! if face.normal.z < 0
  face.pushpull(WALL_HEIGHT_IN)
  group = nil
  face
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

def add_parapet(entities, polyline_pts, thickness_in: 1.5)
  return if polyline_pts.length < 2
  polyline_pts.each_cons(2) do |a, b|
    next if a == b
    p1 = pdf_pt_to_su_pt(*a)
    p2 = pdf_pt_to_su_pt(*b)
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    len = Math.sqrt(dx * dx + dy * dy)
    next if len < 0.01
    nx = -dy / len * (thickness_in / 2.0)
    ny =  dx / len * (thickness_in / 2.0)
    quad = [
      Geom::Point3d.new(p1.x + nx, p1.y + ny, 0),
      Geom::Point3d.new(p2.x + nx, p2.y + ny, 0),
      Geom::Point3d.new(p2.x - nx, p2.y - ny, 0),
      Geom::Point3d.new(p1.x - nx, p1.y - ny, 0),
    ]
    face = entities.add_face(quad) rescue nil
    next if face.nil?
    face.reverse! if face.normal.z < 0
    face.pushpull(PARAPET_HEIGHT_IN)
  end
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
  model.start_operation('build_from_consensus', true)
  ents = model.active_entities

  thickness_pt = data['wall_thickness_pts']
  walls = data['walls'] || []
  puts "[consume] walls: #{walls.length}"

  wall_mat = model.materials.add('wall_dark')
  wall_mat.color = Sketchup::Color.new(*WALL_FILL_RGB)

  walls.each do |w|
    f = add_wall_volume(ents, w, thickness_pt)
    next if f.nil?
    f.parent.entities.grep(Sketchup::Face).each do |fc|
      fc.material = wall_mat unless fc.material
    end
  end

  rooms = data['rooms'] || []
  puts "[consume] rooms: #{rooms.length}"
  rooms.each_with_index do |r, i|
    add_floor_face(ents, r, ROOM_PALETTE[i % ROOM_PALETTE.length])
  end

  barriers = data['soft_barriers'] || []
  puts "[consume] soft_barriers: #{barriers.length}"
  barriers.each do |b|
    add_parapet(ents, b['polyline_pts'])
  end

  model.commit_operation
  status = model.save(out)
  puts "[consume] saved -> #{out} (status=#{status})"
  Sketchup.exit_code = 0
  Sketchup.send_action('cmd_quit:')  rescue nil
  Sketchup.quit                      rescue nil
end

begin
  main
rescue => e
  puts "[ERR] #{e.class}: #{e.message}"
  e.backtrace.each { |l| puts "  #{l}" }
  Sketchup.exit_code = 1
  Sketchup.quit rescue nil
end
