# inspect_model.rb — inventário estruturado do .skp ABERTO. Não modifica nada.
#
# Rodado por tools/sketchup/batch.py:
#   SketchUp.exe <modelo.skp> -RubyStartup inspect_model.rb   (env SKMCP_*)
# Params: max_depth (default 2), protected_prefixes.
require_relative 'skmcp_runtime'

SkmcpRuntime.run('inspect_model') do |params, model|
  depth = (params['max_depth'] || 2).to_i.clamp(1, 6)
  prefixes = params['protected_prefixes'] || []
  ents = model.entities

  nodes = SkmcpRuntime.walk(ents, depth: depth).map do |e, info|
    info.merge(
      'tag' => (e.layer.name rescue nil),
      'locked' => (e.locked? rescue false),
      'hidden' => e.hidden?,
      'material' => (e.material ? e.material.name : nil),
      'bbox_m' => SkmcpRuntime.bbox_m(e.bounds),
      'protected' => SkmcpCore.protected_name?(info['name'], prefixes),
      'children' => e.definition.entities.count { |c| c.is_a?(Sketchup::Group) || c.is_a?(Sketchup::ComponentInstance) },
    )
  end

  materials = model.materials.map do |m|
    c = m.color
    { 'name' => m.name, 'display_name' => (m.display_name rescue m.name),
      'rgb' => [c.red, c.green, c.blue], 'alpha' => (m.alpha rescue 1.0).round(3),
      'texture' => (m.texture ? File.basename(m.texture.filename.to_s) : nil) }
  end

  units = (model.options['UnitsOptions']['LengthUnit'] rescue nil)
  {
    'title' => model.title,
    'path' => model.path,
    'length_unit_code' => units,
    'bbox_m' => SkmcpRuntime.bbox_m(model.bounds),
    'counts' => {
      'top_groups' => ents.grep(Sketchup::Group).size,
      'top_components' => ents.grep(Sketchup::ComponentInstance).size,
      'loose_faces_at_root' => ents.grep(Sketchup::Face).size,
      'loose_edges_at_root' => ents.grep(Sketchup::Edge).size,
      'definitions' => model.definitions.size,
      'materials' => model.materials.size,
      'tags' => model.layers.size,
      'scenes' => model.pages.size,
    },
    'nodes' => nodes,
    'materials' => materials,
    'tags' => model.layers.map { |l| { 'name' => l.name, 'visible' => l.visible? } },
    'scenes' => model.pages.map(&:name),
  }
end
