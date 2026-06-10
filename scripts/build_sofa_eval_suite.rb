# build_sofa_eval_suite.rb — primitives board + suite de avaliacao (rescue por caso).
# Rodar: SketchUp.exe <bootstrap.skp> -RubyStartup scripts/build_sofa_eval_suite.rb
# ENV: SOFA_SCHEMA, SOFA_ARCHETYPES, SOFA_EVAL, SOFA_EVAL_DIR, SOFA_LOG,
#      SOFA_SUBSET (ids separados por virgula; vazio = subset minimo da Fase 15).

require 'json'
require 'fileutils'
require_relative 'sofa_generator'
require_relative 'sofa_primitives'

SP = SofaPrimitives
ROOT = File.dirname(File.dirname(__FILE__))
EVAL = ENV['SOFA_EVAL_DIR'] || File.join(ROOT, 'renders', 'sofa_eval')
LOGP = ENV['SOFA_LOG'] || File.join(EVAL, 'suite_done.txt')

# Prancha de PRIMITIVAS isoladas (Fase 11). Se assento/encosto ainda parecerem
# caixa, e aqui que se ve antes de montar sofas.
def primitives_board(model, dir)
  model.entities.clear!
  e = model.active_entities
  fab = SP.mat(model, 'b_fab', [210, 200, 185])
  wood = SP.mat(model, 'b_wood', [96, 66, 44])
  seam = SP.mat(model, 'b_seam', [150, 142, 128])
  x = 0.0
  nxt = lambda { |w| x0 = x; x += w + 0.20; x0 }
  x0 = nxt.call(0.50); SP.rounded_box(e, x0, 0, x0 + 0.50, 0.50, 0, 0.30, r: 0.045, top_round: 0.045, mat_obj: fab, name: 'rounded_box')
  x0 = nxt.call(0.60); SP.seat_cushion_primitive(e, x0, 0, x0 + 0.60, 0.58, 0, 0.16, softness: 'high', mat_obj: fab, name: 'seat_cushion')
  x0 = nxt.call(0.60); SP.back_cushion_primitive(e, x0, 0, x0 + 0.60, 0.22, 0, 0.45, softness: 'medium', mat_obj: fab, name: 'back_cushion')
  x0 = nxt.call(0.60); SP.pillow_primitive(e, x0, 0, x0 + 0.60, 0.26, 0, 0.45, softness: 'high', mat_obj: fab, name: 'pillow')
  x0 = nxt.call(0.13); SP.rounded_box(e, x0, 0, x0 + 0.13, 0.90, 0, 0.50, r: 0.03, top_round: 0.03, mat_obj: fab, name: 'arm_slim')
  x0 = nxt.call(0.28); SP.soft_rounded_box(e, x0, 0, x0 + 0.28, 0.90, 0, 0.50, softness: 'high', mat_obj: fab, name: 'arm_wide')
  x0 = nxt.call(0.26); SP.rolled_arm_primitive(e, x0, 0, x0 + 0.26, 0.90, 0, 0.50, softness: 'high', mat_obj: fab, name: 'arm_rolled')
  x0 = nxt.call(0.10); SP.tapered_leg(e, x0 + 0.05, 0.05, 0.05, 0, 0.16, mat_obj: wood, name: 'tapered_leg')
  x0 = nxt.call(0.10); SP.block_leg(e, x0 + 0.05, 0.05, 0.05, 0, 0.16, mat_obj: wood, name: 'block_leg')
  x0 = nxt.call(0.60); SP.seat_cushion_primitive(e, x0, 0, x0 + 0.60, 0.58, 0, 0.16, softness: 'high', mat_obj: fab, name: 'cushion_seam', seam: true, seam_mat: seam)

  FileUtils.mkdir_p(dir)
  view = model.active_view
  bb = model.bounds
  c = bb.center
  dg = bb.diagonal
  ex = bb.max.x - bb.min.x
  ez = bb.max.z - bb.min.z
  up = Geom::Vector3d.new(0, 0, 1)
  camf = Sketchup::Camera.new(Geom::Point3d.new(c.x, bb.min.y - dg, c.z), c, up)
  camf.perspective = false
  camf.height = [ez, ex / (1600.0 / 1200.0)].max * 1.10
  view.camera = camf
  view.write_image(filename: File.join(dir, 'primitives_front.png'), width: 1600, height: 1200, antialias: true)
  camq = Sketchup::Camera.new(Geom::Point3d.new(bb.max.x + dg * 0.5, bb.min.y - dg * 0.9, c.z + dg * 0.45), c, up)
  camq.perspective = true
  view.camera = camq
  view.zoom_extents
  view.write_image(filename: File.join(dir, 'primitives_three_quarter.png'), width: 1600, height: 1200, antialias: true)
end

begin
  schema = SofaGenerator.load_schema(ENV['SOFA_SCHEMA'] || File.join(ROOT, 'configs', 'sofa_schema.json'))
  arch = JSON.parse(File.read(ENV['SOFA_ARCHETYPES'] || File.join(ROOT, 'configs', 'sofa_archetypes.json')))
  evalc = JSON.parse(File.read(ENV['SOFA_EVAL'] || File.join(ROOT, 'configs', 'sofa_eval_cases.json')))
  all = arch + evalc
  subset = (ENV['SOFA_SUBSET'] || '').split(',').map(&:strip).reject(&:empty?)
  default_min = %w[
    straight_3seat_track_arm_split_cushion_back
    straight_2seat_slim_arm_split_cushion_back
    bench_seat_tight_back_exposed_legs
    eval_loveseat_slim_arm_tight_back
    eval_3seat_bench_wide_arm_recessed_base
  ]
  pick = subset.empty? ? all.select { |c| default_min.include?(c['id']) } : all.select { |c| subset.include?(c['id']) }

  model = Sketchup.active_model
  results = []
  begin
    primitives_board(model, File.join(EVAL, 'primitives'))
    results << 'primitives_board OK -> primitives_front.png, primitives_three_quarter.png'
  rescue StandardError => e
    results << "primitives_board ERROR #{e.class}: #{e.message} | #{e.backtrace.first}"
  end
  pick.each do |cfg|
    begin
      vj = SofaGenerator.generate(cfg, schema, File.join(EVAL, cfg['id']))
      results << "#{cfg['id']} #{vj[:status]} bbox=#{vj[:bbox_m]} warns=#{(vj[:warnings] || []).size}"
    rescue StandardError => e
      results << "#{cfg['id']} ERROR #{e.class}: #{e.message} | #{e.backtrace.first}"
    end
  end
  FileUtils.mkdir_p(EVAL)
  File.write(LOGP, "SUITE casos=#{pick.size}\n" + results.join("\n") + "\n")
rescue StandardError => e
  begin
    FileUtils.mkdir_p(EVAL)
    File.write(LOGP, "FATAL: #{e.class}: #{e.message}\n#{e.backtrace.first(15).join("\n")}\n")
  rescue StandardError
    nil
  end
end
