# build_sofa_3seat_v1.rb — monta o sofa de 3 lugares v1 usando SO as primitivas
# de sofa_primitives.rb (docs/SOFA_SKILL.md). Renderiza front/3-4/top/side.
#
# Rodar:  SketchUp.exe <bootstrap.skp> -RubyStartup scripts/build_sofa_3seat_v1.rb
# Saidas (ENV ou default relativo ao repo):
#   SOFA_OUT_SKP  -> .skp do sofa
#   SOFA_DIR      -> pasta dos renders (default <repo>/renders/check)
#   SOFA_LOG      -> log/sinal de done (ERROR:... se falhar)
#
# Decisao 2 vs 3 almofadas de assento: v1 usa 3 ASSENTOS + 3 ENCOSTOS (vincos
# alinhados 1:1 por lugar) — leitura coerente e pedido explicito de 3 encostos.

require 'fileutils'
require_relative 'sofa_primitives'
SP = SofaPrimitives

REPO = File.dirname(File.dirname(__FILE__))
RDIR = ENV['SOFA_DIR'] || File.join(REPO, 'renders', 'check')
LOGP = ENV['SOFA_LOG'] || File.join(RDIR, 'build_done.txt')
OUTP = ENV['SOFA_OUT_SKP'] || File.join(RDIR, 'sofa_3seat_v1.skp')

begin
  FileUtils.mkdir_p(RDIR)

  # ---- parametros (metros) — espelham docs/SOFA_SKILL.md §2 ----------------
  w = 2.20    # largura total
  d = 0.95    # profundidade total
  h = 0.85    # altura total (topo do encosto)
  seats = 3
  gap = 0.015 # vinco entre almofadas

  foot_h = 0.10 # pe curto
  base_top = 0.27
  seat_h = 0.43 # topo da almofada de assento (sentar)
  arm_h  = 0.62
  arm_w  = 0.24 # braco LARGO
  back_t = 0.20 # espessura do encosto
  seat_d = 0.58 # profundidade util do assento
  rec    = 0.06 # recuo do plinto frontal
  rake_deg = 10.0  # inclinacao do encosto (8-12)

  seat_back  = d - back_t
  seat_front = seat_back - seat_d
  back_z0    = seat_h - 0.03
  seat_z0    = base_top
  seat_x0    = arm_w
  seat_x1    = w - arm_w

  # ---- materiais (3 tons + pes + piping) ----------------------------------
  model = Sketchup.active_model
  model.entities.clear!
  fab  = SP.mat(model, 'sofa_linho',   [210, 200, 185])  # tecido linho (assento)
  base = SP.mat(model, 'sofa_estrut',  [126, 120, 111])  # estrutura/base (mais escura)
  back = SP.mat(model, 'sofa_encosto', [186, 177, 163])  # encosto (sombra)
  pipe = SP.mat(model, 'sofa_piping',  [150, 142, 128])  # vivo/costura
  wood = SP.mat(model, 'sofa_pe',      [ 96,  66,  44])  # pe madeira (walnut)

  root = model.active_entities.add_group
  root.name = 'Sofa_3seat_v1'
  ent = root.entities

  # ---- 1. pes (4 curtos, recuados, afilados) ------------------------------
  fr = 0.05
  fhw = 0.045
  [[fr + fhw, fr + fhw], [w - fr - fhw, fr + fhw],
   [fr + fhw, d - fr - fhw], [w - fr - fhw, d - fr - fhw]].each_with_index do |(lx, ly), i|
    SP.leg(ent, lx, ly, fhw, 0.0, foot_h, taper: 0.35, mat_obj: wood, name: "leg_#{i + 1}")
  end

  # ---- 2. base/plinto (recuado na frente) ---------------------------------
  SP.rounded_box(ent, seat_x0, rec, seat_x1, d, foot_h, base_top,
                 r: 0.03, top_bevel: 0.0, mat_obj: base, name: 'base_main')

  # ---- 3. bracos (largos, topo arredondado) -------------------------------
  SP.armrest(ent, 0.0, 0.0, arm_w, d, foot_h, arm_h, mat_obj: fab, name: 'arm_left')
  SP.armrest(ent, w - arm_w, 0.0, w, d, foot_h, arm_h, mat_obj: fab, name: 'arm_right')

  # ---- 4. almofadas de assento (3, vinco, COROADAS, piping) ----------------
  cw = (seat_x1 - seat_x0 - gap * (seats - 1)) / seats
  seats.times do |i|
    sx0 = seat_x0 + i * (cw + gap)
    SP.seat_cushion(ent, sx0, seat_front, sx0 + cw, seat_back, seat_z0, seat_h,
                    r: 0.05, crown: 0.06, mat_obj: fab, piping_mat: pipe, name: "seat_#{i + 1}")
  end

  # ---- 5. almofadas de encosto (3, COROADAS) + rake por rotacao ------------
  pivot = Geom::Point3d.new(0, seat_back * SP::M, back_z0 * SP::M)
  rake = Geom::Transformation.rotation(pivot, Geom::Vector3d.new(1, 0, 0),
                                       -rake_deg * Math::PI / 180.0)
  seats.times do |i|
    bx0 = seat_x0 + i * (cw + gap)
    bg = SP.back_cushion(ent, bx0, seat_back, bx0 + cw, d, back_z0, h,
                         r: 0.05, crown: 0.05, mat_obj: back, piping_mat: pipe, name: "back_#{i + 1}")
    bg.transform!(rake) if bg
  end

  # ---- render dos 4 checks -------------------------------------------------
  view = model.active_view
  bb = model.bounds
  c = bb.center
  diag = bb.diagonal
  up = Geom::Vector3d.new(0, 0, 1)

  set = lambda do |eye, target, upv, persp|
    cam = Sketchup::Camera.new(eye, target, upv)
    cam.perspective = persp
    view.camera = cam
    view.zoom_extents
  end
  png = lambda do |name|
    view.write_image(filename: File.join(RDIR, name), width: 1600, height: 1200,
                     antialias: true, transparent: false)
  end

  set.call(Geom::Point3d.new(c.x, bb.min.y - diag, c.z), c, up, false)            # FRONT
  png.call('sofa_front.png')
  set.call(Geom::Point3d.new(bb.max.x + diag, c.y, c.z), c, up, false)            # SIDE
  png.call('sofa_side.png')
  set.call(Geom::Point3d.new(c.x, c.y, bb.max.z + diag * 2), c,
           Geom::Vector3d.new(0, 1, 0), false)                                    # TOP
  png.call('sofa_top.png')
  set.call(Geom::Point3d.new(bb.max.x + diag * 0.8, bb.min.y - diag * 0.9, c.z + diag * 0.7),
           c, up, true)                                                           # 3/4
  png.call('sofa_3q.png')

  FileUtils.mkdir_p(File.dirname(OUTP))
  model.save(OUTP)

  File.write(LOGP, "ok parts=#{root.entities.length} bbox_in=#{bb.min.to_a.map { |v| v.round(1) }}..#{bb.max.to_a.map { |v| v.round(1) }}\nrenders: front side top 3q\nskp: #{OUTP}\n")
rescue StandardError => e
  begin
    FileUtils.mkdir_p(File.dirname(LOGP))
    File.write(LOGP, "ERROR: #{e.class}: #{e.message}\n#{e.backtrace.first(12).join("\n")}\n")
  rescue StandardError
    nil
  end
end
