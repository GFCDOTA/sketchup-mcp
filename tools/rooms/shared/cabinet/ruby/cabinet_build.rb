# cabinet_build.rb — materializa um `cabinet_assembly_plan.v1` VALIDADO no .skp ABERTO (a cópia de trabalho) e salva.
#
# Rodado por tools/rooms/shared/cabinet/sketchup.py via tools/sketchup/batch.run_job (mesmo contrato dos jobs su_*):
#   SketchUp.exe [<copia.skp>] -RubyStartup skmcp_launch.rb   (SKMCP_PARAMS / SKMCP_RESULT)
# Params:
#   plan        o plano (o Python já chamou require_valid; aqui só se recusa plano nao-OK / de outra capacidade)
#   save_as     caminho de saída (obrigatório quando o SketchUp abriu SEM arquivo)
#   edits       lista opcional de edições locais (mesma operação, tudo-ou-nada):
#                 {op:'edit_definition', part:<id>, size_m:[x,y,z], propagate:true|false}
#                 {op:'set_material',    part:<id>, material:<nome>}
#
# Garantias (testadas em L2 no SketchUp real):
# - Cria SÓ um grupo raiz "Cabinet_<request_id>" com tag Cabinet; nunca toca outra entidade do modelo.
# - Reexecução controlada: o grupo anterior do MESMO request_id (marcado pelo atributo skmcp_cabinet) é substituído,
#   nunca duplicado. Outros gabinetes e a arquitetura ficam como estão.
# - Peças = instâncias de componente (editáveis), uma definição por peça equivalente (definições compartilhadas só entre
#   peças equivalentes). edit_definition sem propagate faz make_unique antes; com propagate:true a mudança chega às
#   equivalentes — somente quando pedida.
# - Material por peça: nome do plano + cor derivada do nome (sem textura). Veio: registrado em atributo, NÃO aplicado
#   (sem textura/UV) -> grain_support = NOT_SUPPORTED. Não declara PASS de veio.
require 'json'
require 'digest'
require_relative '../../../../sketchup/ruby/skmcp_runtime'

DICT = 'skmcp_cabinet'
IN_PER_M = 1.0 / 0.0254

def cab_in(v)
  v.to_f * IN_PER_M
end

def cab_color(name)
  h = Digest::SHA256.hexdigest(name.to_s)
  [h[0, 2], h[2, 2], h[4, 2]].map { |x| 64 + (x.hex % 160) }
end

def cab_material(model, name)
  mat = model.materials[name] || model.materials.add(name)
  mat.color = Sketchup::Color.new(*cab_color(name))
  mat
end

def cab_tag(model, name)
  model.layers[name] || model.layers.add(name)
end

def cab_build_box(defn, size_m)
  sx, sy, sz = size_m.map { |v| cab_in(v) }
  pts = [[0, 0, 0], [sx, 0, 0], [sx, sy, 0], [0, sy, 0]]
  face = defn.entities.add_face(pts)
  face.reverse! if face.normal.z < 0
  face.pushpull(sz)
end

def cab_defn_name(request_id, key)
  "CabinetDef_#{request_id}_#{key.gsub(/[^A-Za-z0-9_.:-]+/, '_')}"
end

def cab_remove_previous(model, request_id)
  removed = 0
  model.entities.grep(Sketchup::Group).each do |g|
    next unless g.get_attribute(DICT, 'request_id') == request_id && g.get_attribute(DICT, 'root') == true

    g.erase!
    removed += 1
  end
  model.definitions.purge_unused if removed.positive?
  removed
end

def cab_find_root(model, request_id)
  model.entities.grep(Sketchup::Group).find do |g|
    g.get_attribute(DICT, 'request_id') == request_id && g.get_attribute(DICT, 'root') == true
  end
end

def cab_parts_by_id(root)
  root.entities.grep(Sketchup::ComponentInstance).to_h { |i| [i.get_attribute(DICT, 'part_id'), i] }
end

def cab_apply_edit(model, root, edit)
  inst = cab_parts_by_id(root)[edit['part']]
  raise "edição: peça '#{edit['part']}' não existe" unless inst

  case edit['op']
  when 'edit_definition'
    propagated = inst.definition.count_used_instances
    inst.make_unique if !edit['propagate'] && inst.definition.count_used_instances > 1
    defn = inst.definition
    defn.entities.clear!
    cab_build_box(defn, edit['size_m'])
    { 'op' => edit['op'], 'part' => edit['part'], 'propagate' => edit['propagate'] ? true : false,
      'definition_instances_before' => propagated, 'definition' => defn.name,
      'definition_instances_after' => defn.count_used_instances }
  when 'set_material'
    inst.material = cab_material(model, edit['material'])
    inst.set_attribute(DICT, 'material', edit['material'])
    { 'op' => edit['op'], 'part' => edit['part'], 'material' => edit['material'] }
  else
    raise "edição desconhecida: #{edit['op']}"
  end
end

SkmcpRuntime.run('cabinet_build') do |params, model|
  plan = params.fetch('plan')
  unless plan['schema_version'] == 'cabinet_assembly_plan.v1' && plan['status'] == 'OK' && (plan['findings'] || []).empty? &&
         plan.dig('capability', 'id') == 'shared.cabinet.parametric'
    raise 'plano recusado: o Ruby só materializa cabinet_assembly_plan.v1 com status OK e sem achados'
  end

  SkmcpRuntime.close_edit_context(model)
  request_id = plan['request_id']
  pose = plan['pose']
  root_name = "Cabinet_#{request_id}"
  before = model.entities.to_a.size
  removed = 0
  edits_report = []
  model.start_operation('cabinet_build', true)
  begin
    if params['edits'].nil?
      removed = cab_remove_previous(model, request_id)
      root = model.entities.add_group
      root.name = root_name
      root.layer = cab_tag(model, 'Cabinet')
      root.set_attribute(DICT, 'root', true)
      root.set_attribute(DICT, 'request_id', request_id)
      root.set_attribute(DICT, 'capability', plan['capability']['id'])
      root.set_attribute(DICT, 'capability_version', plan['capability']['version'])
      root.set_attribute(DICT, 'signature', plan['signature'])
      by_part = plan['parts'].to_h { |p| [p['id'], p] }
      plan['definitions'].each do |d|
        defn = model.definitions.add(cab_defn_name(request_id, d['key']))
        cab_build_box(defn, d['size_m'])
        d['instances'].each do |pid|
          part = by_part.fetch(pid)
          origin = Geom::Point3d.new(*part['min_m'].map { |v| cab_in(v) })
          inst = root.entities.add_instance(defn, Geom::Transformation.new(origin))
          inst.name = part['id']
          inst.layer = cab_tag(model, "Cabinet_#{part['role']}")
          inst.material = cab_material(model, part['material'])
          { 'part_id' => part['id'], 'role' => part['role'], 'material' => part['material'], 'grain' => part['grain'],
            'request_id' => request_id, 'signature' => plan['signature'] }.each { |k, v| inst.set_attribute(DICT, k, v) }
        end
      end
      pos = Geom::Point3d.new(cab_in(pose['x']), cab_in(pose['y']), cab_in(pose['z']))
      root.transformation = Geom::Transformation.new(pos) *
                            Geom::Transformation.rotation(Geom::Point3d.new(0, 0, 0), Z_AXIS, pose['rotation_deg'].to_f.degrees)
    else
      root = cab_find_root(model, request_id)
      raise "edições: nenhum gabinete '#{request_id}' neste modelo" unless root

      params['edits'].each { |e| edits_report << cab_apply_edit(model, root, e) }
    end
    model.commit_operation
  rescue Exception # rubocop:disable Lint/RescueException
    model.abort_operation
    raise
  end

  target = params['save_as'].to_s
  path = model.path.to_s
  if path.empty?
    raise 'o modelo não tem caminho e save_as não foi dado' if target.empty?

    saved = model.save(target)
    path = target
  else
    saved = model.save
  end
  raise "save falhou para #{path}" unless saved && File.exist?(path)

  { 'built' => params['edits'].nil?, 'request_id' => request_id, 'root' => root_name, 'replaced_previous' => removed,
    'entities_before' => before, 'entities_after' => model.entities.to_a.size,
    'definitions' => model.definitions.map { |d| [d.name, d.count_used_instances] }.select { |n, _| n.start_with?('CabinetDef_') }.to_h,
    'edits' => edits_report, 'grain_support' => 'NOT_SUPPORTED',
    'grain_note' => 'veio registrado como atributo; sem textura/UV não é aplicado nem verificado',
    'saved' => true, 'out_skp' => path, 'size_bytes' => File.size(path) }
end
