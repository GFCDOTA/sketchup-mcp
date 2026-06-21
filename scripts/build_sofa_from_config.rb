# build_sofa_from_config.rb — gera UM sofa a partir de um config JSON.
# Rodar: SketchUp.exe <bootstrap.skp> -RubyStartup scripts/build_sofa_from_config.rb
# ENV: SOFA_CONFIG (json com 1 config), SOFA_SCHEMA, SOFA_OUT_DIR, SOFA_LOG.

require 'json'
require 'fileutils'
require_relative 'sofa_generator'

ROOT = File.dirname(File.dirname(__FILE__))
LOGP = ENV['SOFA_LOG'] || File.join(ROOT, 'renders', 'sofa_eval', 'from_config_done.txt')

begin
  schema = SofaGenerator.load_schema(ENV['SOFA_SCHEMA'] || File.join(ROOT, 'configs', 'sofa_schema.json'))
  cfg = JSON.parse(File.read(ENV['SOFA_CONFIG']))
  cfg = cfg[0] if cfg.is_a?(Array)
  dir = ENV['SOFA_OUT_DIR'] || File.join(ROOT, 'renders', 'sofa_eval', cfg['id'])
  vj = SofaGenerator.generate(cfg, schema, dir)
  FileUtils.mkdir_p(File.dirname(LOGP))
  File.write(LOGP, "done id=#{cfg['id']} status=#{vj[:status]} bbox=#{vj[:bbox_m]} warns=#{(vj[:warnings] || []).size}\nout=#{dir}\n")
rescue StandardError => e
  begin
    FileUtils.mkdir_p(File.dirname(LOGP))
    File.write(LOGP, "ERROR: #{e.class}: #{e.message}\n#{e.backtrace.first(15).join("\n")}\n")
  rescue StandardError
    nil
  end
end
