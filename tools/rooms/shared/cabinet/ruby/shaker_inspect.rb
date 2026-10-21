# shaker_inspect.rb — inspeção GEOMÉTRICA dos gabinetes e das portas Shaker de um .skp ABERTO (reaberto do disco). Não modifica nada.
#
# Irmão do cabinet_inspect.rb (que continua intocado): além das peças diretas de cada gabinete, devolve cada subgrupo
# "Shaker_<request_id>" com os 8 vértices de MUNDO de cada peça (definição × subgrupo × raiz), manifold/faces/arestas, material,
# tag, atributos skmcp_shaker e o "fingerprint" do que NÃO é gabinete (prova de que o resto do modelo ficou como estava).
# Medidas em metros (6 casas).
require 'json'
require 'digest'
require_relative '../../../../sketchup/ruby/skmcp_runtime'

DICT = 'skmcp_shaker'
PARENT_DICT = 'skmcp_cabinet'

def m6(v)
  (v.to_f * 0.0254).round(6)
end

def world_pts(inst, parent_tr)
  tr = parent_tr * inst.transformation
  bb = inst.definition.bounds
  (0..7).map { |i| tr * bb.corner(i) }.map { |p| [m6(p.x), m6(p.y), m6(p.z)] }
end

def geometry_summary(defn)
  faces = defn.entities.grep(Sketchup::Face)
  edges = defn.entities.grep(Sketchup::Edge)
  { 'faces' => faces.size, 'edges' => edges.size, 'vertices' => faces.flat_map(&:vertices).uniq.size,
    'area_m2' => (faces.sum(&:area) * 0.0254 * 0.0254).round(6) }
end

def part_report(inst, dict, tr)
  {
    'name' => inst.name, 'part_id' => inst.get_attribute(dict, 'part_id'), 'role' => inst.get_attribute(dict, 'role'),
    'definition' => inst.definition.name, 'definition_instances' => inst.definition.count_used_instances,
    'manifold' => inst.manifold?, 'tag' => inst.layer.name, 'material' => (inst.material ? inst.material.name : nil),
    'attr_material' => inst.get_attribute(dict, 'material'), 'attr_grain' => inst.get_attribute(dict, 'grain'),
    'attr_signature' => inst.get_attribute(dict, 'signature'), 'geometry' => geometry_summary(inst.definition),
    'world_corners_m' => world_pts(inst, tr), 'pid' => inst.persistent_id
  }
end

def node_fingerprint(e, tr)
  bb = e.respond_to?(:definition) ? e.definition.bounds : e.bounds
  t = (tr * e.transformation).to_a.map { |v| v.round(5) }
  Digest::SHA256.hexdigest([e.name, (e.respond_to?(:definition) ? e.definition.name : ''), t,
                            bb.min.to_a.map { |v| v.round(4) }, bb.max.to_a.map { |v| v.round(4) }].inspect)[0, 16]
end

SkmcpRuntime.run('shaker_inspect') do |_params, model|
  SkmcpRuntime.close_edit_context(model)
  ents = model.entities
  roots = ents.grep(Sketchup::Group).select { |g| g.get_attribute(PARENT_DICT, 'root') == true }
  cabinets = roots.map do |root|
    rtr = root.transformation
    shakers = root.entities.grep(Sketchup::Group).select { |g| g.get_attribute(DICT, 'root') == true }.map do |sub|
      str = rtr * sub.transformation
      {
        'name' => sub.name, 'request_id' => sub.get_attribute(DICT, 'request_id'),
        'parent_request_id' => sub.get_attribute(DICT, 'parent_request_id'),
        'capability' => sub.get_attribute(DICT, 'capability'), 'capability_version' => sub.get_attribute(DICT, 'capability_version'),
        'signature' => sub.get_attribute(DICT, 'signature'), 'parent_plan_signature' => sub.get_attribute(DICT, 'parent_plan_signature'),
        'replaces_part' => sub.get_attribute(DICT, 'replaces_part'), 'source_verified' => sub.get_attribute(DICT, 'source_verified'),
        'tag' => sub.layer.name, 'pid' => sub.persistent_id,
        'loose_faces' => sub.entities.grep(Sketchup::Face).size, 'loose_edges' => sub.entities.grep(Sketchup::Edge).size,
        'transform' => sub.transformation.to_a.map { |v| v.round(6) },
        'parts' => sub.entities.grep(Sketchup::ComponentInstance).map { |i| part_report(i, DICT, str) }
      }
    end
    {
      'name' => root.name, 'request_id' => root.get_attribute(PARENT_DICT, 'request_id'),
      'signature' => root.get_attribute(PARENT_DICT, 'signature'), 'tag' => root.layer.name, 'pid' => root.persistent_id,
      'world_transform' => rtr.to_a.map { |v| v.round(6) },
      'loose_faces' => root.entities.grep(Sketchup::Face).size, 'loose_edges' => root.entities.grep(Sketchup::Edge).size,
      'parts' => root.entities.grep(Sketchup::ComponentInstance).map { |i| part_report(i, PARENT_DICT, rtr) },
      'shakers' => shakers
    }
  end
  others = ents.reject { |e| e.is_a?(Sketchup::Group) && e.get_attribute(PARENT_DICT, 'root') == true }
  identity = Geom::Transformation.new
  fp = others.map { |e| node_fingerprint(e, identity) rescue e.class.to_s }.sort
  {
    'path' => model.path,
    'cabinets' => cabinets,
    'non_cabinet' => { 'count' => others.size, 'fingerprint' => Digest::SHA256.hexdigest(fp.join(',')), 'items' => fp.size },
    'counts' => {
      'top_groups' => ents.grep(Sketchup::Group).size, 'top_components' => ents.grep(Sketchup::ComponentInstance).size,
      'loose_faces_at_root' => ents.grep(Sketchup::Face).size, 'loose_edges_at_root' => ents.grep(Sketchup::Edge).size,
      'definitions' => model.definitions.size,
      'shaker_definitions' => model.definitions.count { |d| d.name.start_with?('ShakerDef_') },
      'cabinet_definitions' => model.definitions.count { |d| d.name.start_with?('CabinetDef_') },
      'materials' => model.materials.size, 'tags' => model.layers.map(&:name)
    },
    'definitions' => model.definitions.select { |d| d.name.start_with?('ShakerDef_') || d.name.start_with?('CabinetDef_') }
                          .map { |d| [d.name, d.count_used_instances] }.to_h
  }
end
