# apply_edits.rb — aplica uma lista de edições ao .skp ABERTO e o salva.
#
# O .skp aberto já é a CÓPIA de destino (tools/sketchup/jobs.py copia a entrada
# antes): o original nunca é aberto, então nem um Ctrl+S na janela que fica
# aberta em modo interactive o alcança.
#
# Tudo-ou-nada: as ops rodam dentro de UMA operação do SketchUp; qualquer erro
# aborta a operação inteira e nada é salvo.
#
# Params: ops (já validadas por tools/sketchup/ops.py), protected_prefixes,
# protected_substrings. A regra de arquitetura é revalidada aqui:
# `name_contains`/`persistent_id` só revelam QUAIS entidades casam dentro do
# modelo. A recusa olha a entidade, os ancestrais, os descendentes, a definição,
# `locked` e se a definição é compartilhada (SkmcpCore.guard_violation).
# insert_component também recusa um .skp que TRAGA arquitetura dentro (uma 2ª
# cópia da planta inventaria paredes — Hard Rule #1).
#
# Referencial: `by_m` e `rotate` são em eixos do MUNDO. Entity#transform! age no
# referencial do PAI — num grupo girado, um move "cru" andaria nos eixos girados.
# Por isso o vetor vai para o local do pai, e a rotação de mundo é conjugada
# inteira (SkmcpCore.local_transform_for_world). Qualquer grupo aberto no .skp é
# fechado antes (SkmcpRuntime.close_edit_context): o walk e o insert assumem a raiz.
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

def skmcp_apply(model, op, entity, info)
  case op['op']
  when 'set_material' then entity.material = skmcp_material(model, op)
  when 'move'
    v_world = op['by_m'].map { |v| v.to_f.m.to_f }
    v_local = SkmcpCore.world_to_local_vector(info['parent_world'], v_world)
    entity.transform!(Geom::Transformation.translation(Geom::Vector3d.new(*v_local)))
  when 'rotate'
    bb = entity.definition.bounds
    lo, hi = SkmcpCore.world_bbox([bb.min.x, bb.min.y, bb.min.z].map(&:to_f),
                                  [bb.max.x, bb.max.y, bb.max.z].map(&:to_f), info['world'])
    c_world = (0..2).map { |i| (lo[i] + hi[i]) / 2.0 }
    # conjuga a rotação de MUNDO inteira para o local do pai: exato sob qualquer
    # pai invertível (espelhado, escala não uniforme) — no mundo segue rígido
    t_local = SkmcpCore.local_transform_for_world(info['parent_world'],
                                                  SkmcpCore.rotation_z(c_world, op['degrees']))
    entity.transform!(Geom::Transformation.new(t_local))
  when 'set_tag' then entity.layer = (model.layers[op['tag']] || model.layers.add(op['tag']))
  when 'set_hidden' then entity.hidden = op['hidden']
  when 'rename' then entity.name = op['name']
  when 'delete' then entity.erase!
  else raise "op desconhecida: #{op['op']}"
  end
end

SkmcpRuntime.run('apply_edits') do |params, model|
  prefixes = params['protected_prefixes'] || []
  substrings = params['protected_substrings'] || []
  report = []
  SkmcpRuntime.close_edit_context(model)
  model.start_operation('skmcp apply_edits', true)
  begin
    params.fetch('ops').each_with_index do |op, i|
      if op['op'] == 'insert_component'
        defn = model.definitions.load(op['skp_path'])
        # DefinitionList#load nomeia a definição pelo nome do ARQUIVO: um
        # Window_x.skp viraria "arquitetura do PDF" para a guarda e o inspect
        if SkmcpCore.protected_name?(defn.name, prefixes, substrings)
          raise "ops[#{i}] (insert_component): a definição carregada '#{defn.name}' usa prefixo " \
                'reservado para arquitetura do PDF (Hard Rule #1)'
        end
        # ...e o CONTEÚDO: carregar o .skp de uma planta traria PlanShell_/Window_
        # aninhados — paredes fora do consensus, e um móvel que a guarda nunca
        # mais deixaria mover. O raise cai no rescue: abort_operation, nada salvo.
        inner = SkmcpRuntime.protected_inside(defn, prefixes, substrings)
        unless inner.empty?
          raise "ops[#{i}] (insert_component): '#{File.basename(op['skp_path'])}' traz entidades com " \
                "nome de arquitetura do PDF: #{inner.first(5).map { |n| n['path'] }.inspect} (Hard Rule #1)"
        end
        x, y, z = op['position_m'].map { |v| v.to_f.m }
        origin = Geom::Point3d.new(x, y, z)
        tr = Geom::Transformation.translation(origin) *
             Geom::Transformation.rotation(ORIGIN, Z_AXIS, op['rotation_deg'].to_f.degrees)
        inst = model.entities.add_instance(defn, tr) # raiz: position_m é de mundo
        inst.name = op['name'] if op['name']
        inst.layer = (model.layers[op['tag']] || model.layers.add(op['tag'])) if op['tag']
        report << { 'index' => i, 'op' => op['op'], 'inserted' => defn.name, 'pid' => inst.persistent_id }
        next
      end

      pairs = SkmcpRuntime.walk(model.entities) # recalculado a cada op: a anterior pode ter movido/apagado
      infos = SkmcpCore.dedupe(pairs.map(&:last))
      hits, err = SkmcpCore.select(infos, op['target'])
      raise "ops[#{i}] (#{op['op']}): #{err}" if err
      if GUARDED.include?(op['op'])
        bad = hits.map { |h| SkmcpCore.guard_violation(h, infos, prefixes, substrings) }.compact
        raise "ops[#{i}] (#{op['op']}) recusado: #{bad.first(5).join('; ')} (Hard Rule #1)" unless bad.empty?
      end
      if %w[move rotate].include?(op['op'])
        nested = SkmcpCore.nested_hits(hits)
        unless nested.empty?
          raise "ops[#{i}] (#{op['op']}): o alvo casa um grupo E peças dentro dele — elas andariam " \
                "duas vezes: #{nested.first(5).map { |h| h['path'] }.inspect}; restrinja o alvo"
        end
      end
      by_pid = pairs.to_h { |e, info| [info['pid'], e] }
      hits.each do |h|
        e = by_pid[h['pid']]
        skmcp_apply(model, op, e, h) unless e.deleted? # pai apagado antes leva o filho junto
      end
      report << { 'index' => i, 'op' => op['op'], 'matched' => hits.map { |h| h['path'] },
                  'contexts' => hits.map { |h| h['contexts'] } }
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
