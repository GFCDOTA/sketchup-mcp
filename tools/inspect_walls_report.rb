# Inspect the active SketchUp model and emit a JSON diagnostic of every
# entity at the active_entities root level. Goal: identify what produces
# white / default-material surfaces in the apartment model.
#
# Inputs (env, set by autorun_inspector.rb):
#   ENV['INSPECT_REPORT'] -> path to write JSON report
# Optional:
#   ENV['INSPECT_QUIT']='1' -> call Sketchup.quit after writing

require 'json'

PROGRESS_LOG = 'C:/Users/felip_local/AppData/Roaming/SketchUp/SketchUp 2026/SketchUp/Plugins/inspect_progress.txt'
File.delete(PROGRESS_LOG) rescue nil

def plg(m)
  File.open(PROGRESS_LOG, 'a') { |f| f.puts("[#{Time.now.strftime('%H:%M:%S.%L')}] #{m}") } rescue nil
end

def safe_color_arr(c)
  return nil if c.nil?
  [c.red, c.green, c.blue, c.alpha]
rescue
  nil
end

def material_summary(mat)
  return { 'name' => nil, 'color' => nil, 'alpha' => nil, 'is_default' => true } if mat.nil?
  name  = mat.name rescue nil
  col   = (mat.color rescue nil)
  alpha = mat.alpha rescue nil
  { 'name' => name, 'color' => safe_color_arr(col), 'alpha' => alpha, 'is_default' => false }
end

def face_record(face, parent_chain)
  bb       = face.bounds
  area_in2 = face.area rescue nil
  mfront   = face.material rescue nil
  mback    = face.back_material rescue nil
  norm     = nil
  begin
    n = face.normal
    norm = [n.x.round(4), n.y.round(4), n.z.round(4)]
  rescue
    norm = nil
  end
  pid = face.persistent_id rescue nil
  layer_name = face.layer.name rescue nil
  edge_count = face.edges.length rescue nil
  {
    'entity_id'      => face.entityID,
    'persistent_id'  => pid,
    'kind'           => 'Face',
    'parent_chain'   => parent_chain,
    'layer'          => layer_name,
    'material_front' => material_summary(mfront),
    'material_back'  => material_summary(mback),
    'normal'         => norm,
    'area_in2'       => (area_in2.nil? ? nil : area_in2.round(2)),
    'bbox'           => [bb.min.x.to_f.round(2), bb.min.y.to_f.round(2), bb.min.z.to_f.round(2),
                          bb.max.x.to_f.round(2), bb.max.y.to_f.round(2), bb.max.z.to_f.round(2)],
    'edge_count'     => edge_count,
  }
end

def walk(entities, parent_chain, faces_out, edges_out, groups_out, depth: 0, max_depth: 4)
  return if depth > max_depth
  i = 0
  entities.each do |e|
    i += 1
    case e
    when Sketchup::Group
      bb = e.bounds
      gpid   = e.persistent_id rescue nil
      gname  = e.name rescue nil
      glayer = e.layer.name rescue nil
      gmat   = e.material rescue nil
      groups_out << {
        'entity_id'     => e.entityID,
        'persistent_id' => gpid,
        'kind'          => 'Group',
        'name'          => gname,
        'layer'         => glayer,
        'material'      => material_summary(gmat),
        'depth'         => depth,
        'parent_chain'  => parent_chain,
        'bbox'          => [bb.min.x.to_f.round(2), bb.min.y.to_f.round(2), bb.min.z.to_f.round(2),
                             bb.max.x.to_f.round(2), bb.max.y.to_f.round(2), bb.max.z.to_f.round(2)],
        'face_count'    => e.entities.grep(Sketchup::Face).length,
        'edge_count'    => e.entities.grep(Sketchup::Edge).length,
      }
      walk(e.entities, parent_chain + [gname.to_s], faces_out, edges_out, groups_out,
           depth: depth + 1, max_depth: max_depth)
    when Sketchup::ComponentInstance
      bb = e.bounds
      cname = e.name rescue nil
      cdef  = e.definition.name rescue nil
      clayer = e.layer.name rescue nil
      cmat = e.material rescue nil
      groups_out << {
        'entity_id'      => e.entityID,
        'kind'           => 'ComponentInstance',
        'name'           => cname,
        'definition'     => cdef,
        'layer'          => clayer,
        'material'       => material_summary(cmat),
        'depth'          => depth,
        'parent_chain'   => parent_chain,
        'bbox'           => [bb.min.x.to_f.round(2), bb.min.y.to_f.round(2), bb.min.z.to_f.round(2),
                              bb.max.x.to_f.round(2), bb.max.y.to_f.round(2), bb.max.z.to_f.round(2)],
      }
      walk(e.definition.entities, parent_chain + [(cname.to_s.empty? ? cdef : cname)],
           faces_out, edges_out, groups_out, depth: depth + 1, max_depth: max_depth)
    when Sketchup::Face
      faces_out << face_record(e, parent_chain)
    when Sketchup::Edge
      next  # skip edges to keep payload small
    end
  end
end

def classify_face(f)
  m = f['material_front']
  is_default = m.nil? || m['is_default']
  name = (m && m['name']) || ''
  parent = f['parent_chain'].is_a?(Array) ? f['parent_chain'].join('/') : ''
  z_min = f['bbox'][2]
  z_max = f['bbox'][5]
  normal = f['normal'] || [0, 0, 0]
  is_horizontal = normal[2].to_f.abs > 0.9
  parapet_top_in = (1.10 * 39.3700787402)

  if is_default
    if parent =~ /\Aw\d+/
      'wall_face_default(in_wall_group)'
    elsif is_horizontal && z_min.between?(parapet_top_in - 5, parapet_top_in + 5)
      'parapet_top_default'
    elsif !is_horizontal && z_min.abs < 1 && z_max.between?(parapet_top_in - 5, parapet_top_in + 5)
      'parapet_side_default'
    elsif is_horizontal && z_min.abs < 1
      'floor_face_no_material'
    else
      'unclassified_default'
    end
  elsif name =~ /\Aroom_/
    'room_floor'
  elsif name == 'wall_dark'
    'wall_face_dark'
  else
    "named_material(#{name})"
  end
end

def detect_overlaps(groups)
  walls = groups.select { |g| g['name'].to_s =~ /\Aw\d+\z/ }
  pairs = []
  walls.combination(2).each do |a, b|
    ax0, ay0, az0, ax1, ay1, az1 = a['bbox']
    bx0, by0, bz0, bx1, by1, bz1 = b['bbox']
    overlap_x = [0, [ax1, bx1].min - [ax0, bx0].max].max
    overlap_y = [0, [ay1, by1].min - [ay0, by0].max].max
    overlap_z = [0, [az1, bz1].min - [az0, bz0].max].max
    vol = overlap_x * overlap_y * overlap_z
    next if vol < 1.0
    pairs << {
      'a' => a['name'], 'b' => b['name'],
      'overlap_in3' => vol.round(2),
      'overlap_box_in' => [overlap_x.round(2), overlap_y.round(2), overlap_z.round(2)],
    }
  end
  pairs.sort_by { |p| -p['overlap_in3'] }.first(20)
end

def main
  report_path = ENV['INSPECT_REPORT'] || 'E:/Claude/sketchup-mcp/runs/vector/inspect_report.json'
  plg("main start; report=#{report_path}")
  model = Sketchup.active_model
  plg("model=#{model.inspect} path=#{(model.path rescue 'n/a')}")
  ents = model.active_entities
  plg("active_entities count=#{ents.length}")

  faces, edges, groups = [], [], []
  walk(ents, [], faces, edges, groups, depth: 0, max_depth: 4)
  plg("walk done: groups=#{groups.length} faces=#{faces.length}")

  faces.each { |f| f['classification'] = classify_face(f) }

  face_class_counts = Hash.new(0)
  faces.each { |f| face_class_counts[f['classification']] += 1 }

  materials_summary = []
  model.materials.each do |m|
    materials_summary << {
      'name'  => m.name,
      'color' => safe_color_arr(m.color),
      'alpha' => m.alpha,
    }
  end
  plg("materials count=#{materials_summary.length}")

  layers_summary = []
  model.layers.each do |l|
    layers_summary << { 'name' => l.name, 'visible' => (l.visible? rescue nil) }
  end
  plg("layers count=#{layers_summary.length}")

  overlaps = detect_overlaps(groups)
  plg("overlaps count=#{overlaps.length}")

  default_class_keys = [
    'wall_face_default(in_wall_group)',
    'parapet_top_default',
    'parapet_side_default',
    'floor_face_no_material',
    'unclassified_default',
  ]
  default_faces = faces.select { |f| default_class_keys.include?(f['classification']) }

  report = {
    'meta' => {
      'inspected_at' => Time.now.iso8601,
      'skp_path'     => (model.path rescue nil),
      'sketchup_version' => Sketchup.version,
    },
    'totals' => {
      'groups'    => groups.length,
      'faces'     => faces.length,
      'materials' => materials_summary.length,
      'layers'    => layers_summary.length,
    },
    'face_classification_counts' => face_class_counts,
    'materials' => materials_summary,
    'layers' => layers_summary,
    'wall_overlaps_top20' => overlaps,
    'default_faces_count' => default_faces.length,
    'default_faces_sample' => default_faces.first(50),
    'groups' => groups,
  }

  File.write(report_path, JSON.pretty_generate(report))
  plg("wrote #{report_path}")
  if ENV['INSPECT_QUIT'] == '1'
    Sketchup.quit rescue nil
  end
end

begin
  main
rescue => e
  plg("EXCEPTION: #{e.class}: #{e.message}")
  e.backtrace.first(20).each { |l| plg("  #{l}") }
  begin
    File.write(ENV['INSPECT_REPORT'] || 'E:/Claude/sketchup-mcp/runs/vector/inspect_report.json',
               JSON.pretty_generate({ 'error' => "#{e.class}: #{e.message}",
                                      'backtrace' => e.backtrace.first(20) }))
  rescue
  end
end
