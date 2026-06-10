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

# camera deterministica (mesma linguagem do render_views SketchUp)
def place_camera(model, kind)
  bb = model.bounds; c = bb.center; dg = bb.diagonal
  up = Geom::Vector3d.new(0, 0, 1)
  eye = case kind
        when 'front' then Geom::Point3d.new(c.x, bb.min.y - dg, c.z)
        when 'side'  then Geom::Point3d.new(bb.max.x + dg, c.y, c.z)
        else Geom::Point3d.new(bb.max.x + dg * 0.85, bb.min.y - dg * 0.95, c.z + dg * 0.65)
        end
  cam = Sketchup::Camera.new(eye, c, up); cam.perspective = true
  model.active_view.camera = cam; model.active_view.zoom_extents
end

begin
  ctx = VRay::Context.active
  scene = ctx.scene; renderer = ctx.renderer; model = ctx.model
  L << "ctx ok | model=#{model.title} | VRay #{VRay::SKETCHUP_VERSION rescue '?'}"; flush(L, LOG)
  place_camera(model, ENV['VRAY_CAM'] || 'three_quarter')

  scene.change {
    so = scene['/SettingsOutput']
    so[:img_width] = W; so[:img_height] = H; so[:lock_resolution] = true
  }

  # PASSO OBRIGATORIO: exportar modelo+scene pro renderer
  exporter = VRay::ModelExporter.new(model: model, scene: scene, renderer: renderer)
  exporter.export_model(view: model.active_view)
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
