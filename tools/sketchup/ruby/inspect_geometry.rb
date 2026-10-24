# inspect_geometry.rb — GEOMETRIA CONSTRUIDA do .skp aberto (FP-055 P4). Nao modifica nada.
#
# Rodado por tools/sketchup/batch.py (SketchUp.exe <copia.skp> -RubyStartup inspect_geometry.rb, env SKMCP_*).
# Para cada grupo/componente de TOPO, percorrendo TODA a hierarquia (grupos e componentes aninhados, com a transformacao
# composta), exporta em coordenadas de MUNDO e em metros:
#   - `projected_faces`: toda face NAO vertical (horizontal ou inclinada) projetada no plano XY — contorno externo + furos —
#     com a sua faixa de Z. Faces inclinadas, beirais e saliencias entram (a parte de baixo de uma saliencia e uma face).
#     Face estritamente vertical projeta em segmento (area nula): o volume dela e delimitado pelas faces que a fecham;
#   - `bbox_world_m`: o bounding box de mundo que o PROPRIO SketchUp calcula para o grupo — o validador Python confere que a
#     pegada extraida cobre esse bbox (extracao incompleta = BLOCKED, nunca PASS);
#   - contagens: faces visitadas, verticais, nao verticais, entidades ocultas puladas.
# Limites (documentados no validador): entidade oculta e ignorada; superficie curva vem facetada (como o SketchUp a guarda);
# objeto feito SO de faces verticais sem tampa teria pegada nula (detectado pela cobertura do bbox).
require_relative 'skmcp_runtime'

module SkmcpGeometry
  VERTICAL_NZ = 1.0e-3 # |n.z| abaixo disto = face vertical (projecao sem area)

  def self.pts_m(loop, tr)
    loop.vertices.map do |v|
      p = tr * v.position
      [SkmcpRuntime.to_m(p.x), SkmcpRuntime.to_m(p.y), SkmcpRuntime.to_m(p.z)]
    end
  end

  def self.normal_z(face, tr)
    n = face.normal.transform(tr)
    n.length > 0 ? (n.z / n.length) : 0.0
  end

  def self.collect(ents, tr, acc)
    ents.each do |e|
      case e
      when Sketchup::Face
        acc[:n_faces] += 1
        outer = pts_m(e.outer_loop, tr)
        zs = outer.map { |p| p[2] }
        acc[:zmin] = [acc[:zmin], zs.min].compact.min
        acc[:zmax] = [acc[:zmax], zs.max].compact.max
        if normal_z(e, tr).abs < VERTICAL_NZ
          acc[:n_vertical] += 1
          next
        end
        holes = e.loops.reject(&:outer?).map { |l| pts_m(l, tr).map { |p| [p[0].round(5), p[1].round(5)] } }
        acc[:faces] << { 'zmin' => zs.min.round(5), 'zmax' => zs.max.round(5),
                         'inclined' => (zs.max - zs.min) > 1.0e-4,
                         'outer' => outer.map { |p| [p[0].round(5), p[1].round(5)] }, 'holes' => holes }
      when Sketchup::Group, Sketchup::ComponentInstance
        if e.hidden?
          acc[:hidden_skipped] += 1
          next
        end
        acc[:nested] += 1
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
    acc = { faces: [], zmin: nil, zmax: nil, n_faces: 0, n_vertical: 0, hidden_skipped: 0, nested: 0 }
    SkmcpGeometry.collect(e.definition.entities, e.transformation, acc)
    name = e.name.to_s.empty? ? e.definition.name : e.name
    groups << { 'name' => name, 'hidden' => e.hidden?, 'zmin_m' => acc[:zmin], 'zmax_m' => acc[:zmax],
                'bbox_world_m' => SkmcpRuntime.bbox_m(e.bounds),
                'counts' => { 'faces' => acc[:n_faces], 'vertical' => acc[:n_vertical],
                              'projected' => acc[:faces].size, 'nested' => acc[:nested],
                              'hidden_skipped' => acc[:hidden_skipped] },
                'projected_faces' => acc[:faces] }
  end
  units = (model.options['UnitsOptions']['LengthUnit'] rescue nil)
  { 'title' => model.title, 'path' => model.path, 'length_unit_code' => units, 'unit' => 'm',
    'frame' => 'sketchup_world', 'groups' => groups }
end
