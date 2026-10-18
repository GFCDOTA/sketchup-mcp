# skmcp_runtime.rb — o contrato entre tools/sketchup/batch.py e os jobs Ruby.
#
#   SKMCP_PARAMS  JSON de entrada (escrito pelo Python)
#   SKMCP_RESULT  JSON de saída — escrito por ÚLTIMO e atômico (tmp + rename):
#                 existir = esta execução terminou
#   SKMCP_QUIT    "1" → fecha ESTE SketchUp depois de escrever (modo headless)
#
# O job roda num UI.start_timer: no -RubyStartup a view ainda não está pronta,
# e write_image antes disso sai preto/vazio. `defer_s` nos params ajusta.
require 'json'
require_relative 'skmcp_core'

module SkmcpRuntime
  M_PER_IN = 0.0254

  module_function

  def params
    JSON.parse(File.read(ENV.fetch('SKMCP_PARAMS'), encoding: 'utf-8'))
  end

  def write_result(hash)
    path = ENV['SKMCP_RESULT'] || File.join(Dir.pwd, 'skmcp_result.json')
    tmp = "#{path}.tmp"
    File.write(tmp, JSON.pretty_generate(hash))
    File.rename(tmp, path)
  end

  def to_m(len)
    (len.to_f * M_PER_IN).round(4)
  end

  def bbox_m(bb)
    { 'min' => [to_m(bb.min.x), to_m(bb.min.y), to_m(bb.min.z)],
      'max' => [to_m(bb.max.x), to_m(bb.max.y), to_m(bb.max.z)],
      'size' => [to_m(bb.width), to_m(bb.height), to_m(bb.depth)] }
  end

  # Grupos e instâncias de componente até `depth` níveis, com o caminho do
  # Outliner. Retorna [[entity, info], ...].
  #
  # Cada info carrega o que a proteção e o referencial precisam:
  #   ancestors / ancestor_pids — a cadeia até a raiz (proteção olha o pai também)
  #   parent_world — transformação de MUNDO do contexto onde a entidade vive;
  #                  transform! e bounds trabalham nesse referencial, não no mundo
  #   world        — parent_world × transformação da própria entidade
  # Lê `definition.entities` (nunca `Group#entities`, que tornaria o grupo único).
  # Default de profundidade alto: a proteção precisa ver TUDO, não só 4 níveis.
  def walk(entities, depth: 64, prefix: nil, parent_world: SkmcpCore::IDENTITY,
           ancestors: [], acc: [])
    entities.each do |e|
      next unless e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
      name = e.name.to_s
      defn = e.definition.name.to_s
      label = name.empty? ? defn : name
      path = prefix ? "#{prefix}/#{label}" : label
      world = SkmcpCore.mat_mul(parent_world, e.transformation.to_a)
      locked = (e.locked? rescue false)
      info = { 'name' => name, 'definition' => defn, 'pid' => e.persistent_id, 'path' => path,
               'type' => e.is_a?(Sketchup::Group) ? 'group' : 'component',
               'locked' => locked, 'ancestors' => ancestors,
               'ancestor_pids' => ancestors.map { |a| a['pid'] },
               'parent_world' => parent_world, 'world' => world }
      acc << [e, info]
      next unless depth > 1

      me = { 'pid' => e.persistent_id, 'label' => label, 'name' => name,
             'definition' => defn, 'locked' => locked }
      walk(e.definition.entities, depth: depth - 1, prefix: path, parent_world: world,
                                  ancestors: ancestors + [me], acc: acc)
    end
    acc
  end

  # bbox de mundo em metros, a partir do bbox da definição e da matriz de mundo.
  def bbox_world_m(entity, world)
    bb = entity.definition.bounds
    lo, hi = SkmcpCore.world_bbox([bb.min.x, bb.min.y, bb.min.z].map(&:to_f),
                                  [bb.max.x, bb.max.y, bb.max.z].map(&:to_f), world)
    { 'min' => lo.map { |v| to_m(v) }, 'max' => hi.map { |v| to_m(v) },
      'size' => (0..2).map { |i| to_m(hi[i] - lo[i]) } }
  end

  def run(job)
    defer = 2.0
    begin
      defer = params.fetch('defer_s', defer).to_f
    rescue StandardError
      nil # params ilegível: o erro aparece no próprio run, com mensagem
    end
    UI.start_timer(defer, false) do
      started = Time.now
      result =
        begin
          { 'ok' => true, 'job' => job }.merge(yield(params, Sketchup.active_model))
        rescue Exception => e # rubocop:disable Lint/RescueException — ScriptError também vira resultado
          { 'ok' => false, 'job' => job, 'error' => "#{e.class}: #{e.message}",
            'backtrace' => (e.backtrace || []).first(12) }
        end
      result['elapsed_s'] = (Time.now - started).round(2)
      result['sketchup_version'] = (Sketchup.version rescue nil)
      write_result(result)
      Sketchup.quit if ENV['SKMCP_QUIT'] == '1'
    end
  end
end
