# shaker_build.rb — materializa um `shaker_door_plan.v1` VALIDADO dentro do gabinete pai que já está no .skp ABERTO (a cópia
# de trabalho) e salva. Job irmão do cabinet_build.rb (que continua protegido: só aceita shared.cabinet.parametric).
#
# Rodado por tools/rooms/shared/cabinet/shaker/sketchup.py via tools/sketchup/batch.run_job (SKMCP_PARAMS / SKMCP_RESULT).
# Params:
#   plan      o plano Shaker (o Python já chamou require_valid_shaker; aqui só se recusa plano nao-OK / de outra capacidade)
#   save_as   caminho de saída (só se o SketchUp abriu SEM arquivo)
#   edits     lista opcional de edições locais (mesma operação, tudo-ou-nada), como no cabinet_build:
#               {op:'edit_definition', part:<id>, size_m:[x,y,z], propagate:true|false}
#               {op:'set_material',    part:<id>, material:<nome>}
#
# Garantias (provadas em L2 no SketchUp real):
# - Só mexe DENTRO do gabinete pai "Cabinet_<parent_request_id>": apaga a frente lisa que a Shaker substitui (substituição
#   explícita — nada de frente lisa sob a Shaker) e cria UM subgrupo "Shaker_<request_id>" com as 5 peças. Arquitetura e
#   outros objetos do modelo não são tocados.
# - O pai tem que existir E ter a mesma assinatura do plano (`parent_plan_signature`): pai alterado depois = recusa (R-12/R-18).
# - Reexecução do MESMO request_id substitui o subgrupo anterior, nunca duplica (R-16).
# - Peças = instâncias de componente editáveis; uma definição por peça equivalente; edit_definition sem propagate faz
#   make_unique; com propagate:true a mudança chega às equivalentes — só quando pedida (R-10, R-11).
# - Veio: registrado como atributo, NÃO aplicado (sem UV) -> grain_support = NOT_SUPPORTED (R-14).
require 'json'
require 'digest'
require_relative '../../../../sketchup/ruby/skmcp_runtime'

DICT = 'skmcp_shaker'
PARENT_DICT = 'skmcp_cabinet'
IN_PER_M = 1.0 / 0.0254

def shk_in(v)
  v.to_f * IN_PER_M
end

def shk_color(name)
  h = Digest::SHA256.hexdigest(name.to_s)
  [h[0, 2], h[2, 2], h[4, 2]].map { |x| 64 + (x.hex % 160) }
end

def shk_material(model, name)
  mat = model.materials[name] || model.materials.add(name)
  mat.color = Sketchup::Color.new(*shk_color(name))
  mat
end

def shk_tag(model, name)
  model.layers[name] || model.layers.add(name)
end

def shk_build_box(defn, size_m)
  sx, sy, sz = size_m.map { |v| shk_in(v) }
  face = defn.entities.add_face([[0, 0, 0], [sx, 0, 0], [sx, sy, 0], [0, sy, 0]])
  face.reverse! if face.normal.z < 0
  face.pushpull(sz)
end

def shk_defn_name(request_id, key)
  "ShakerDef_#{request_id}_#{key.gsub(/[^A-Za-z0-9_.:-]+/, '_')}"
end

def shk_parent(model, request_id)
  model.entities.grep(Sketchup::Group).find do |g|
    g.get_attribute(PARENT_DICT, 'root') == true && g.get_attribute(PARENT_DICT, 'request_id') == request_id
  end
end

def shk_subgroups(parent, request_id)
  parent.entities.grep(Sketchup::Group).select do |g|
    g.get_attribute(DICT, 'root') == true && g.get_attribute(DICT, 'request_id') == request_id
  end
end

def shk_drop_definition_if_unused(model, defn)
  model.definitions.remove(defn) if defn.valid? && defn.count_used_instances.zero? && !defn.image?
rescue StandardError
  nil # remover a definição órfã é higiene; sem isso o modelo continua correto
end

def shk_parts_by_id(sub)
  sub.entities.grep(Sketchup::ComponentInstance).to_h { |i| [i.get_attribute(DICT, 'part_id'), i] }
end

def shk_apply_edit(model, sub, edit)
  inst = shk_parts_by_id(sub)[edit['part']]
  raise "edição: peça '#{edit['part']}' não existe" unless inst

  case edit['op']
  when 'edit_definition'
    before = inst.definition.count_used_instances
    inst.make_unique if !edit['propagate'] && before > 1
    defn = inst.definition
    defn.entities.clear!
    shk_build_box(defn, edit['size_m'])
    { 'op' => edit['op'], 'part' => edit['part'], 'propagate' => edit['propagate'] ? true : false,
      'definition_instances_before' => before, 'definition' => defn.name,
      'definition_instances_after' => defn.count_used_instances }
  when 'set_material'
    inst.material = shk_material(model, edit['material'])
    inst.set_attribute(DICT, 'material', edit['material'])
    { 'op' => edit['op'], 'part' => edit['part'], 'material' => edit['material'] }
  else
    raise "edição desconhecida: #{edit['op']}"
  end
end

SkmcpRuntime.run('shaker_build') do |params, model|
  plan = params.fetch('plan')
  unless plan['schema_version'] == 'shaker_door_plan.v1' && plan['status'] == 'OK' && (plan['findings'] || []).empty? &&
         plan.dig('capability', 'id') == 'shared.cabinet.front.shaker' && plan['execution_authorized'] == false
    raise 'plano recusado: o Ruby só materializa shaker_door_plan.v1 com status OK, sem achados e sem autorizar execução'
  end

  SkmcpRuntime.close_edit_context(model)
  request_id = plan['request_id']
  parent_id = plan['parent_cabinet_request_id']
  parent = shk_parent(model, parent_id)
  raise "gabinete pai '#{parent_id}' não existe neste modelo" unless parent

  if parent.get_attribute(PARENT_DICT, 'signature') != plan['parent_plan_signature']
    raise 'o gabinete pai neste modelo tem outra assinatura que o plano Shaker (pai alterado depois do plano)'
  end

  before = model.entities.to_a.size
  replaced = 0
  removed_front = nil
  edits_report = []
  model.start_operation('shaker_build', true)
  begin
    if params['edits'].nil?
      old = shk_subgroups(parent, request_id)
      replaced = old.size
      old.each(&:erase!)
      # definições órfãs da execução anterior saem AGORA: senão a nova leva ganha nome "#1" e o modelo acumula lixo (achado L2 s3)
      model.definitions.to_a.each do |d|
        shk_drop_definition_if_unused(model, d) if d.name.start_with?("ShakerDef_#{request_id}_")
      end
      front = parent.entities.grep(Sketchup::ComponentInstance).find do |i|
        i.get_attribute(PARENT_DICT, 'part_id') == plan['replaces_part']
      end
      if front
        defn = front.definition
        front.erase!
        shk_drop_definition_if_unused(model, defn)
        removed_front = plan['replaces_part']
      elsif replaced.zero?
        raise "frente '#{plan['replaces_part']}' não existe no gabinete pai e não há Shaker anterior para substituir"
      end

      sub = parent.entities.add_group
      sub.name = "Shaker_#{request_id}"
      sub.layer = shk_tag(model, 'Cabinet')
      { 'root' => true, 'request_id' => request_id, 'parent_request_id' => parent_id, 'capability' => plan['capability']['id'],
        'capability_version' => plan['capability']['version'], 'signature' => plan['signature'],
        'parent_plan_signature' => plan['parent_plan_signature'], 'replaces_part' => plan['replaces_part'],
        'source_verified' => plan.dig('origin_context', 'source_verified') }.each { |k, v| sub.set_attribute(DICT, k, v) }
      by_part = plan['parts'].to_h { |p| [p['id'], p] }
      plan['definitions'].each do |d|
        defn = model.definitions.add(shk_defn_name(request_id, d['key']))
        shk_build_box(defn, d['size_m'])
        d['instances'].each do |pid|
          part = by_part.fetch(pid)
          origin = Geom::Point3d.new(*part['min_m'].map { |v| shk_in(v) })
          inst = sub.entities.add_instance(defn, Geom::Transformation.new(origin))
          inst.name = part['id']
          inst.layer = shk_tag(model, "Cabinet_#{part['role']}")
          inst.material = shk_material(model, part['material'])
          { 'part_id' => part['id'], 'role' => part['role'], 'material' => part['material'], 'grain' => part['grain'],
            'request_id' => request_id, 'signature' => plan['signature'] }.each { |k, v| inst.set_attribute(DICT, k, v) }
        end
      end
    else
      sub = shk_subgroups(parent, request_id).first
      raise "edições: nenhuma Shaker '#{request_id}' neste modelo" unless sub

      params['edits'].each { |e| edits_report << shk_apply_edit(model, sub, e) }
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

  { 'built' => params['edits'].nil?, 'request_id' => request_id, 'parent_request_id' => parent_id,
    'replaced_previous' => replaced, 'removed_front' => removed_front, 'entities_before' => before,
    'entities_after' => model.entities.to_a.size,
    'definitions' => model.definitions.map { |d| [d.name, d.count_used_instances] }.select { |n, _| n.start_with?('ShakerDef_') }.to_h,
    'edits' => edits_report, 'grain_support' => 'NOT_SUPPORTED',
    'grain_note' => 'veio registrado como atributo; sem textura/UV não é aplicado nem verificado',
    'saved' => true, 'out_skp' => path, 'size_bytes' => File.size(path) }
end
