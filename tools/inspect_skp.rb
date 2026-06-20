# inspect_skp.rb — analisador de referencia de movel (furniture-reference-analyzer).
# Abre o .skp passado POSITIONAL e escreve um relatorio JSON (INSPECT_OUT) com:
# unidade do modelo, bounding box (in + m), materiais, definicoes de componentes,
# contagem de entidades e a hierarquia (grupos/componentes ate 2 niveis). Renderiza
# top/front/iso (RENDER_TOP/FRONT/ISO). Escreve INSPECT_LOG por ultimo (sinal de done
# pro Python). NAO modifica o modelo. Reuso:
#   SketchUp.exe <ref.skp> -RubyStartup inspect_skp.rb   (env INSPECT_OUT/LOG/RENDER_*)
require 'json'

M_PER_IN = 0.0254

def size_m(bb)
  [((bb.max.x - bb.min.x) * M_PER_IN).round(3),
   ((bb.max.y - bb.min.y) * M_PER_IN).round(3),
   ((bb.max.z - bb.min.z) * M_PER_IN).round(3)]
end

def center_m(bb)
  [(bb.center.x * M_PER_IN).round(3), (bb.center.y * M_PER_IN).round(3),
   (bb.center.z * M_PER_IN).round(3)]
end

def short(klass)
  klass.name.split('::').last
end

def count_all(ents, acc)
  ents.each do |e|
    k = short(e.class)
    acc[k] = (acc[k] || 0) + 1
    if e.is_a?(Sketchup::Group)
      count_all(e.entities, acc)
    elsif e.is_a?(Sketchup::ComponentInstance)
      count_all(e.definition.entities, acc)
    end
  end
  acc
end

def walk(ents, depth, max_depth)
  nodes = []
  ents.each do |e|
    next unless e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
    if e.is_a?(Sketchup::Group)
      sub = e.entities
      name = e.name.to_s.empty? ? '(group)' : e.name
    else
      sub = e.definition.entities
      name = e.definition.name
    end
    node = { 'type' => short(e.class), 'name' => name, 'size_m' => size_m(e.bounds),
             'center_m' => center_m(e.bounds) }
    n_sub = sub.grep(Sketchup::Group).size + sub.grep(Sketchup::ComponentInstance).size
    if depth < max_depth && n_sub > 0
      node['children'] = walk(sub, depth + 1, max_depth)
    else
      node['n_subgroups'] = n_sub
    end
    nodes << node
  end
  nodes
end

def set_cam(model, eye, target, up)
  view = model.active_view
  cam = Sketchup::Camera.new(eye, target, up)
  cam.perspective = false
  view.camera = cam
  view.zoom_extents
end

def render(model, path)
  model.active_view.write_image(filename: path, width: 1200, height: 1200,
                                antialias: true, transparent: false)
end

model = Sketchup.active_model
bb = model.bounds
c = bb.center
d = bb.diagonal
uo = model.options['UnitsOptions']

rep = {}
rep['title'] = model.title
rep['path'] = model.path.to_s
rep['length_unit_code'] = uo ? uo['LengthUnit'] : nil   # 0=in 1=ft 2=mm 3=cm 4=m
rep['bbox'] = {
  'min_in'  => [bb.min.x.to_f.round(2), bb.min.y.to_f.round(2), bb.min.z.to_f.round(2)],
  'size_in' => [(bb.max.x - bb.min.x).to_f.round(2), (bb.max.y - bb.min.y).to_f.round(2),
                (bb.max.z - bb.min.z).to_f.round(2)],
  'size_m'  => size_m(bb)
}
rep['materials'] = model.materials.map { |m|
  { 'name' => m.name,
    'color' => (m.color ? [m.color.red, m.color.green, m.color.blue] : nil),
    'alpha' => m.alpha.round(2),
    'texture' => (m.texture ? File.basename(m.texture.filename.to_s) : nil) }
}
rep['definitions'] = model.definitions.reject { |dn| dn.image? }.map { |dn|
  { 'name' => dn.name, 'instances' => dn.count_instances, 'size_m' => size_m(dn.bounds) }
}
rep['entity_counts'] = count_all(model.entities, {})
rep['hierarchy'] = walk(model.entities, 0, 2)
File.write(ENV['INSPECT_OUT'], JSON.pretty_generate(rep)) if ENV['INSPECT_OUT']

if ENV['RENDER_TOP']
  set_cam(model, Geom::Point3d.new(c.x, c.y, c.z + d * 3), c, Geom::Vector3d.new(0, 1, 0))
  render(model, ENV['RENDER_TOP'])
end
if ENV['RENDER_FRONT']
  set_cam(model, Geom::Point3d.new(c.x, c.y - d * 3, c.z), c, Geom::Vector3d.new(0, 0, 1))
  render(model, ENV['RENDER_FRONT'])
end
if ENV['RENDER_ISO']
  set_cam(model, Geom::Point3d.new(c.x + d * 1.5, c.y - d * 1.6, c.z + d * 1.4), c,
          Geom::Vector3d.new(0, 0, 1))
  render(model, ENV['RENDER_ISO'])
end

File.write(ENV['INSPECT_LOG'] || 'inspect_log.txt',
           "inspected '#{model.title}' | bbox_m #{rep['bbox']['size_m'].inspect} | " \
           "mats #{rep['materials'].size} | defs #{rep['definitions'].size} | " \
           "top_nodes #{rep['hierarchy'].size}\n")
