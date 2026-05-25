# Diagnostic-only dump: walk the active model and write a JSON
# listing every top-level Group with bbox + face/edge counts + a
# normalised material name.
#
# Loaded by autorun_consume.rb when autorun_control.txt's line 3
# points at this file. Reads ENV['SKP_OUT'] as the destination JSON
# path (overloading the var name — semantically it's our output).
#
# Does NOT modify the model: no model.entities.clear!, no
# pushpull, no save. Safe to run against any .skp / .skb / .skp-temp
# without writing back to it.

require 'json'

M_TO_IN = 39.3700787402

def walk(ents, faces, edges, subs)
  ents.each do |e|
    case e
    when Sketchup::Face then faces << e
    when Sketchup::Edge then edges << e
    when Sketchup::Group
      subs << e
      walk(e.entities, faces, edges, subs)
    end
  end
end

def primary_material_name(faces)
  counts = Hash.new(0)
  faces.each do |f|
    m = f.material
    counts[m.name] += 1 if m
  end
  return nil if counts.empty?
  counts.max_by { |_, n| n }.first
end

def dump_group(g)
  faces = []
  edges = []
  subs  = []
  walk(g.entities, faces, edges, subs)
  bb = g.bounds
  m_per_in = 1.0 / M_TO_IN
  {
    'name'              => g.name,
    'face_count'        => faces.length,
    'edge_count'        => edges.length,
    'sub_group_count'   => subs.length,
    'bbox_m' => {
      'min' => [
        (bb.min.x * m_per_in).round(4),
        (bb.min.y * m_per_in).round(4),
        (bb.min.z * m_per_in).round(4),
      ],
      'max' => [
        (bb.max.x * m_per_in).round(4),
        (bb.max.y * m_per_in).round(4),
        (bb.max.z * m_per_in).round(4),
      ],
    },
    'height_m' => ((bb.max.z - bb.min.z) * m_per_in).round(4),
    'primary_material' => primary_material_name(faces),
  }
end

out_json = ENV['SKP_OUT'] or raise 'SKP_OUT env not set (used as dump JSON path)'
puts "[dump] writing #{out_json}"

begin
  model = Sketchup.active_model
  groups = model.active_entities.grep(Sketchup::Group)
  records = groups.map { |g| dump_group(g) }
  payload = {
    'schema_version' => '1.0.0',
    'tool'           => 'dump_skp_groups',
    'skp_path'       => model.path,
    'total_top_level_groups' => groups.length,
    'groups'         => records,
  }
  File.write(out_json, JSON.pretty_generate(payload))
  puts "[dump] wrote #{records.length} groups"
rescue StandardError => e
  File.write(out_json + '.error.txt',
             "#{e.class}: #{e.message}\n#{e.backtrace.first(20).join("\n")}")
  raise
end
