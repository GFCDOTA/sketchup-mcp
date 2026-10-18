# apply_edits.rb — aplica uma lista de edições ao .skp ABERTO e o salva.
#
# O .skp aberto já é a CÓPIA de destino (tools/sketchup/jobs.py copia a entrada
# antes): o original nunca é aberto, então nem um Ctrl+S na janela que fica
# aberta em modo interactive o alcança.
#
# Tudo-ou-nada: as ops rodam dentro de UMA operação do SketchUp; qualquer erro
# aborta a operação inteira e nada é salvo.
#
# Params: ops (já validadas por tools/sketchup/ops.py), protected_prefixes.
# A regra de arquitetura é revalidada aqui: `name_contains`/`persistent_id` só
# revelam QUAIS entidades casam dentro do modelo.
require_relative 'skmcp_runtime'

# rename entra junto: renomear tiraria o grupo da proteção e liberaria o move seguinte
GUARDED = %w[move rotate delete rename].freeze

def skmcp_material(model, op)
  if op['material']
    mat = model.materials[op['material']]
    raise "material '#{op['material']}' não existe no modelo" unless mat
    return mat
  end
  if op['color']
    name = op['material_name'] || "skmcp_rgb_#{op['color'].join('_')}"
    mat = model.materials[name] || model.materials.add(name)
    mat.color = Sketchup::Color.new(*op['color'])
    return mat
  end
  name = op['material_name'] || "skmcp_tex_#{File.basename(op['texture'], '.*')}"
  mat = model.materials[name] || model.materials.add(name)
  mat.texture = op['texture']
  raise "textura não carregou: #{op['texture']}" unless mat.texture
  size = op.fetch('texture_size_m', 1.0).to_f.m
  mat.texture.size = [size, size]
  mat
end

def skmcp_apply(model, op, entity)
  case op['op']
  when 'set_material' then entity.material = skmcp_material(model, op)
  when 'move'
    dx, dy, dz = op['by_m'].map { |v| v.to_f.m }
    entity.transform!(Geom::Transformation.translation(Geom::Vector3d.new(dx, dy, dz)))
  when 'rotate'
    entity.transform!(Geom::Transformation.rotation(entity.bounds.center, Z_AXIS, op['degrees'].to_f.degrees))
  when 'set_tag' then entity.layer = (model.layers[op['tag']] || model.layers.add(op['tag']))
  when 'set_hidden' then entity.hidden = op['hidden']
  when 'rename' then entity.name = op['name']
  when 'delete' then entity.erase!
  else raise "op desconhecida: #{op['op']}"
  end
end

SkmcpRuntime.run('apply_edits') do |params, model|
  prefixes = params['protected_prefixes'] || []
  report = []
  model.start_operation('skmcp apply_edits', true)
  begin
    params.fetch('ops').each_with_index do |op, i|
      if op['op'] == 'insert_component'
        defn = model.definitions.load(op['skp_path'])
        x, y, z = op['position_m'].map { |v| v.to_f.m }
        origin = Geom::Point3d.new(x, y, z)
        tr = Geom::Transformation.translation(origin) *
             Geom::Transformation.rotation(ORIGIN, Z_AXIS, op['rotation_deg'].to_f.degrees)
        inst = model.active_entities.add_instance(defn, tr)
        inst.name = op['name'] if op['name']
        inst.layer = (model.layers[op['tag']] || model.layers.add(op['tag'])) if op['tag']
        report << { 'index' => i, 'op' => op['op'], 'inserted' => defn.name, 'pid' => inst.persistent_id }
        next
      end

      infos = SkmcpRuntime.walk(model.entities)
      hits, err = SkmcpCore.select(infos.map(&:last), op['target'])
      raise "ops[#{i}] (#{op['op']}): #{err}" if err
      if GUARDED.include?(op['op'])
        prot = hits.select { |h| SkmcpCore.protected_name?(h['name'], prefixes) }
        unless prot.empty?
          raise "ops[#{i}] (#{op['op']}): #{prot.map { |h| h['path'] }.inspect} é arquitetura " \
                "derivada do PDF — #{op['op']} proibido (Hard Rule #1)"
        end
      end
      by_pid = infos.to_h { |e, info| [info['pid'], e] }
      hits.each do |h|
        e = by_pid[h['pid']]
        skmcp_apply(model, op, e) unless e.deleted? # pai apagado antes leva o filho junto
      end
      report << { 'index' => i, 'op' => op['op'], 'matched' => hits.map { |h| h['path'] } }
    end
    model.commit_operation
  rescue Exception # rubocop:disable Lint/RescueException
    model.abort_operation
    raise
  end

  path = model.path
  raise 'o modelo aberto não tem caminho — o Python sempre abre a cópia de destino' if path.to_s.empty?
  saved = model.save
  raise "save falhou para #{path}" unless saved && File.exist?(path)
  { 'applied' => report, 'saved' => true, 'out_skp' => path, 'size_bytes' => File.size(path) }
end
