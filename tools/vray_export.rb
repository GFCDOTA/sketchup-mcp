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

    # TEXTURAS premium: aplica texturas procedurais nos materiais dos moveis (SU da UV;
    # V-Ray traduz). So na exportacao V-Ray (line renders continuam chapados). VRAY_TEX_DIR.
    tex_dir = ENV['VRAY_TEX_DIR']
    if tex_dir && File.directory?(tex_dir)
      wd = 'wood_dark.png'; wm = 'wood_medium.png'; fl = 'fabric_light.png'; fa = 'fabric_accent.png'
      tex_map = {
        'ph_estrado' => wd, 'ph_foot' => wd, 'ph_pe' => wd, 'ph_plinto' => wd, 'ph_rodape' => wd,
        'ph_mesa_centro' => wd, 'ph_base' => wd,
        'ph_corpo' => wm, 'ph_porta' => wm, 'ph_tampo' => wm, 'ph_gaveta' => wm, 'ph_rack_tv' => wm,
        'ph_dresser' => wm, 'ph_bancada' => wm, 'ph_torre' => wm, 'ph_aereo' => wm,
        'ph_seat_cushion' => fl, 'ph_back_cushion' => fl, 'ph_arm' => fl, 'ph_colchao' => fl,
        'ph_travesseiro' => fl, 'ph_headboard' => fl,
        'ph_manta' => fa, 'ph_tapete' => fa, 'ph_rug' => fa
      }
      n_tex = 0
      tex_map.each do |matname, png|
        m = model.materials[matname]
        next unless m
        path = File.join(tex_dir, png)
        next unless File.exist?(path)
        begin
          m.texture = path
          m.texture.size = [40, 40]   # ~1m de repeticao (inches)
          n_tex += 1
        rescue StandardError => e
          out << "tex ERR #{matname}: #{e.message}"
        end
      end
      out << "texturas aplicadas: #{n_tex}"
    end

    view = model.active_view
    bb = model.bounds
    c = bb.center
    d = bb.diagonal
    cam_mode = ENV['VRAY_CAM'] || 'iso'
    up = Geom::Vector3d.new(0, 0, 1)
    persp = true
    if ENV['VRAY_EYE'] && ENV['VRAY_TARGET']
      # camera INTERIOR custom: eye + target em inches (coords do modelo)
      ex, ey, ez = ENV['VRAY_EYE'].split(',').map(&:to_f)
      tx, ty, tz = ENV['VRAY_TARGET'].split(',').map(&:to_f)
      eye = Geom::Point3d.new(ex, ey, ez)
      c = Geom::Point3d.new(tx, ty, tz)
      out << "camera CUSTOM eye=#{ENV['VRAY_EYE']} target=#{ENV['VRAY_TARGET']}"
    elsif cam_mode == 'top'
      eye = Geom::Point3d.new(c.x, c.y, c.z + d * 1.6)
      up = Geom::Vector3d.new(0, 1, 0)
      persp = false
      out << "camera top"
    else
      eye = Geom::Point3d.new(c.x + d * 0.55, c.y - d * 0.65, c.z + d * 0.7)
      out << "camera iso; diag=#{d.round}"
    end
    cam = Sketchup::Camera.new(eye, c, up)
    cam.perspective = persp
    cam.fov = (ENV['VRAY_FOV'] || '55').to_f if persp
    view.camera = cam

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
