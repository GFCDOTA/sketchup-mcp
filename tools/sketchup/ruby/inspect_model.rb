# inspect_model.rb — inventário estruturado do .skp ABERTO. Não modifica nada.
#
# Rodado por tools/sketchup/batch.py:
#   SketchUp.exe <modelo.skp> -RubyStartup inspect_model.rb   (env SKMCP_*)
# Params: max_depth (default 2), protected_prefixes, protected_substrings.
# Fecha um grupo aberto antes (SkmcpRuntime.close_edit_context): dentro dele as
# transformações vêm em mundo e o bbox de mundo sairia errado. Roda numa cópia.
# Medidas em metros. bbox_local_m = referencial do pai; bbox_world_m = mundo.
require_relative 'skmcp_runtime'

SkmcpRuntime.run('inspect_model') do |params, model|
  depth = (params['max_depth'] || 2).to_i.clamp(1, 6)
  prefixes = params['protected_prefixes'] || []
  substrings = params['protected_substrings'] || []
  SkmcpRuntime.close_edit_context(model)
  ents = model.entities

  pairs = SkmcpRuntime.walk(ents, depth: depth)
  by_pid = pairs.to_h { |e, info| [info['pid'], e] }
  nodes = SkmcpCore.dedupe(pairs.map(&:last)).map do |info|
    e = by_pid[info['pid']]
    own = SkmcpCore.protected_name?(info['name'], prefixes, substrings) ||
          SkmcpCore.protected_name?(info['definition'], prefixes, substrings)
    inherited = info['ancestors'].any? do |a|
      SkmcpCore.protected_name?(a['name'], prefixes, substrings) ||
        SkmcpCore.protected_name?(a['definition'], prefixes, substrings)
    end
    w = SkmcpCore.normalize(info['world'])
    {
      'name' => info['name'], 'definition' => info['definition'], 'pid' => info['pid'],
      'path' => info['path'], 'paths' => info['paths'], 'type' => info['type'],
      # contexts > 1: a entidade vive numa definição usada em vários lugares
      'contexts' => info['contexts'],
      'tag' => (e.layer.name rescue nil),
      'locked' => info['locked'],
      'hidden' => e.hidden?,
      'material' => (e.material ? e.material.name : nil),
      # bbox_local_m: no referencial do PAI (o que Entity#bounds devolve);
      # bbox_world_m: no mundo. Iguais só para entidades na raiz.
      'bbox_local_m' => SkmcpRuntime.bbox_m(e.bounds),
      'bbox_world_m' => SkmcpRuntime.bbox_world_m(e, info['world']),
      'world_origin_m' => [w[12], w[13], w[14]].map { |v| SkmcpRuntime.to_m(v) },
      'world_transform' => w.map { |v| v.round(6) },
      'protected' => own || inherited,
      'protected_by' => own ? 'self' : (inherited ? 'ancestor' : nil),
      'children' => e.definition.entities.count { |c| c.is_a?(Sketchup::Group) || c.is_a?(Sketchup::ComponentInstance) },
    }
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
