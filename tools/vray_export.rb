# vray_export.rb — abre o modelo (ja mobiliado), seta a camera e EXPORTA um .vrscene
# via a API Ruby do V-Ray (VRay::RenderSessionExport). Depois o vray.exe renderiza o
# .vrscene HEADLESS. Rodado: SketchUp.exe <furnished_copy.skp> -RubyStartup vray_export.rb
# Env: VRSCENE_OUT (.vrscene), VRAY_LOG (sinal done), VRAY_CAM (iso|top), VRAY_DEFER (s).
def vray_export_run
  log = ENV['VRAY_LOG'] || File.join(__dir__, 'vray_export_log.txt')
  vrscene = ENV['VRSCENE_OUT'] || File.join(__dir__, 'export.vrscene')
  out = []
  begin
    model = Sketchup.active_model
    view = model.active_view
    bb = model.bounds
    c = bb.center
    d = bb.diagonal
    cam_mode = ENV['VRAY_CAM'] || 'iso'
    if cam_mode == 'top'
      eye = Geom::Point3d.new(c.x, c.y, c.z + d * 1.6)
      up = Geom::Vector3d.new(0, 1, 0)
      persp = false
    else
      eye = Geom::Point3d.new(c.x + d * 0.55, c.y - d * 0.65, c.z + d * 0.7)
      up = Geom::Vector3d.new(0, 0, 1)
      persp = true
    end
    cam = Sketchup::Camera.new(eye, c, up)
    cam.perspective = persp
    cam.fov = 50 if persp
    view.camera = cam
    out << "camera set (#{cam_mode}); model bounds diag=#{d.round}"

    ctx = (VRay::Context.active rescue nil)
    out << "VRay::Context.active -> #{ctx.class} nil?=#{ctx.nil?}"
    if ctx
      File.delete(vrscene) if File.exist?(vrscene)
      VRay::RenderSessionExport.new(context: ctx, path: vrscene).start
      ex = File.exist?(vrscene)
      out << "vrscene exported=#{ex} size=#{(ex ? File.size(vrscene) : 0)}"
    else
      out << "SEM context — export abortado"
    end
    out << "DONE"
  rescue StandardError => e
    out << "VRAY_EXPORT ERR: #{e.class}: #{e.message}"
    out << (e.backtrace.first(6).join("\n") rescue '')
  end
  File.write(log, out.join("\n"))
end

UI.start_timer((ENV['VRAY_DEFER'] || '12').to_f, false) { vray_export_run }
