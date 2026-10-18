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
  def walk(entities, depth: 4, prefix: nil, acc: [])
    entities.each do |e|
      next unless e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
      name = e.name.to_s
      defn = e.definition.name.to_s
      label = name.empty? ? defn : name
      path = prefix ? "#{prefix}/#{label}" : label
      info = { 'name' => name, 'definition' => defn, 'pid' => e.persistent_id, 'path' => path,
               'type' => e.is_a?(Sketchup::Group) ? 'group' : 'component' }
      acc << [e, info]
      walk(e.definition.entities, depth: depth - 1, prefix: path, acc: acc) if depth > 1
    end
    acc
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
