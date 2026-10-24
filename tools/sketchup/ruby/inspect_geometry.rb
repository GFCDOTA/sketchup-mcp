# inspect_geometry.rb — GEOMETRIA CONSTRUIDA do .skp aberto (FP-055 P4). Nao modifica nada.
#
# Rodado por tools/sketchup/batch.py (SketchUp.exe <copia.skp> -RubyStartup inspect_geometry.rb, env SKMCP_*).
# Para cada grupo/componente de TOPO: as faces HORIZONTAIS de toda a hierarquia, em coordenadas de MUNDO e em metros
# (contorno externo + furos), e a faixa de Z. E o que o validador Python usa para reconstruir, a partir do modelo real
# (nao dos dados enviados ao builder): piso de cada comodo, massa das paredes, folhas de porta e a pegada de cada movel.
# Fecha um grupo aberto antes (SkmcpRuntime.close_edit_context) para as transformacoes sairem em mundo.
require_relative 'skmcp_runtime'

module SkmcpGeometry
  FLAT_TOL_IN = 0.01 # face horizontal: variacao de Z menor que isto (polegadas)

  def self.pts_m(loop, tr)
    loop.vertices.map do |v|
      p = tr * v.position
      [SkmcpRuntime.to_m(p.x), SkmcpRuntime.to_m(p.y), SkmcpRuntime.to_m(p.z)]
    end
  end

  def self.collect(ents, tr, acc)
    ents.each do |e|
      case e
      when Sketchup::Face
        outer = pts_m(e.outer_loop, tr)
        zs = outer.map { |p| p[2] }
        acc[:zmin] = [acc[:zmin], zs.min].compact.min
        acc[:zmax] = [acc[:zmax], zs.max].compact.max
        next if (zs.max - zs.min) > SkmcpRuntime.to_m(FLAT_TOL_IN)
        holes = e.loops.reject(&:outer?).map { |l| pts_m(l, tr).map { |p| p[0..1] } }
        acc[:faces] << { 'z' => zs.first.round(5), 'outer' => outer.map { |p| [p[0].round(5), p[1].round(5)] },
                         'holes' => holes.map { |h| h.map { |p| [p[0].round(5), p[1].round(5)] } } }
      when Sketchup::Group, Sketchup::ComponentInstance
        next if e.hidden?
        collect(e.definition.entities, tr * e.transformation, acc)
      end
    end
  end
end

SkmcpRuntime.run('inspect_geometry') do |_params, model|
  SkmcpRuntime.close_edit_context(model)
  groups = []
  model.entities.each do |e|
    next unless e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
    acc = { faces: [], zmin: nil, zmax: nil }
    SkmcpGeometry.collect(e.definition.entities, e.transformation, acc)
    name = e.name.to_s.empty? ? e.definition.name : e.name
    groups << { 'name' => name, 'hidden' => e.hidden?, 'zmin_m' => acc[:zmin], 'zmax_m' => acc[:zmax],
                'horizontal_faces' => acc[:faces] }
  end
  units = (model.options['UnitsOptions']['LengthUnit'] rescue nil)
  { 'title' => model.title, 'path' => model.path, 'length_unit_code' => units, 'unit' => 'm',
    'frame' => 'sketchup_world', 'groups' => groups }
end
