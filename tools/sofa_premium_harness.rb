# sofa_premium_harness.rb — FP-SOFA-PREMIUM itens 2-3: constroi o sofa premium
# como COMPONENTES SketchUp reais a partir do parts JSON do build_sofa (boxes +
# profile_xz/profile_yz), opcionalmente aplica a alt_006 (roundover 25mm nas
# arestas VERTICAIS frontais dos bracos via INTERSECAO de solidos: prisma do
# perfil-topo ∩ prisma do plano com cantos frontais em arco), salva o .skp e
# renderiza as 4 cameras canonicas em clay (sem materiais).
#
# Env: SOFA_HARNESS_JSON, SOFA_HARNESS_OUT (.skp), SOFA_HARNESS_PNG (prefixo),
#      SOFA_HARNESS_ALT006 ("1" liga), SOFA_HARNESS_LOG.
require "json"

M_TO_IN = 39.3700787402
ALT006_R_M = 0.025

def log_line(msg)
  path = ENV["SOFA_HARNESS_LOG"]
  return unless path
  File.open(path, "a") { |f| f.puts("#{Time.now.strftime('%H:%M:%S')} #{msg}") }
end

def pts3(arr)
  arr.map { |x, y, z| Geom::Point3d.new(x * M_TO_IN, y * M_TO_IN, z * M_TO_IN) }
end

def build_part(ents, part)
  g = ents.add_group
  g.name = part["label"]
  ge = g.entities
  if (prof = part["profile_xz"])
    # perfil em (x,z) na cota y0, extrudado ate y1
    y0 = part["y0"]
    face = ge.add_face(pts3(prof.map { |x, z| [x, y0, z] }))
    return g if face.nil?
    depth = (part["y1"] - part["y0"]) * M_TO_IN
    # pushpull na direcao +Y: se a normal olha -Y, empurra negativo
    face.pushpull(face.normal.y > 0 ? depth : -depth)
  elsif (prof = part["profile_yz"])
    x0 = part["x0"]
    face = ge.add_face(pts3(prof.map { |y, z| [x0, y, z] }))
    return g if face.nil?
    depth = (part["x1"] - part["x0"]) * M_TO_IN
    face.pushpull(face.normal.x > 0 ? depth : -depth)
  else
    x0, y0, x1, y1 = part.values_at("x0", "y0", "x1", "y1")
    z0, z1 = part["z0"], part["z1"]
    face = ge.add_face(pts3([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]]))
    return g if face.nil?
    h = (z1 - z0) * M_TO_IN
    face.pushpull(face.normal.z > 0 ? h : -h)
    g.transform!(Geom::Transformation.translation(Geom::Vector3d.new(0, 0, z0 * M_TO_IN))) if z0.abs > 1e-9
  end
  g
end

def rounded_front_plan_cutter(ents, part, r_m)
  # prisma do FOOTPRINT do braco com os 2 cantos FRONTAIS (y0) em arco r_m,
  # extrudado a altura toda + folga — o ∩ com o braco arredonda as arestas
  # verticais frontais preservando o roundover do topo.
  x0, y0, x1, y1 = part.values_at("x0", "y0", "x1", "y1")
  z0, z1 = part["z0"], part["z1"]
  r = [r_m, (x1 - x0) / 2.0 - 1e-4, (y1 - y0) / 2.0 - 1e-4].min
  pts = []
  seg = 6
  # CCW no plano: fundo (y1) reto; frente (y0) com arcos
  pts << [x0, y1]
  pts << [x0, y0 + r]
  seg.times do |i|  # canto frontal-esquerdo: centro (x0+r, y0+r), 180->270
    a = Math::PI + (Math::PI / 2.0) * (i + 1) / seg
    pts << [x0 + r + r * Math.cos(a), y0 + r + r * Math.sin(a)]
  end
  pts << [x1 - r, y0]
  seg.times do |i|  # canto frontal-direito: centro (x1-r, y0+r), 270->360
    a = 1.5 * Math::PI + (Math::PI / 2.0) * (i + 1) / seg
    pts << [x1 - r + r * Math.cos(a), y0 + r + r * Math.sin(a)]
  end
  pts << [x1, y1]
  g = ents.add_group
  face = g.entities.add_face(pts3(pts.map { |x, y| [x, y, z0 - 0.01] }))
  return nil if face.nil?
  h = (z1 - z0 + 0.02) * M_TO_IN
  face.pushpull(face.normal.z > 0 ? h : -h)
  g
end

def render_cam(model, center_in, radius_in, elev_deg, azim_deg, png, w, h)
  el = elev_deg * Math::PI / 180.0
  az = azim_deg * Math::PI / 180.0
  eye = Geom::Point3d.new(
    center_in.x + radius_in * Math.cos(el) * Math.cos(az),
    center_in.y + radius_in * Math.cos(el) * Math.sin(az),
    center_in.z + radius_in * Math.sin(el),
  )
  cam = Sketchup::Camera.new(eye, center_in, Geom::Vector3d.new(0, 0, 1))
  cam.perspective = true
  cam.fov = 45.0
  model.active_view.camera = cam
  model.active_view.write_image(filename: png, width: w, height: h,
                                antialias: true, transparent: false)
end

begin
  model = Sketchup.active_model
  model.start_operation("sofa_premium_harness", true)
  model.entities.clear!
  log_line("modelo limpo")

  parts = JSON.parse(File.read(ENV["SOFA_HARNESS_JSON"]))
  groups = {}
  parts.each do |part|
    g = build_part(model.entities, part)
    groups[part["label"]] = g
    log_line("part #{part['label']} ok")
  end

  if ENV["SOFA_HARNESS_ALT006"] == "1"
    parts.select { |p| p["kind"] == "arm" }.each do |part|
      arm = groups[part["label"]]
      cutter = rounded_front_plan_cutter(model.entities, part, ALT006_R_M)
      if cutter.nil?
        log_line("alt006 #{part['label']} FAIL cutter nil")
        next
      end
      begin
        res = arm.intersect(cutter)
        if res
          res.name = part["label"]
          groups[part["label"]] = res
          log_line("alt006 #{part['label']} INTERSECT ok")
        else
          cutter.erase!
          log_line("alt006 #{part['label']} intersect nil — mantido sem fillet vertical")
        end
      rescue => e
        cutter.erase! rescue nil
        log_line("alt006 #{part['label']} EXCEPTION #{e.class}: #{e.message}")
      end
    end
    # suaviza as arestas dos arcos (soften coerente, nao esconde geometria)
    model.entities.grep(Sketchup::Group).each do |g|
      g.entities.grep(Sketchup::Edge).each do |e|
        e.soft = e.smooth = true if e.faces.length == 2 &&
                                    e.faces[0].normal.angle_between(e.faces[1].normal) < 0.45
      end
    end
    log_line("soften aplicado")
  end

  model.commit_operation

  out = ENV["SOFA_HARNESS_OUT"]
  model.save(out)
  log_line("skp salvo #{out}")

  # bbox -> cameras canonicas
  bb = model.bounds
  c = bb.center
  radius = bb.diagonal * 1.7
  cams = [["iso_3q", 20, -35], ["frente", 8, -90], ["lado", 8, 0], ["iso_alta", 35, -55]]
  prefix = ENV["SOFA_HARNESS_PNG"]
  cams.each do |name, elev, azim|
    png = "#{prefix}_#{name}.png"
    render_cam(model, c, radius, elev, azim, png, 1400, 1000)
    log_line("render #{name} ok")
  end
  log_line("DONE")
rescue => e
  log_line("FATAL #{e.class}: #{e.message}\n#{e.backtrace.first(5).join("\n")}")
end
