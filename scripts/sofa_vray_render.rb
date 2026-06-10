# sofa_vray_render.rb — render V-Ray HEADLESS scriptado (track de realismo).
# Rodar: SketchUp.exe <sofa.skp> -RubyStartup scripts/sofa_vray_render.rb
# ENV: VRAY_DIR (saida), VRAY_LOG, VRAY_W/VRAY_H (tamanho), VRAY_CAM (front|side|three_quarter).
#
# DESCOBERTA-CHAVE (2026-06-10): renderer.start SOZINHO nao exporta a geometria ->
# render idle em 0s/imagem vazia. O passo OBRIGATORIO antes e:
#   VRay::ModelExporter.new(model:, scene:, renderer:).export_model(view: model.active_view)
# que "combines model and scene and exports to the renderer, with settings and view".
# Depois: renderer.start -> renderer.wait (start(sync:true) espera o START, nao o FIM;
# wait() espera terminar -> state :idleDone) -> renderer.save_vfb_image(path, apply_color_corrections:).
# Materiais do SketchUp sao AUTO-convertidos pra VRayBRDF no export (albedo -> diffuse).
# Ajuste fino de roughness/bump/sheen = via subscriber on_model_exported (proximo passo).

DIR = ENV['VRAY_DIR'] || File.join(File.dirname(File.dirname(__FILE__)), 'renders', 'sofa_vray')
OUT = "#{DIR}/vray_out.png"
LOG = ENV['VRAY_LOG'] || "#{DIR}/vray_log.txt"
W = (ENV['VRAY_W'] || '1200').to_i
H = (ENV['VRAY_H'] || '900').to_i
require 'fileutils'
FileUtils.mkdir_p(DIR) rescue nil
L = []
def flush(arr, log); File.write(log, arr.join("\n") + "\n") rescue nil; end

# Chao neutro (GPT V-Ray passo1): bounce + contexto, ~6m, NEUTRO, no z minimo do sofa.
# Adicionar ANTES de medir a camera (e usar bounds do SOFA, nao do chao, p/ enquadrar).
def add_ground(model, sbb)
  ents = model.active_entities
  M = 39.3700787402
  gm = model.materials['vray_ground'] || model.materials.add('vray_ground')
  gm.color = Sketchup::Color.new(150, 150, 150)
  sc = sbb.center; gz = sbb.min.z; half = 3.0 * M
  pts = [[sc.x - half, sc.y - half, gz], [sc.x + half, sc.y - half, gz],
         [sc.x + half, sc.y + half, gz], [sc.x - half, sc.y + half, gz]].map { |a| Geom::Point3d.new(*a) }
  f = ents.add_face(pts); f.material = gm; f.back_material = gm
  f.reverse! if f.normal.z < 0
rescue StandardError
  nil
end

# camera 3/4 ENQUADRADA NO SOFA (sbb = bounds do sofa, capturado antes do chao)
def place_camera(model, sbb, kind)
  sc = sbb.center; dg = sbb.diagonal
  up = Geom::Vector3d.new(0, 0, 1)
  eye = case kind
        when 'front' then Geom::Point3d.new(sc.x, sbb.min.y - dg * 1.05, sc.z + dg * 0.1)
        when 'side'  then Geom::Point3d.new(sbb.max.x + dg * 1.05, sc.y, sc.z + dg * 0.1)
        else Geom::Point3d.new(sbb.max.x + dg * 0.55, sbb.min.y - dg * 0.75, sc.z + dg * 0.45)
        end
  cam = Sketchup::Camera.new(eye, Geom::Point3d.new(sc.x, sc.y, sc.z + dg * 0.05), up)
  cam.perspective = true; cam.fov = 35
  model.active_view.camera = cam
end

begin
  ctx = VRay::Context.active
  scene = ctx.scene; renderer = ctx.renderer; model = ctx.model
  L << "ctx ok | model=#{model.title} | VRay #{VRay::SKETCHUP_VERSION rescue '?'}"; flush(L, LOG)

  sbb = model.bounds            # bounds do SOFA (antes do chao)
  add_ground(model, sbb)        # GPT passo1: chao neutro
  place_camera(model, sbb, ENV['VRAY_CAM'] || 'three_quarter')

  # output + AUTO-EXPOSICAO + WB neutro (GPT passo2: charcoal le cinza-carvao, nao preto)
  scene.change {
    so = scene['/SettingsOutput']
    so[:img_width] = W; so[:img_height] = H; so[:lock_resolution] = true
    scam = scene['/SettingsCamera']
    if scam
      scam[:auto_exposure] = 1 rescue nil
      scam[:auto_white_balance] = 1 rescue nil
    end
  }

  # PASSO OBRIGATORIO: exportar modelo+scene pro renderer
  exporter = VRay::ModelExporter.new(model: model, scene: scene, renderer: renderer)
  exporter.export_model(view: model.active_view)
  # re-garante auto-exposicao apos export
  begin
    scam = scene['/SettingsCamera']
    scene.change { scam[:auto_exposure] = 1; scam[:auto_white_balance] = 1 } if scam
  rescue StandardError
    nil
  end
  L << "export_model OK"; flush(L, LOG)

  t0 = Time.now
  renderer.start
  renderer.wait rescue nil
  t = 0
  while renderer.state.to_s =~ /render|prepar|init/i
    sleep 1; t += 1; break if t > 480
  end
  L << "render #{(Time.now - t0).round(1)}s state=#{renderer.state}"; flush(L, LOG)

  renderer.save_vfb_image(OUT, apply_color_corrections: true)
  ok = File.exist?(OUT) && File.size(OUT) > 8000
  L << "save #{OUT} -> #{(File.size(OUT) rescue 0)} bytes ok=#{ok}"
  L << "DONE"; flush(L, LOG)
rescue => e
  L << "FATAL: #{e.class}: #{e.message}"; L << (e.backtrace.first(8).join("\n") rescue '')
  flush(L, LOG)
end
