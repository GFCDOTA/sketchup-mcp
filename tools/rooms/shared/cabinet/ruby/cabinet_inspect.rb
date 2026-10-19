# cabinet_inspect.rb — inspeção GEOMÉTRICA dos gabinetes de um .skp ABERTO (reaberto do disco). Não modifica nada.
#
# Diferente do inspect_model (bbox), devolve os 8 vértices de MUNDO de cada peça (definição × cadeia de transformações),
# manifold/faces/arestas, material, tag, atributos skmcp_cabinet e o "fingerprint" do que NÃO é gabinete — a prova de que
# a arquitetura/outros objetos ficaram como estavam. Medidas em metros (6 casas).
# Params: (nenhum obrigatório)
require 'json'
require 'digest'
require_relative '../../../../sketchup/ruby/skmcp_runtime'

DICT = 'skmcp_cabinet'

def m6(v)
  (v.to_f * 0.0254).round(6)
end

def world_pts(inst, parent_tr)
  tr = parent_tr * inst.transformation
  bb = inst.definition.bounds
  corners = (0..7).map { |i| bb.corner(i) }
  corners.map { |c| p = tr * c; [m6(p.x), m6(p.y), m6(p.z)] }
end

def geometry_summary(defn)
  faces = defn.entities.grep(Sketchup::Face)
  edges = defn.entities.grep(Sketchup::Edge)
  verts = defn.entities.grep(Sketchup::Face).flat_map { |f| f.vertices }.uniq
  { 'faces' => faces.size, 'edges' => edges.size, 'vertices' => verts.size,
    'area_m2' => (faces.sum(&:area) * 0.0254 * 0.0254).round(6) }
end

def node_fingerprint(e, tr)
  bb = e.respond_to?(:definition) ? e.definition.bounds : e.bounds
  t = (tr * e.transformation).to_a.map { |v| v.round(5) }
  Digest::SHA256.hexdigest([e.name, (e.respond_to?(:definition) ? e.definition.name : ''), t, bb.min.to_a.map { |v| v.round(4) }, bb.max.to_a.map { |v| v.round(4) }].inspect)[0, 16]
end

SkmcpRuntime.run('cabinet_inspect') do |_params, model|
  SkmcpRuntime.close_edit_context(model)
  ents = model.entities
  roots = ents.grep(Sketchup::Group).select { |g| g.get_attribute(DICT, 'root') == true }
  cabinets = roots.map do |root|
    rtr = root.transformation
    parts = root.entities.grep(Sketchup::ComponentInstance).map do |i|
      {
        'name' => i.name, 'part_id' => i.get_attribute(DICT, 'part_id'), 'role' => i.get_attribute(DICT, 'role'),
        'definition' => i.definition.name, 'definition_instances' => i.definition.count_used_instances,
        'manifold' => i.manifold?, 'tag' => i.layer.name, 'material' => (i.material ? i.material.name : nil),
        'attr_material' => i.get_attribute(DICT, 'material'), 'attr_grain' => i.get_attribute(DICT, 'grain'),
        'attr_signature' => i.get_attribute(DICT, 'signature'),
        'geometry' => geometry_summary(i.definition), 'world_corners_m' => world_pts(i, rtr),
        'pid' => i.persistent_id
      }
    end
    { 'name' => root.name, 'request_id' => root.get_attribute(DICT, 'request_id'),
      'capability' => root.get_attribute(DICT, 'capability'), 'capability_version' => root.get_attribute(DICT, 'capability_version'),
      'signature' => root.get_attribute(DICT, 'signature'), 'tag' => root.layer.name, 'pid' => root.persistent_id,
      'world_transform' => rtr.to_a.map { |v| v.round(6) },
      'loose_faces' => root.entities.grep(Sketchup::Face).size, 'loose_edges' => root.entities.grep(Sketchup::Edge).size,
      'parts' => parts }
  end
  others = ents.reject { |e| e.is_a?(Sketchup::Group) && e.get_attribute(DICT, 'root') == true }
  identity = Geom::Transformation.new
  fp = others.map { |e| node_fingerprint(e, identity) rescue "#{e.class}" }.sort
  {
    'path' => model.path,
    'cabinets' => cabinets,
    'non_cabinet' => { 'count' => others.size, 'fingerprint' => Digest::SHA256.hexdigest(fp.join(',')), 'items' => fp.size },
    'counts' => {
      'top_groups' => ents.grep(Sketchup::Group).size, 'top_components' => ents.grep(Sketchup::ComponentInstance).size,
      'loose_faces_at_root' => ents.grep(Sketchup::Face).size, 'loose_edges_at_root' => ents.grep(Sketchup::Edge).size,
      'definitions' => model.definitions.size,
      'cabinet_definitions' => model.definitions.count { |d| d.name.start_with?('CabinetDef_') },
      'materials' => model.materials.size, 'tags' => model.layers.map(&:name)
    },
    'definitions' => model.definitions.select { |d| d.name.start_with?('CabinetDef_') }.map { |d| [d.name, d.count_used_instances] }.to_h
  }
end
