# geometry_probe.rb — sonda L2 (scratch, NÃO versionada) sobre o .skp ABERTO.
# Não salva nada. Usa o contrato SKMCP_* de tools/sketchup/batch.py.
#
# Params:
#   rays: [{id, origin_m:[x,y,z], dir:[dx,dy,dz], only:"PlanShell_Group"}]
#         → primeiro hit considerando SÓ os grupos top-level cujo nome casa `only`
#           (os demais são escondidos durante o raytest e restaurados depois).
#   topology: true → faces degeneradas / arestas zero / arestas soltas / não-manifold
#             por grupo top-level (recursivo em definições).
require File.join(ENV.fetch('SKMCP_RUBY_DIR'), 'skmcp_runtime')

def probe_topology(ents, acc, seen)
  ents.each do |e|
    case e
    when Sketchup::Face
      acc['faces'] += 1
      acc['degenerate_faces'] += 1 if e.area < 1e-4
    when Sketchup::Edge
      acc['edges'] += 1
      acc['zero_edges'] += 1 if e.length < 1e-3
      n = e.faces.size
      acc['loose_edges'] += 1 if n.zero?
      acc['edges_gt2_faces'] += 1 if n > 2
    when Sketchup::Group, Sketchup::ComponentInstance
      d = e.definition
      next if seen[d.entityID] # definição compartilhada: conta 1x

      seen[d.entityID] = true
      probe_topology(d.entities, acc, seen)
    end
  end
end

SkmcpRuntime.run('geometry_probe') do |params, model|
  SkmcpRuntime.close_edit_context(model)
  ents = model.entities
  tops = ents.select { |e| e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance) }
  label = ->(e) { e.name.to_s.empty? ? e.definition.name.to_s : e.name.to_s }

  topo = {}
  if params['topology']
    tops.each do |g|
      acc = { 'faces' => 0, 'edges' => 0, 'degenerate_faces' => 0, 'zero_edges' => 0,
              'loose_edges' => 0, 'edges_gt2_faces' => 0 }
      probe_topology(g.definition.entities, acc, {})
      (topo[label.call(g)] ||= []) << acc
    end
  end

  rays = (params['rays'] || []).map do |r|
    hidden_before = tops.to_h { |g| [g, g.hidden?] }
    only = r.key?('only') ? r['only'] : 'PlanShell_Group'
    tops.each { |g| g.hidden = !label.call(g).include?(only) } if only
    o = Geom::Point3d.new(*r['origin_m'].map { |v| v.to_f.m })
    d = Geom::Vector3d.new(*r['dir'].map(&:to_f))
    hit = model.raytest([o, d], true) # true = ignora geometria escondida
    hidden_before.each { |g, h| g.hidden = h }
    if hit
      path = hit[1].map { |x| x.respond_to?(:name) ? (x.name.to_s.empty? && x.respond_to?(:definition) ? x.definition.name : x.name) : x.class.name.split('::').last }
      { 'id' => r['id'], 'hit' => true, 'distance_m' => SkmcpRuntime.to_m(o.distance(hit[0])),
        'point_m' => [hit[0].x, hit[0].y, hit[0].z].map { |v| SkmcpRuntime.to_m(v) }, 'path' => path }
    else
      { 'id' => r['id'], 'hit' => false }
    end
  end
  # o raytest escondeu/mostrou grupos: desfaz qualquer marca de modificação
  { 'topology' => topo, 'rays' => rays, 'model_path' => model.path,
    'top_level' => tops.map { |g| label.call(g) } }
end
